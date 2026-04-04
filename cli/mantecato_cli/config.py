from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "mantecato"
    return Path.home() / ".config" / "mantecato"


def _config_path() -> Path:
    return _config_dir() / "config.toml"


def _ensure_config_dir() -> None:
    _config_dir().mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def save_config(config: dict[str, Any]) -> None:
    _ensure_config_dir()
    path = _config_path()
    import tomli_w

    with open(path, "wb") as f:
        tomli_w.dump(config, f)


def get_value(key: str) -> str | None:
    config = load_config()
    parts = key.split(".")
    current: Any = config
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return str(current) if current is not None else None


def set_value(key: str, value: str) -> None:
    config = load_config()
    parts = key.split(".")
    current = config
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    save_config(config)


def list_values() -> dict[str, Any]:
    return load_config()


def get_database_url() -> str | None:
    env = os.environ.get("DATABASE_URL")
    if env:
        return env
    return get_value("database.url")


def get_default_site() -> str | None:
    return get_value("defaults.site")


def get_default_period() -> str:
    val = get_value("defaults.period")
    return val or "30d"


def get_default_format() -> str:
    val = get_value("defaults.format")
    return val or "table"
