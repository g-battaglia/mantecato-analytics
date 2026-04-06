"""Unified configuration for mantecato-core.

Reads DATABASE_URL from environment or from a config file at
~/.config/mantecato/config.toml (respects XDG_CONFIG_HOME).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "mantecato"
    return Path.home() / ".config" / "mantecato"


def _config_path() -> Path:
    return _config_dir() / "config.toml"


def load_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {}
    if tomllib is None:
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def get_config_value(key: str) -> str | None:
    config = load_config()
    parts = key.split(".")
    current: Any = config
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return str(current) if current is not None else None


def get_database_url() -> str:
    """Return DATABASE_URL from env or config file, raising if missing."""
    env = os.environ.get("DATABASE_URL")
    if env:
        return env
    from_config = get_config_value("database.url")
    if from_config:
        return from_config
    raise RuntimeError(
        "DATABASE_URL environment variable is required. "
        "Set it to your PostgreSQL connection string, or add database.url "
        "to ~/.config/mantecato/config.toml."
    )
