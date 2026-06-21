"""Extract the real client IP from HTTP request headers.

The client IP is the primary input to the cookieless visitor digest, so it is
security-sensitive: a forgeable IP lets callers inflate/deflate visitor counts
and bypass datacenter-bot detection. Header trust is therefore gated by operator
configuration (``TRUST_PROXY_HEADERS`` / ``TRUSTED_PROXY_COUNT``):

* Direct exposure (``TRUST_PROXY_HEADERS=False``) → use ``REMOTE_ADDR`` only.
* Known topology (``TRUSTED_PROXY_COUNT=N>0``) → read the client spoof-resistantly
  from the right of the X-Forwarded-For chain (honouring trusted CDN/custom headers).
* Unknown topology (default) → permissive legacy behaviour (leftmost X-Forwarded-For),
  which is spoofable; a startup warning recommends configuring the hop count.
"""

from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from django.http import HttpRequest

# Regex to strip port suffixes from IPv4 addresses (e.g. "1.2.3.4:8080" -> "1.2.3.4")
_IP_PORT_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3}):\d+$")

# Regex to strip brackets and port from IPv6 addresses (e.g. "[::1]:8080" -> "::1")
_IPV6_BRACKET_RE = re.compile(r"^\[([0-9a-fA-F:]+)\](?::\d+)?$")

# CDN/proxy-specific headers checked before the standard X-Forwarded-For.
# These headers are single-valued (set by the edge proxy itself, not by
# upstream clients) so they are more trustworthy than X-Forwarded-For.
_HEADER_CHAIN = [
    "HTTP_TRUE_CLIENT_IP",  # Akamai, Cloudflare (Enterprise)
    "HTTP_CF_CONNECTING_IP",  # Cloudflare
    "HTTP_FASTLY_CLIENT_IP",  # Fastly
    "HTTP_X_NF_CLIENT_CONNECTION_IP",  # Netlify
    "HTTP_DO_CONNECTING_IP",  # DigitalOcean App Platform
    "HTTP_X_REAL_IP",  # Nginx default reverse proxy header
    "HTTP_X_APPENGINE_USER_IP",  # Google App Engine
    "HTTP_X_CLUSTER_CLIENT_IP",  # Rackspace, some load balancers
]


