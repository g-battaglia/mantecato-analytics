"""Anonymous unique-visitor estimation with aggregate HyperLogLog sketches.

This module intentionally never persists visitor keys. At ingestion time the
server derives one keyed digest from coarse request attributes already present
in the HTTP request, updates aggregate registers, and discards the inputs.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

_PRECISION = 7
_REGISTERS = 1 << _PRECISION
_REGISTER_MASK = _REGISTERS - 1
_HASH_BITS = 64


def empty_registers() -> bytes:
    return bytes(_REGISTERS)


def _normalise_registers(value: bytes | bytearray | memoryview | None) -> bytearray:
    if value is None:
        return bytearray(empty_registers())
    data = bytes(value)
    if len(data) < _REGISTERS:
        data = data + bytes(_REGISTERS - len(data))
    return bytearray(data[:_REGISTERS])


def _rank(remaining: int) -> int:
    width = _HASH_BITS - _PRECISION
    if remaining == 0:
        return width + 1
    return width - remaining.bit_length() + 1


def add_digest(registers: bytes | bytearray | memoryview | None, digest: int) -> bytes:
    """Return registers updated with one 64-bit digest."""
    regs = _normalise_registers(registers)
    index = digest & _REGISTER_MASK
    remaining = digest >> _PRECISION
    rank = _rank(remaining)
    if regs[index] < rank:
        regs[index] = rank
    return bytes(regs)


def merge_registers(rows: list[bytes | bytearray | memoryview | None]) -> bytes:
    """Union many HyperLogLog register arrays."""
    merged = bytearray(empty_registers())
    for row in rows:
        regs = _normalise_registers(row)
        for i, value in enumerate(regs):
            if value > merged[i]:
                merged[i] = value
    return bytes(merged)


def estimate(registers: bytes | bytearray | memoryview | None) -> int:
    """Estimate cardinality from HyperLogLog registers."""
    regs = _normalise_registers(registers)
    indicator = sum(2.0 ** -value for value in regs)
    raw = (0.7213 / (1 + 1.079 / _REGISTERS)) * _REGISTERS * _REGISTERS / indicator
    zeros = regs.count(0)
    if raw <= 2.5 * _REGISTERS and zeros:
        raw = _REGISTERS * math.log(_REGISTERS / zeros)
    return max(0, int(round(raw)))


def _anonymize_ip(ip: str | None) -> str:
    if not ip:
        return "unknown-ip"
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown-ip"
    if parsed.version == 4:
        return str(ipaddress.ip_network(f"{parsed}/24", strict=False).network_address) + "/24"
    return str(ipaddress.ip_network(f"{parsed}/48", strict=False).network_address) + "/48"


def visitor_digest(
    *,
    website_id: str,
    occurred_at: datetime,
    ip: str | None,
    device_info: dict[str, str | None],
) -> int:
    """Build a monthly rotating, site-scoped digest for sketch updates."""
    secret = str(settings.SECRET_KEY).encode()
    month = occurred_at.strftime("%Y-%m")
    subject = "|".join(
        [
            str(website_id),
            month,
            _anonymize_ip(ip),
            device_info.get("browser") or "",
            device_info.get("os") or "",
            device_info.get("device") or "",
        ]
    )
    digest = hmac.new(secret, subject.encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big")


def bucket_hour(value: datetime) -> datetime:
    """Return *value* truncated to the hour, preserving timezone awareness."""
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.replace(minute=0, second=0, microsecond=0)


def section_for_path(path: str, depth: int = 2) -> str:
    """Return the URL-prefix section used by section analytics."""
    clean = (path or "/").split("?", 1)[0].split("#", 1)[0].strip("/")
    if not clean:
        return "/"
    parts = clean.split("/")[:depth]
    return "/" + "/".join(parts)


def scope_rows_for_path(path: str) -> list[tuple[str, str]]:
    """Return sketch scopes updated for one pageview."""
    clean_path = path or "/"
    return [
        ("site", ""),
        ("page", clean_path[:500]),
        ("section", section_for_path(clean_path)[:500]),
    ]


def scope_rows_for_event(event_name: str) -> list[tuple[str, str]]:
    """Return sketch scopes updated for one custom event."""
    return [("event", event_name[:500])]


def update_visitor_sketches(
    *,
    website_id: str,
    occurred_at: datetime,
    ip: str | None,
    device_info: dict[str, str | None],
    url_path: str,
    is_bot: bool,
    scopes: list[tuple[str, str]] | None = None,
) -> None:
    """Update anonymous aggregate visitor sketches for a human pageview."""
    if is_bot:
        return
    from apps.core.models import VisitorSketch

    digest = visitor_digest(
        website_id=website_id,
        occurred_at=occurred_at,
        ip=ip,
        device_info=device_info,
    )
    bucket = bucket_hour(occurred_at)
    for scope, scope_value in (scopes if scopes is not None else scope_rows_for_path(url_path)):
        with transaction.atomic():
            row, _ = VisitorSketch.objects.select_for_update().get_or_create(
                website_id=website_id,
                bucket_start=bucket,
                scope=scope,
                scope_value=scope_value,
                defaults={"registers": empty_registers()},
            )
            updated = add_digest(row.registers, digest)
            if updated != bytes(row.registers):
                row.registers = updated
                row.save(update_fields=["registers", "updated_at"])


def has_only_bot_filter(filters: list[Any] | None) -> bool:
    """Return true when filters contain no content/device/geo narrowing."""
    return all(getattr(f, "column", "") == "__bot_filter__" for f in (filters or []))
