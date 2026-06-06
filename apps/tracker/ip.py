"""Extract the real client IP from HTTP request headers.

Checks headers in priority order matching Umami's behaviour: custom header,
CDN-specific headers, standard proxy headers, then REMOTE_ADDR fallback.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

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
    """Extract the real client IP address from the HTTP request.

    Checks headers in a carefully ordered priority chain that matches
    Umami's behaviour. The priority is:

    1. **Custom header** -- operator-configured via the ``CLIENT_IP_HEADER``
       environment variable (e.g. for non-standard proxy setups).
    2. **CDN/proxy-specific headers** -- single-valued headers set by known
       edge proxies (Cloudflare, Fastly, etc.). These are trusted because
       they are set by the infrastructure, not by upstream clients.
    3. **X-Forwarded-For** -- the first (leftmost) IP, which is the
       original client in a compliant proxy chain.
    4. **Forwarded** (RFC 7239) -- the ``for=`` directive.
    5. **X-Forwarded** -- non-standard variant of X-Forwarded-For.
    6. **X-Client-IP / REMOTE_ADDR** -- final fallback.

    Port suffixes are stripped from all extracted IPs (both IPv4 and IPv6).

    Args:
        request: The incoming Django HTTP request.

    Returns:
        The client IP address as a string. Returns an empty string only if
        no IP could be determined at all (should not happen in practice).
    """
    # 1. Check operator-configured custom header
    custom = os.environ.get("CLIENT_IP_HEADER", "").strip()
    if custom:
        meta_key = f"HTTP_{custom.upper().replace('-', '_')}"
        val = request.META.get(meta_key, "").strip()
        if val:
            return _strip_port(val)

    # 2. Check CDN/proxy-specific single-valued headers
    for header in _HEADER_CHAIN:
        val = request.META.get(header, "").strip()
        if val:
            return _strip_port(val)

    # 3. X-Forwarded-For: take the first (leftmost) IP in the chain
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return _strip_port(first)

    # 4. RFC 7239 Forwarded header: extract the "for=" directive
    forwarded = request.META.get("HTTP_FORWARDED", "")
    if forwarded:
        for part in forwarded.split(";"):
            part = part.strip()
            if part.lower().startswith("for="):
                ip = part[4:].strip().strip('"')
                return _strip_port(ip)

    # 5. Non-standard X-Forwarded header
    x_forwarded = request.META.get("HTTP_X_FORWARDED", "")
    if x_forwarded:
        first = x_forwarded.split(",")[0].strip()
        if first:
            return _strip_port(first)

    # 6. Final fallback: X-Client-IP or the raw socket REMOTE_ADDR
    return request.META.get("HTTP_X_CLIENT_IP", "") or request.META.get("REMOTE_ADDR", "")


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
