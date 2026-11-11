"""Synthetic proc/cgroup fixtures: never inspect a real deployment in tests."""

import json
import subprocess
import sys
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from mantecato.memory import MemorySampler, cgroup_memory, process_memory, snapshot


def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.mark.parametrize("relative", ["/", "/tenant/web"])
def test_cgroup_v2_preserves_cache_components_and_unlimited(tmp_path, relative):
    proc, root = tmp_path / "proc", tmp_path / "cgroup"
    put(proc / "self/cgroup", f"0::{relative}\n")
    directory = root / relative.lstrip("/")
    put(directory / "memory.current", "1000\n")
    put(directory / "memory.peak", "1500\n")
    put(directory / "memory.max", "max\n")
    put(directory / "memory.stat", "anon 400\nfile 600\nshmem 100\ninactive_file 200\n")
    put(directory / "memory.events", "oom 0\noom_kill 0\n")
    result = cgroup_memory(proc, root)
    assert result["current_bytes"] == 1000
    assert result["limit_bytes"] is None
    assert result["lifetime_peak_bytes"] == 1500
    assert result["stat"] == {"anon": 400, "file": 600, "shmem": 100, "inactive_file": 200}


def test_cgroup_namespaced_mount_and_v1_fallback(tmp_path):
    proc, root = tmp_path / "proc", tmp_path / "cgroup"
    put(proc / "self/cgroup", "7:memory:/host/path\n")
    put(root / "memory/memory.usage_in_bytes", "400\n")
    put(root / "memory/memory.limit_in_bytes", str(2**63))
    result = cgroup_memory(proc, root)
    assert result["version"] == 1 and result["current_bytes"] == 400
    assert result["limit_bytes"] is None and result["lifetime_peak_bytes"] is None
    assert cgroup_memory(tmp_path / "missing", root) == {}


def test_namespace_membership_never_traverses_outside_cgroup_mount(tmp_path):
    proc, root = tmp_path / "proc", tmp_path / "cgroup"
    put(proc / "self/cgroup", "0::/../../outside\n")
    put(root / "memory.current", "900")
    result = cgroup_memory(proc, root)
    assert result["current_bytes"] == 900
    assert result["resolution"] == "mount_root_fallback"


def test_process_tree_uses_pss_not_virtual_stack_size_and_skips_unrelated(tmp_path):
    for pid, parent in [(10, 1), (11, 10), (12, 11), (20, 1)]:
        put(
            tmp_path / str(pid) / "status",
            f"Pid:\t{pid}\nPPid:\t{parent}\nVmRSS:\t100 kB\nVmSize:\t999999 kB\nThreads:\t2\n",
        )
        put(
            tmp_path / str(pid) / "smaps_rollup",
            "Pss: 60 kB\nPrivate_Clean: 5 kB\nPrivate_Dirty: 20 kB\nShared_Clean: 75 kB\n",
        )
    result = process_memory((10,), tmp_path)
    assert [p["pid"] for p in result] == [10, 11, 12]
    assert all(p["rss_bytes"] == 102400 and p["pss_bytes"] == 61440 for p in result)
    assert all(p["private_bytes"] == 25600 and p["threads"] == 2 for p in result)
    with (
        patch("mantecato.memory.process_memory", return_value=result),
        patch("mantecato.memory.cgroup_memory", return_value={}),
    ):
        report = snapshot((10,))
    assert report["process_totals"]["pss_bytes"] == 3 * 61440
    assert report["rss_sum_double_counts_shared_pages"] is True
    assert "VmSize" not in json.dumps(report)


def test_missing_pss_is_unavailable_not_a_misleading_partial_sum():
    rows = [{"rss_bytes": 100, "pss_bytes": None, "private_bytes": None}]
    with (
        patch("mantecato.memory.process_memory", return_value=rows),
        patch("mantecato.memory.cgroup_memory", return_value={}),
    ):
        result = snapshot()
    assert result["process_totals"] == {"rss_bytes": 100, "pss_bytes": None, "private_bytes": None}


def test_sampler_keeps_endpoints_and_peaks_not_sample_history():
    counter = iter([100, 300, 200])

    def sample(roots):
        return {"process_totals": {"rss_bytes": next(counter)}, "observer_cgroup": {}}

    with patch("mantecato.memory.snapshot", side_effect=sample):
        sampler = MemorySampler(lambda: (123,), interval=10)
        with sampler:
            sampler._sample()
    assert sampler.result["samples"] == 3
    assert sampler.result["peaks"]["rss_bytes"] == 300
    assert sampler.result["start"]["process_totals"]["rss_bytes"] == 100
    assert sampler.result["end"]["process_totals"]["rss_bytes"] == 200
    assert "history" not in sampler.result


def test_sampler_reports_observer_failure_instead_of_zero_memory():
    with (
        patch("mantecato.memory.snapshot", side_effect=OSError("unavailable")),
        MemorySampler(lambda: (123,), interval=10) as sampler,
    ):
        pass
    assert sampler.result["samples"] == 0
    assert sampler.result["sampling_errors"] == 2
    assert sampler.result["peaks"] == {}


def test_standalone_report_needs_no_django_configuration():
    completed = subprocess.run(
        [sys.executable, "-m", "mantecato.memory"],
        env={},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout)["rss_sum_double_counts_shared_pages"] is True
    assert not completed.stderr


def test_memory_command_does_not_access_database_or_run_system_checks():
    output = StringIO()
    with (
        patch(
            "django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection",
            side_effect=AssertionError("DB access"),
        ),
        patch("mantecato.memory.process_memory", return_value=[]),
    ):
        call_command("memory_report", stdout=output)
    result = json.loads(output.getvalue())
    assert result["sample"] == 0 and "database" not in result


@pytest.mark.parametrize(
    "options",
    [
        {"samples": 0},
        {"samples": 3601},
        {"interval": 0.01},
        {"interval": float("nan")},
        {"pid": [-1]},
    ],
)
def test_memory_command_rejects_unbounded_or_invalid_requests(options):
    with pytest.raises(CommandError):
        call_command("memory_report", **options)


@pytest.mark.django_db(transaction=True)
def test_optional_database_metadata_is_read_only_and_sanitized():
    output = StringIO()
    call_command("memory_report", database=True, stdout=output)
    result = json.loads(output.getvalue())["database"]
    assert result["backends"] >= 1
    assert any(s["name"] == "work_mem" for s in result["settings"])
    for forbidden in ("password", "visitor_key", "username", "query"):
        assert forbidden not in json.dumps(result)
