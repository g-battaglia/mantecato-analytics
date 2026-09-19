"""Configuration loading that keeps API secrets out of command arguments."""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from mantecato_cli.errors import UsageError


@dataclass(frozen=True)
class ClientConfig:
    base_url: str
    api_key: str
    timeout: float = 30.0


@dataclass(frozen=True)
class UserConfig:
    profiles: dict[str, dict[str, str]]
    segments: dict[str, list[str]]


def default_config_path() -> Path:
    """Return the documented per-user configuration path."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "mantecato" / "config.yaml"
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "mantecato" / "config.yaml"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "mantecato" / "config.yaml"


def load_user_config(path: Path | None = None) -> UserConfig:
    """Load profiles and filter-only segments through YAML safe loading."""
    target = path or default_config_path()
    if not target.exists():
        return UserConfig(profiles={}, segments={})
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise UsageError(f"Cannot read config file {target}: {exc}") from exc
    if not isinstance(raw, dict):
        raise UsageError("Config root must be an object.")

    profiles_raw = raw.get("profiles") or {}
    segments_raw = raw.get("segments") or {}
    if not isinstance(profiles_raw, dict) or not isinstance(segments_raw, dict):
        raise UsageError("profiles and segments must be objects.")

    profiles: dict[str, dict[str, str]] = {}
    for name, profile in profiles_raw.items():
        if not isinstance(name, str) or not isinstance(profile, dict):
            raise UsageError("Each profile must be an object with a string name.")
        unexpected = set(profile) - {"url", "key_file"}
        if unexpected:
            raise UsageError(f"Profile {name} has unsupported fields: {', '.join(unexpected)}")
        profiles[name] = {key: str(value) for key, value in profile.items()}

    segments: dict[str, list[str]] = {}
    for name, segment in segments_raw.items():
        if not isinstance(name, str) or not isinstance(segment, dict):
            raise UsageError("Each segment must be an object with a string name.")
        if set(segment) != {"filters"} or not isinstance(segment["filters"], list):
            raise UsageError(f"Segment {name} may contain only a filters array.")
        filters = segment["filters"]
        if not all(isinstance(item, str) for item in filters):
            raise UsageError(f"Segment {name} contains a non-string filter.")
        segments[name] = list(filters)
    return UserConfig(profiles=profiles, segments=segments)


def resolve_client_config(
    *,
    url: str | None,
    key_file: Path | None,
    profile: str | None,
    config_path: Path | None,
    timeout: float,
) -> tuple[ClientConfig, UserConfig]:
    """Resolve explicit options, environment, then a non-secret profile."""
    user = load_user_config(config_path)
    profile_data: dict[str, str] = {}
    if profile:
        if profile not in user.profiles:
            available = ", ".join(sorted(user.profiles)) or "(none)"
            raise UsageError(f"Unknown profile {profile}. Available profiles: {available}")
        profile_data = user.profiles[profile]

    base_url = url or os.environ.get("MANTECATO_URL") or profile_data.get("url")
    if not base_url:
        raise UsageError("MANTECATO_URL is required.")
    base_url = _validate_url(base_url)

    selected_key_file = key_file
    if selected_key_file is None:
        env_file = os.environ.get("MANTECATO_API_KEY_FILE")
        configured_file = profile_data.get("key_file")
        if env_file or configured_file:
            selected_key_file = Path(env_file or configured_file or "").expanduser()
    api_key = os.environ.get("MANTECATO_API_KEY")
    if not api_key and selected_key_file:
        api_key = _read_key_file(selected_key_file)
    if not api_key:
        raise UsageError("MANTECATO_API_KEY or MANTECATO_API_KEY_FILE is required.")
    if not api_key.startswith("mtk_"):
        raise UsageError("The API key does not have the expected mtk_ prefix.")
    if timeout <= 0:
        raise UsageError("Timeout must be greater than zero.")
    return ClientConfig(base_url=base_url, api_key=api_key, timeout=timeout), user


def segment_filters(user: UserConfig, names: list[str]) -> list[list[str]]:
    """Resolve each named segment as its own AND filter group."""
    groups: list[list[str]] = []
    for name in names:
        if name not in user.segments:
            available = ", ".join(sorted(user.segments)) or "(none)"
            raise UsageError(f"Unknown segment {name}. Available segments: {available}")
        groups.append(user.segments[name])
    return groups


def _validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.username or parsed.password:
        raise UsageError("MANTECATO_URL must not contain credentials.")
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise UsageError("MANTECATO_URL must be an absolute HTTP(S) URL.")
    loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not loopback:
        raise UsageError("Plain HTTP is allowed only for loopback development URLs.")
    if parsed.query or parsed.fragment:
        raise UsageError("MANTECATO_URL must not contain a query string or fragment.")
    return value.rstrip("/")


def _read_key_file(path: Path) -> str:
    try:
        info = path.stat()
        if os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o077:
            raise UsageError(f"API key file {path} must not be accessible by group or others.")
        return path.read_text(encoding="utf-8").strip()
    except UsageError:
        raise
    except OSError as exc:
        raise UsageError(f"Cannot read API key file {path}: {exc}") from exc
