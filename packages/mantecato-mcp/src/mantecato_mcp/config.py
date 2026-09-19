"""Process-level MCP configuration sourced without exposing secrets as tool inputs."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    timeout: float


def load_config() -> Config:
    url = os.environ.get("MANTECATO_URL", "").strip()
    key = os.environ.get("MANTECATO_API_KEY", "").strip()
    key_file = os.environ.get("MANTECATO_API_KEY_FILE", "").strip()
    if not key and key_file:
        key = _read_key(Path(key_file).expanduser())
    if not url:
        raise ConfigError("MANTECATO_URL is required")
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        raise ConfigError("MANTECATO_URL must not contain credentials")
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ConfigError("MANTECATO_URL must be an absolute HTTP(S) URL")
    loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not loopback:
        raise ConfigError("Plain HTTP is allowed only for loopback development URLs")
    if parsed.query or parsed.fragment:
        raise ConfigError("MANTECATO_URL must not contain a query string or fragment")
    if not key or not key.startswith("mtk_"):
        raise ConfigError("MANTECATO_API_KEY or MANTECATO_API_KEY_FILE is required")
    try:
        timeout = float(os.environ.get("MANTECATO_TIMEOUT", "30"))
    except ValueError as exc:
        raise ConfigError("MANTECATO_TIMEOUT must be numeric") from exc
    if timeout <= 0:
        raise ConfigError("MANTECATO_TIMEOUT must be greater than zero")
    return Config(url.rstrip("/"), key, timeout)


def _read_key(path: Path) -> str:
    try:
        info = path.stat()
        if os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o077:
            raise ConfigError("API key file must not be accessible by group or others")
        return path.read_text(encoding="utf-8").strip()
    except ConfigError:
        raise
    except OSError as exc:
        raise ConfigError(f"Cannot read API key file: {exc}") from exc
