"""Custom-dashboard widget engine + render views."""

from __future__ import annotations

import pytest

from apps.core.models import Website, WebsiteEvent
from apps.dashboards.services import create_new_dashboard
from apps.dashboards.widgets import render_widget, validate_dashboard_config
from core.mantecato_core.date_utils import resolve_date_range
from tests.conftest import ADMIN_USER_ID, WEBSITE_ID


def _ev(url_path: str, **fields: object) -> WebsiteEvent:
    defaults = {
        "website_id": WEBSITE_ID,
        "url_path": url_path,
        "event_type": 1,
        "browser": "Chrome",
        "os": "Mac OS X",
        "device": "desktop",
        "country": "US",
        "is_bot": False,
    }
    defaults.update(fields)
    return WebsiteEvent.objects.create(**defaults)


@pytest.fixture
def seeded(db) -> None:
    Website.objects.create(
        id=WEBSITE_ID, user_id=ADMIN_USER_ID, name="Site", domain="x.com", is_deleted=False
    )
    for _ in range(5):
        _ev("/pro/chart/natal")
    for _ in range(3):
        _ev("/free/chart/natal")
    _ev("/pro/chart/natal", event_type=2, event_name="ai-generate-success")


def _range():
    return resolve_date_range("30d")


# ── Validation ───────────────────────────────────────────────────────────────


def test_validate_ok():
    cfg = {"version": 2, "filters": ["url_path:starts_with:/pro/"], "widgets": [
        {"type": "kpi", "metric": "visitors"},
        {"type": "breakdown", "source": "sections", "depth": 1},
        {"type": "timeseries"},
    ]}
    assert validate_dashboard_config(cfg) == []


def test_validate_catches_bad_widgets():
    errs = validate_dashboard_config({"widgets": [
        {"type": "nope"},
        {"type": "kpi", "metric": "bad"},
        {"type": "breakdown", "source": "zzz"},
        {"type": "kpi", "metric": "visitors", "filters": ["x:y"]},
    ]})
    assert len(errs) >= 4


# ── Dispatcher ───────────────────────────────────────────────────────────────


def test_kpi_widget(seeded):
    w = render_widget(WEBSITE_ID, {}, {"id": "w1", "type": "kpi", "metric": "pageviews"}, runtime_range=_range())
    assert "error" not in w and w["kind"] == "kpi"
    assert w["stat"] is not None


def test_breakdown_sections_groups_by_tier(seeded):
    w = render_widget(
        WEBSITE_ID, {}, {"id": "w2", "type": "breakdown", "source": "sections", "depth": 1},
        runtime_range=_range(),
    )
    assert "error" not in w
    labels = [r["label"] for r in w["rows"]]
    assert "/pro" in labels and "/free" in labels


def test_dashboard_filter_cascades_to_widget(seeded):
    w = render_widget(
        WEBSITE_ID,
        {"filters": ["url_path:starts_with:/pro/"]},
        {"id": "w3", "type": "breakdown", "source": "sections", "depth": 1},
        runtime_range=_range(),
    )
    labels = [r["label"] for r in w["rows"]]
    assert "/pro" in labels
    assert "/free" not in labels


def test_widget_filter_event(seeded):
    w = render_widget(
        WEBSITE_ID, {}, {"id": "w5", "type": "breakdown", "source": "events"}, runtime_range=_range()
    )
    labels = [r["label"] for r in w["rows"]]
    assert "ai-generate-success" in labels


def test_timeseries_widget(seeded):
    w = render_widget(WEBSITE_ID, {}, {"id": "w4", "type": "timeseries"}, runtime_range=_range())
    assert "error" not in w and w["kind"] == "timeseries"
    assert "labels" in w["chart"]


def test_unknown_widget_returns_error(seeded):
    w = render_widget(WEBSITE_ID, {}, {"id": "x", "type": "frobnicate"}, runtime_range=_range())
    assert "error" in w


# ── Views ────────────────────────────────────────────────────────────────────


def test_detail_and_widget_views(authenticated_client, seeded):
    dashboard = create_new_dashboard(
        ADMIN_USER_ID, WEBSITE_ID, "Pro Cohort",
        config={
            "version": 2, "dateRange": "30d", "filters": ["url_path:starts_with:/pro/"],
            "widgets": [
                {"id": "k1", "type": "kpi", "metric": "pageviews", "grid": {"w": 3}},
                {"id": "b1", "type": "breakdown", "source": "sections", "depth": 1, "grid": {"w": 6}},
            ],
        },
    )
    did = dashboard["id"]

    detail = authenticated_client.get(f"/dashboards/{did}/")
    assert detail.status_code == 200
    assert b"hx-get" in detail.content  # widgets lazy-load via HTMX

    widget = authenticated_client.get(f"/dashboards/{did}/widget/b1/?range=30d")
    assert widget.status_code == 200
    assert b"/pro" in widget.content  # tier section rendered, scoped by the dashboard filter
    assert b"/free" not in widget.content


def test_builder_page_and_preview(authenticated_client, seeded):
    import json as _json

    dashboard = create_new_dashboard(ADMIN_USER_ID, WEBSITE_ID, "Builder", config={"version": 2})
    did = dashboard["id"]

    # The edit route renders the visual builder (Gridstack + builder JS).
    builder = authenticated_client.get(f"/dashboards/{did}/edit/")
    assert builder.status_code == 200
    assert b"grid-stack" in builder.content
    assert b"dashboard_builder.js" in builder.content

    # Live preview of an unsaved widget config.
    preview = authenticated_client.post(
        f"/dashboards/{did}/preview-widget/",
        data=_json.dumps({
            "widget": {"id": "tmp", "type": "breakdown", "source": "sections", "depth": 1},
            "dashboardFilters": ["url_path:starts_with:/pro/"],
            "dashboardDateRange": "30d",
        }),
        content_type="application/json",
    )
    assert preview.status_code == 200
    assert b"/pro" in preview.content
    assert b"/free" not in preview.content


def test_create_redirects_to_builder(authenticated_client, db):
    from apps.core.models import Website

    Website.objects.create(id=WEBSITE_ID, user_id=ADMIN_USER_ID, name="S", is_deleted=False)
    resp = authenticated_client.post(
        "/dashboards/create/",
        data={"name": "New", "description": "", "website_id": WEBSITE_ID, "config": ""},
    )
    assert resp.status_code == 302
    assert "/edit/" in resp.headers["Location"]


def test_api_rejects_invalid_config(api_auth, client):
    from tests.conftest import API_TOKEN

    resp = client.post(
        "/api/dashboards/create/",
        data={"name": "X", "website_id": WEBSITE_ID, "config": {"widgets": [{"type": "bogus"}]}},
        content_type="application/json",
        HTTP_AUTHORIZATION=API_TOKEN,
    )
    assert resp.status_code == 400
