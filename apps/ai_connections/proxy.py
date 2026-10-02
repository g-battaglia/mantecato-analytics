"""Narrow HTTPS scheme adaptation for MCP behind an explicitly trusted proxy.

Gunicorn 26's native ASGI parser reports socket TLS, not forwarded scheme headers.
Do not apply this adapter to Django/collector paths or rewrite the peer identity.
"""

import ipaddress
import logging
import os


class TrustedProxyScheme:
    def __init__(self, allowed_peers):
        entries = [entry.strip() for entry in allowed_peers.split(",") if entry.strip()]
        self.trust_all = False
        self.networks = ()
        try:
            networks = tuple(
                ipaddress.ip_network(entry, strict=False) for entry in entries if entry != "*"
            )
        except ValueError:
            logging.getLogger("mantecato.security").warning(
                "Invalid FORWARDED_ALLOW_IPS: MCP will not trust forwarded scheme headers."
            )
        else:
            self.trust_all = "*" in entries
            self.networks = networks

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1,::1"))

    def __call__(self, scope):
        if scope.get("type") != "http" or scope.get("scheme") != "http":
            return scope
        try:
            peer = ipaddress.ip_address(scope["client"][0])
        except (KeyError, IndexError, TypeError, ValueError):
            return scope
        if not self.trust_all and not any(peer in network for network in self.networks):
            return scope
        values = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"x-forwarded-proto"
        ]
        # A single, exact value only: duplicate/chained/ambiguous headers fail
        # closed. Host, client IP and all other headers remain untouched.
        if values != [b"https"]:
            return scope
        return {**scope, "scheme": "https"}
