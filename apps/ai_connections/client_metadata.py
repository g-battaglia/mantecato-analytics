"""Client metadata fetches pin public DNS results, without changing TLS identity."""

import ipaddress
import json
import time
from urllib.parse import urlsplit

import dns.exception
import dns.resolver
import httpcore

from apps.ai_connections.policy import AccessDenied, validate_redirect


def registration(data, metadata=False):
    if not isinstance(data, dict):
        raise AccessDenied("invalid_client_metadata")
    name, redirects = data.get("client_name"), data.get("redirect_uris")
    grants = data.get("grant_types", ["authorization_code", "refresh_token"])
    responses = data.get("response_types", ["code"])
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 120
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
        or not isinstance(redirects, list)
        or not 1 <= len(redirects) <= 20
        or not isinstance(grants, list)
        or not isinstance(responses, list)
        or any(not isinstance(v, str) for v in grants + responses)
        or "authorization_code" not in grants
        or "code" not in responses
        or data.get("token_endpoint_auth_method", "none") != "none"
        or (
            not metadata
            and (set(grants) - {"authorization_code", "refresh_token"} or responses != ["code"])
        )
    ):
        raise AccessDenied("invalid_client_metadata")
    return name.strip(), sorted({validate_redirect(x) for x in redirects})


class PinnedBackend(httpcore.NetworkBackend):
    def __init__(self, host, port, addresses):
        self.host, self.port, self.addresses = host, port, addresses
        self.backend = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != self.host or port != self.port:
            raise AccessDenied("invalid_client_metadata")
        # The pool retains the original URL: start_tls still validates its hostname.
        return self.backend.connect_tcp(
            self.addresses[0],
            port,
            timeout,
            local_address,
            socket_options,
        )

    def connect_unix_socket(self, *args, **kwargs):
        raise AccessDenied("invalid_client_metadata")

    def sleep(self, seconds):
        return self.backend.sleep(seconds)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def public_addresses(host):
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    resolver = dns.resolver.Resolver()
    deadline = time.monotonic() + 3
    addresses = []
    for record_type in ("A", "AAAA"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AccessDenied("invalid_client_metadata")
        try:
            answer = resolver.resolve(host, record_type, search=False, lifetime=remaining)
            addresses.extend(str(record) for record in answer)
        except dns.resolver.NoAnswer:
            continue
    return sorted(set(addresses))


def fetch_metadata(url):
    """No redirects, proxies, unbounded buffers, or DNS lookup after validation."""
    try:
        deadline = time.monotonic() + 6
        if len(url) > 2048 or any(c.isspace() or c == "\\" for c in url):
            raise ValueError()
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.path
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
        ):
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or 443
        addresses = public_addresses(host)
        if not addresses:
            raise ValueError()
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                not ip.is_global
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_loopback
                or ip.is_link_local
            ):
                raise ValueError()
        backend = PinnedBackend(host, port, addresses)
        with (
            httpcore.ConnectionPool(network_backend=backend, retries=0) as pool,
            pool.stream(
                "GET",
                url,
                headers={"Accept": "application/json"},
                extensions={"timeout": {"connect": 3, "read": 3, "write": 3, "pool": 3}},
            ) as response,
        ):
            if response.status != 200:
                raise ValueError()
            response_headers = {key.lower(): value for key, value in response.headers}
            content_type = response_headers.get(b"content-type", b"").lower()
            if content_type.split(b";", 1)[0].strip() != b"application/json":
                raise ValueError()
            body = bytearray()
            for chunk in response.iter_stream():
                if time.monotonic() >= deadline:
                    raise ValueError()
                body.extend(chunk)
                if len(body) > 16_384:
                    raise ValueError()
        document = json.loads(body, object_pairs_hook=_unique_pairs)
        if not isinstance(document, dict) or document.get("client_id") != url:
            raise ValueError()
        return registration(document, metadata=True)
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        dns.exception.DNSException,
        httpcore.NetworkError,
        httpcore.ProtocolError,
        httpcore.TimeoutException,
    ):
        raise AccessDenied("invalid_client_metadata") from None