def get_client_ip(request: HttpRequest) -> str:
    """Extract the client IP address from the HTTP request.

    The extraction strategy depends on operator-configured proxy trust (see the
    module docstring). Port suffixes are stripped from all extracted IPs (both
    IPv4 and IPv6).

    Args:
        request: The incoming Django HTTP request.

    Returns:
        The client IP address as a string. Returns an empty string only if
        no IP could be determined at all (should not happen in practice).
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")

    # Direct exposure: forwarding headers are attacker-controlled, so the only
    # trustworthy source is the socket peer.
    if not getattr(settings, "TRUST_PROXY_HEADERS", True):
        return _strip_port(remote_addr)

    proxy_count = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    if proxy_count > 0:
        ip = _client_ip_behind_trusted_proxies(request, proxy_count)
        return ip or _strip_port(remote_addr)

    # Unknown topology: permissive legacy behaviour (spoofable — see the
    # TRUSTED_PROXY_COUNT startup warning).
    return _client_ip_permissive(request) or _strip_port(remote_addr)


def _custom_header_ip(request: HttpRequest) -> str:
    """Return the IP from the operator-configured ``CLIENT_IP_HEADER``, or ``""``.

    Honouring this is safe even in hardened mode: the operator has *explicitly*
    named the header their edge sets, asserting it is trustworthy. A generic
    proxy would not populate an arbitrary named header.
    """
    custom = getattr(settings, "CLIENT_IP_HEADER", "")
    if custom:
        meta_key = f"HTTP_{custom.upper().replace('-', '_')}"
        val = request.META.get(meta_key, "").strip()
        if val:
            return _strip_port(val)
    return ""


def _cdn_header_ip(request: HttpRequest) -> str:
    """Return the IP from a known CDN single-valued header, or ``""``.

    These are *guessed* (not operator-asserted): a real CDN overwrites them, but
    a generic reverse proxy forwards a client-supplied value unchanged. They are
    therefore only used in the permissive (best-effort) path, never in hardened
    proxy-count mode where they would reintroduce spoofing.
    """
    for header in _HEADER_CHAIN:
        val = request.META.get(header, "").strip()
        if val:
            return _strip_port(val)
    return ""


def _client_ip_behind_trusted_proxies(request: HttpRequest, proxy_count: int) -> str:
    """Spoof-resistant client IP for a known ``proxy_count``-hop topology.

    Only an *explicitly-configured* edge header (``CLIENT_IP_HEADER``) is honoured
    first — the generic CDN-header guesses are deliberately NOT trusted here,
    since a generic forwarding proxy would relay a client-supplied
    ``CF-Connecting-IP``/``X-Real-IP`` unchanged. Otherwise the client is read
    from the right of X-Forwarded-For: each trusted proxy appends the address it
    *observed*, so the entry ``proxy_count`` positions from the right was written
    by the outermost trusted hop (the one that saw the real client). Anything an
    upstream client prepends only lengthens the chain on the left and cannot
    reach that position.
    """
    ip = _custom_header_ip(request)
    if ip:
        return ip
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    entries = [p.strip() for p in xff.split(",") if p.strip()]
    if len(entries) >= proxy_count:
        return _strip_port(entries[-proxy_count])
    return ""


def _client_ip_permissive(request: HttpRequest) -> str:
    """Legacy permissive extraction (custom/CDN headers, then leftmost XFF)."""
    ip = _custom_header_ip(request) or _cdn_header_ip(request)
    if ip:
        return ip

    # X-Forwarded-For: take the first (leftmost) IP in the chain.
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return _strip_port(first)

    # RFC 7239 Forwarded header: extract the "for=" directive.
    forwarded = request.META.get("HTTP_FORWARDED", "")
    if forwarded:
        for part in forwarded.split(";"):
            part = part.strip()
            if part.lower().startswith("for="):
                ip = part[4:].strip().strip('"')
                return _strip_port(ip)

    # Non-standard X-Forwarded header.
    x_forwarded = request.META.get("HTTP_X_FORWARDED", "")
    if x_forwarded:
        first = x_forwarded.split(",")[0].strip()
        if first:
            return _strip_port(first)

    # Final fallback: X-Client-IP or the raw socket REMOTE_ADDR.
    return request.META.get("HTTP_X_CLIENT_IP", "") or request.META.get("REMOTE_ADDR", "")


def truncate_ip(ip: str, ipv4_prefix: int = 24, ipv6_prefix: int = 48) -> str:
    """Mask the host bits of an IP, keeping only the given network prefix.

    Used to coarsen the IP **before** it feeds the cookieless visitor digest, so a
    longer-lived salt cannot turn the digest into a precise device fingerprint.
    CNIL requires truncating the last IPv4 byte (``/24``) and the Italian Garante
    expects at least the 4th octet masked for the consent-exempt audience-measurement
    basis; an analogous prefix (default ``/48``) is applied to IPv6.

    ``ipv4_prefix >= 32`` / ``ipv6_prefix >= 128`` mean "no truncation" (full IP).
    Non-IP strings are returned unchanged (defensive — input is post-``_strip_port``).

    Args:
        ip: A bare IPv4/IPv6 address string (no port).
        ipv4_prefix: Network prefix length to keep for IPv4 (0–32).
        ipv6_prefix: Network prefix length to keep for IPv6 (0–128).

    Returns:
        The network address of the truncated range, as a string.
    """
    if not ip:
        return ip
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 4:
        if ipv4_prefix >= 32:
            return str(addr)
        prefix = max(0, ipv4_prefix)
    else:
        if ipv6_prefix >= 128:
            return str(addr)
        prefix = max(0, ipv6_prefix)
    network = ipaddress.ip_network(f"{addr}/{prefix}", strict=False)
    return str(network.network_address)


def _strip_port(ip: str) -> str:
    """Remove port suffix from an IP address string.

    Handles both IPv4 (``"1.2.3.4:8080"`` -> ``"1.2.3.4"``) and bracketed
    IPv6 (``"[::1]:8080"`` -> ``"::1"``) formats. Bare IPv6 addresses
    without brackets are returned as-is.

    Args:
        ip: The IP address string, potentially including a port suffix.

    Returns:
        The IP address without any port component.
    """
    m = _IP_PORT_RE.match(ip)
    if m:
        return m.group(1)
    m = _IPV6_BRACKET_RE.match(ip)
    if m:
        return m.group(1)
    return ip
