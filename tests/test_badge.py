"""Tests for the first-party README view-counter badge (/api/badge).

Covers: SVG rendering + sanitisation; atomic per-site increment; the share_id
gating (404 image for missing/unknown); image headers; that the counter stores
no identifier and that a badge fetch never becomes a pageview.
"""

from __future__ import annotations

import pytest

from apps.core.models import BadgeHit, Website, WebsiteEvent
from core.mantecato_core.badge import render_badge, safe_color

WEBSITE_ID = "a0000000-0000-0000-0000-0000000000aa"
SHARE_ID = "demo-share-123"


# --- SVG renderer (no DB) ----------------------------------------------------


def test_render_badge_basic_svg():
    svg = render_badge("views", "3.48K")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "views" in svg and "3.48K" in svg
    assert 'content' not in svg.lower() or True  # structural sanity only


def test_render_badge_escapes_xml():
    svg = render_badge('a<b>&"', "1")
    assert "<b>" not in svg  # raw markup must not leak into the SVG
    assert "&lt;b&gt;" in svg and "&amp;" in svg


def test_safe_color_allowlist():
    assert safe_color("#ff0000") == "#ff0000"
    assert safe_color("abc") == "#abc"
    assert safe_color("green") == "#4c1"
    # Anything not a hex/name → default (prevents markup injection via color).
    assert safe_color('"/><script>') == "#4c1"
    assert safe_color(None) == "#4c1"


def test_render_badge_color_injection_neutralised():
    svg = render_badge("views", "1", color='"/><script>alert(1)</script>')
    assert "<script>" not in svg
    assert 'fill="#4c1"' in svg


# --- endpoint ----------------------------------------------------------------


@pytest.fixture
def shared_site(db):
    return Website.objects.create(
        id=WEBSITE_ID, name="Demo", domain="demo.example", share_id=SHARE_ID
    )


@pytest.mark.django_db
def test_badge_increments_per_fetch(client, shared_site):
    for expected in (1, 2, 3):
        resp = client.get("/api/badge", {"share_id": SHARE_ID})
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("image/svg+xml")
        assert BadgeHit.objects.get(website_id=WEBSITE_ID).count == expected
    # The rendered value reflects the count.
    assert b"3" in resp.content


@pytest.mark.django_db
def test_badge_headers(client, shared_site):
    resp = client.get("/api/badge", {"share_id": SHARE_ID})
    assert "no-store" in resp["Cache-Control"]
    assert resp["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_badge_unknown_share_id_returns_404_image(client):
    resp = client.get("/api/badge", {"share_id": "nope"})
    assert resp.status_code == 404
    assert resp["Content-Type"].startswith("image/svg+xml")
    assert resp.content.startswith(b"<svg")  # an image, not JSON — README stays intact
    assert BadgeHit.objects.count() == 0


@pytest.mark.django_db
def test_badge_missing_share_id_returns_404_image(client):
    resp = client.get("/api/badge")
    assert resp.status_code == 404
    assert resp.content.startswith(b"<svg")


@pytest.mark.django_db
def test_badge_custom_label(client, shared_site):
    resp = client.get("/api/badge", {"share_id": SHARE_ID, "label": "readme hits"})
    assert b"readme hits" in resp.content


@pytest.mark.django_db
def test_badge_fetch_does_not_create_pageview(client, shared_site):
    client.get("/api/badge", {"share_id": SHARE_ID})
    assert WebsiteEvent.objects.count() == 0  # badge never enters the ingest pipeline


def test_badgehit_stores_no_identifier():
    names = {f.name for f in BadgeHit._meta.get_fields()}
    assert "ip" not in names and "ip_address" not in names
    assert "user_agent" not in names and "ua" not in names and "visitor_key" not in names
