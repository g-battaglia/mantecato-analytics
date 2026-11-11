"""Dependency-free memory diagnostics, shared by the CLI and local benchmarks.

Cgroup totals are authoritative for a container's budget. RSS sums are retained
as diagnostics only: they double-count shared pages. PSS is the better process
attribution on Linux. Missing counters are reported as unavailable, never zero.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def _text(path: Path) -> str:
    try:
        return path.read_text()
    except (OSError, UnicodeError):
        return ""


def _integer(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def _key_values(text: str, *, kib: bool = False) -> dict[str, int]:
    result = {}
    for line in text.splitlines():
        parts = line.replace(":", "").split()
        if len(parts) >= 2 and (value := _integer(parts[1])) is not None:
            result[parts[0]] = value * (1024 if kib and parts[2:] == ["kB"] else 1)
    return result


def cgroup_memory(proc: Path = Path("/proc"), root: Path = Path("/sys/fs/cgroup")) -> dict:
    """Resolve this process's cgroup, including namespaced and nested mounts.

    Do not subtract file cache or add shmem to file: shmem is a component of it.
    The reporting process's cgroup may include more than a benchmark's targets.
    """
    for line in _text(proc / "self/cgroup").splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        _, controllers, relative = parts
        version = 2 if not controllers else 1
        if version == 1 and "memory" not in controllers.split(","):
            continue
        mount = root if version == 2 else root / "memory"
        counter = "memory.current" if version == 2 else "memory.usage_in_bytes"
        # The mount can expose either the host hierarchy or this cgroup as '/'.
        # Namespace-relative membership may contain '..'. Never traverse it;
        # use the exposed mount root and label that fallback explicitly.
        candidates = [] if ".." in Path(relative).parts else [mount / relative.lstrip("/")]
        candidates.append(mount)
        directory = next((p for p in candidates if (p / counter).exists()), None)
        if directory is None:
            continue
        names = (
            ("memory.current", "memory.peak", "memory.max")
            if version == 2
            else ("memory.usage_in_bytes", "memory.max_usage_in_bytes", "memory.limit_in_bytes")
        )
        values = [_integer(_text(directory / name)) for name in names]
        if values[2] is not None and values[2] >= 2**60:
            values[2] = None  # v1's unlimited sentinel, like v2's 'max'.
        return {
            "version": version,
            "resolution": "membership"
            if directory == candidates[0] and ".." not in Path(relative).parts
            else "mount_root_fallback",
            "current_bytes": values[0],
            "lifetime_peak_bytes": values[1],
            "limit_bytes": values[2],
            "stat": _key_values(_text(directory / "memory.stat")),
            "events": _key_values(_text(directory / "memory.events")),
            "pressure": _text(directory / "memory.pressure").strip() or None,
        }
    return {}


def process_memory(roots: tuple[int, ...], proc: Path = Path("/proc")) -> list[dict]:
    """Sample roots and descendants without exporting command lines/environment."""
    processes = {}
    if proc.is_dir():
        for directory in proc.iterdir():
            if not directory.name.isdecimal():
                continue
            status = _key_values(_text(directory / "status"), kib=True)
            if "Pid" not in status:
                continue  # Process exited during observation, or access denied.
            processes[int(directory.name)] = {
                "pid": status["Pid"],
                "parent_pid": status.get("PPid"),
                "threads": status.get("Threads"),
                "rss_bytes": status.get("VmRSS"),
                "pss_bytes": None,
                "private_bytes": None,
            }
    elif sys.platform == "darwin":
        # macOS has no smaps/cgroups. One ps invocation covers the process tree.
        output = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,rss="], capture_output=True, text=True, check=True
        ).stdout
        for line in output.splitlines():
            pid, parent, rss = map(int, line.split())
            processes[pid] = {
                "pid": pid,
                "parent_pid": parent,
                "rss_bytes": rss * 1024,
                "threads": None,
                "pss_bytes": None,
                "private_bytes": None,
            }
    selected = set(roots)
    while True:
        children = {pid for pid, p in processes.items() if p["parent_pid"] in selected}
        expanded = selected | children
        if expanded == selected:
            break
        selected = expanded
    result = [processes[pid] for pid in sorted(selected) if pid in processes]
    # smaps is more expensive than status: inspect selected processes only.
    if proc.is_dir():
        for process in result:
            smaps = _key_values(_text(proc / str(process["pid"]) / "smaps_rollup"), kib=True)
            process["pss_bytes"] = smaps.get("Pss")
            if smaps:
                process["private_bytes"] = sum(
                    smaps.get(key, 0)
                    for key in ("Private_Clean", "Private_Dirty", "Private_Hugetlb")
                )
    return result


def snapshot(roots: tuple[int, ...] | None = None) -> dict:
    processes = process_memory(roots or (os.getpid(),))
    totals = {}
    for field in ("rss_bytes", "pss_bytes", "private_bytes"):
        values = [p[field] for p in processes]
        totals[field] = sum(values) if values and all(v is not None for v in values) else None
    return {
        "processes": processes,
        "process_totals": totals,
        "rss_sum_double_counts_shared_pages": True,
        "observer_cgroup": cgroup_memory(),
        "cgroup_scope": "observer_and_all_other_members_not_just_selected_processes",
    }


class MemorySampler:
    """Keep bounded peaks and endpoints, not an ever-growing sample history.

    Database/cron processes must be included explicitly, or measured in their
    own container. Sampling is observation, not a guaranteed instantaneous peak.
    """

    def __init__(self, roots: Callable[[], tuple[int, ...]], interval: float = 0.25):
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("Sampling interval must be positive")
        self.roots = roots
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.result: dict = {"samples": 0, "interval_seconds": interval, "peaks": {}}

    def _sample(self):
        try:
            value = snapshot(self.roots())
        except (OSError, subprocess.SubprocessError):
            # A failed observer is not a zero-memory sample. Keep the workload
            # running, but explicitly flag incomplete measurement evidence.
            self.result["sampling_errors"] = self.result.get("sampling_errors", 0) + 1
            return
        self.result.setdefault("start", value)
        self.result["end"] = value
        self.result["samples"] += 1
        peaks = self.result["peaks"]
        for key, amount in value["process_totals"].items():
            if amount is not None:
                peaks[key] = max(peaks.get(key, 0), amount)
        current = value["observer_cgroup"].get("current_bytes")
        if current is not None:
            peaks["observer_cgroup_current_bytes"] = max(
                peaks.get("observer_cgroup_current_bytes", 0), current
            )

    def _run(self):
        while not self._stop.wait(self.interval):
            self._sample()

    def __enter__(self):
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        self._sample()


if __name__ == "__main__":
    # The standalone form avoids loading Django merely to observe a container.
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", action="append", type=int, help="Root PID (repeatable)")
    args = parser.parse_args()
    if args.pid and any(pid < 1 for pid in args.pid):
        parser.error("PIDs must be positive")
    print(json.dumps(snapshot(tuple(args.pid) if args.pid else None)))
