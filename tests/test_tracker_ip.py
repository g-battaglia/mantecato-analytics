"""Unit tests for client-IP extraction (apps.tracker.ip.get_client_ip).

The client IP feeds the cookieless visitor digest, datacenter-bot detection and
the ingest rate-limit key, so spoof-resistance in the configured (hardened)
proxy mode is security-relevant.
"""

from __future__ import annotations

from django.test import RequestFactory, override_settings

from apps.tracker.ip import get_client_ip

_RF = RequestFactory()  # default REMOTE_ADDR = "127.0.0.1"


@override_settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_COUNT=0, CLIENT_IP_HEADER="")
def test_permissive_default_takes_leftmost_xff() -> None:
    req = _RF.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 10.0.0.1")
    assert get_client_ip(req) == "1.2.3.4"


@override_settings(TRUST_PROXY_HEADERS=False, TRUSTED_PROXY_COUNT=0, CLIENT_IP_HEADER="")
def test_direct_exposure_ignores_forwarding_headers() -> None:
    req = _RF.get(
        "/",
        HTTP_X_FORWARDED_FOR="1.2.3.4",
        HTTP_CF_CONNECTING_IP="6.6.6.6",
        REMOTE_ADDR="203.0.113.9",
    )
    assert get_client_ip(req) == "203.0.113.9"


@override_settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_COUNT=1, CLIENT_IP_HEADER="")
def test_trusted_one_hop_reads_rightmost_xff() -> None:
    # Client spoofs the leftmost entry; the single trusted proxy appends the
    # address it actually observed (rightmost), which is the real client.
    req = _RF.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 9.9.9.9")
    assert get_client_ip(req) == "9.9.9.9"


@override_settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_COUNT=2, CLIENT_IP_HEADER="")
def test_trusted_two_hops_reads_second_from_right() -> None:
    req = _RF.get("/", HTTP_X_FORWARDED_FOR="spoofed, 9.9.9.9, 10.0.0.1")
    assert get_client_ip(req) == "9.9.9.9"


@override_settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_COUNT=1, CLIENT_IP_HEADER="")
def test_trusted_mode_ignores_spoofable_cdn_header() -> None:
    # A generic forwarding proxy relays a client-supplied CF-Connecting-IP
    # unchanged. In hardened mode (no explicit CLIENT_IP_HEADER) it must be
    # ignored in favour of the spoof-resistant right-of-XFF value.
    req = _RF.get(
        "/",
        HTTP_CF_CONNECTING_IP="6.6.6.6",
        HTTP_X_FORWARDED_FOR="1.1.1.1, 9.9.9.9",
    )
    assert get_client_ip(req) == "9.9.9.9"


@override_settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_COUNT=1, CLIENT_IP_HEADER="X-Real-IP")
def test_trusted_mode_honours_explicitly_configured_header() -> None:
    # The operator explicitly named the header their edge sets → trustworthy.
    req = _RF.get(
        "/",
        HTTP_X_REAL_IP="9.9.9.9",
        HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2",
    )
    assert get_client_ip(req) == "9.9.9.9"


@override_settings(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_COUNT=3, CLIENT_IP_HEADER="")
def test_trusted_mode_short_chain_falls_back_to_remote_addr() -> None:
    # Fewer entries than configured hops → don't trust XFF, use the socket peer.
    req = _RF.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1", REMOTE_ADDR="203.0.113.9")
    assert get_client_ip(req) == "203.0.113.9"
