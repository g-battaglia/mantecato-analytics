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
        {"id": "a", "type": "kpi", "metric": "visitors"},
        {"id": "b", "type": "breakdown", "source": "sections", "depth": 1},
        {"id": "c", "type": "timeseries"},
    ]}
    assert validate_dashboard_config(cfg) == []


def test_validate_catches_bad_widgets():
    errs = validate_dashboard_config({"widgets": [
        {"id": "a", "type": "nope"},
        {"id": "b", "type": "kpi", "metric": "bad"},
        {"id": "c", "type": "breakdown", "source": "zzz"},
        {"id": "d", "type": "kpi", "metric": "visitors", "filters": ["x:y"]},
    ]})
    assert len(errs) >= 4


def test_validate_requires_unique_widget_ids():
    missing = validate_dashboard_config({"widgets": [{"type": "kpi", "metric": "visitors"}]})
    assert any("id" in e for e in missing)
    dup = validate_dashboard_config({"widgets": [
        {"id": "x", "type": "kpi", "metric": "visitors"},
        {"id": "x", "type": "timeseries"},
    ]})
    assert any("duplicate" in e for e in dup)


def test_validate_rejects_url_unsafe_id():
    # An id with '/' would 500 the detail page (NoReverseMatch on <str:widget_id>).
    errs = validate_dashboard_config({"widgets": [{"id": "a/b", "type": "timeseries"}]})
    assert any("url-safe" in e for e in errs)


def test_validate_survives_non_string_fields():
    # Unhashable JSON values in membership-checked fields must yield errors, not
    # a TypeError (which would 500 create/update).
    errs = validate_dashboard_config(
        {"dateRange": [], "widgets": [{"id": "x", "type": [], "metric": {}}]}
    )
    assert errs


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


def test_runtime_positive_filter_cannot_relax_saved_scope(seeded):
    from core.mantecato_core.filters import Filter

    w = render_widget(
        WEBSITE_ID,
        {"filters": ["url_path:starts_with:/pro/"]},
        {"id": "w", "type": "breakdown", "source": "sections", "depth": 1},
        runtime_range=_range(),
        runtime_filters=[Filter(column="url_path", operator="starts_with", value="/free/")],
    )
    labels = [r["label"] for r in w["rows"]]
    assert "/pro" in labels
    assert "/free" not in labels  # widening runtime url_path dropped — scope wins


def test_runtime_negative_filter_narrows_scoped_column(seeded):
    # A negated runtime filter on a scoped column must survive (it AND-narrows).
    from core.mantecato_core.filters import Filter

    _ev("/pro/keep")
    w = render_widget(
        WEBSITE_ID,
        {"filters": ["url_path:starts_with:/pro/"]},
        {"id": "w", "type": "breakdown", "source": "pages"},
        runtime_range=_range(),
        runtime_filters=[Filter(column="url_path", operator="not_contains", value="/chart/")],
    )
    labels = [r["label"] for r in w["rows"]]
    assert "/pro/keep" in labels
    assert not any("/chart/" in lbl for lbl in labels)  # narrowing runtime kept


def test_stacked_negation_filters_exclude_both(seeded):
    # Regression: same-column negations must AND (exclude both), not OR (tautology).
    _ev("/pro/keep")
    w = render_widget(
        WEBSITE_ID,
        {"filters": ["url_path:neq:/pro/chart/natal", "url_path:not_contains:/free/"]},
        {"id": "p", "type": "breakdown", "source": "pages"},
        runtime_range=_range(),
    )
    labels = [r["label"] for r in w["rows"]]
    assert "/pro/keep" in labels
    assert "/pro/chart/natal" not in labels  # excluded by neq
    assert not any("/free/" in lbl for lbl in labels)  # excluded by not_contains


def test_validate_rejects_out_of_range_depth():
    errs = validate_dashboard_config(
        {"widgets": [{"id": "s", "type": "breakdown", "source": "sections", "depth": 999999}]}
    )
    assert any("depth" in e for e in errs)


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


def test_timeseries_respects_runtime_granularity(seeded):
    # Threading the filter-bar granularity through must not break rendering.
    w = render_widget(
        WEBSITE_ID, {}, {"id": "t", "type": "timeseries"},
        runtime_range=_range(), runtime_granularity="day",
    )
    assert "error" not in w and "labels" in w["chart"]


def test_sources_breakdown_uses_real_keys(seeded):
    # Regression: the "sources" mapping used non-existent keys → every row "—"/0.
    _ev("/pro/x", referrer_domain="google.com")
    _ev("/pro/x", referrer_domain="google.com")
    w = render_widget(
        WEBSITE_ID, {}, {"id": "s", "type": "breakdown", "source": "sources"}, runtime_range=_range()
    )
    assert "error" not in w
    assert w["rows"], "expected referrer rows"
    assert all(r["label"] != "—" for r in w["rows"])
    assert any(r["value"] > 0 for r in w["rows"])


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


def test_heatmap_widget_renders_with_day_labels(authenticated_client, seeded):
    dashboard = create_new_dashboard(
        ADMIN_USER_ID, WEBSITE_ID, "HM",
        config={"version": 2, "widgets": [{"id": "hm", "type": "heatmap", "grid": {"w": 12}}]},
    )
    did = dashboard["id"]
    r = authenticated_client.get(f"/dashboards/{did}/widget/hm/?range=30d")
    assert r.status_code == 200
    assert b"Sun" in r.content and b"Sat" in r.content  # DOW labels (0=Sun) render


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


def test_create_blank_config_applies_default_scaffold(authenticated_client, db):
    from apps.core.models import Website
    from apps.dashboards.services import get_dashboards_for_user

    Website.objects.create(id=WEBSITE_ID, user_id=ADMIN_USER_ID, name="S", is_deleted=False)
    authenticated_client.post(
        "/dashboards/create/",
        data={"name": "Scaffold", "description": "", "website_id": WEBSITE_ID, "config": ""},
    )
    cfg = get_dashboards_for_user(ADMIN_USER_ID)[0]["config"]
    # Blank config must persist the v2 default scaffold, not an empty {}.
    assert cfg.get("version") == 2 and "widgets" in cfg


def test_dashboard_list_links_to_detail(authenticated_client, db):
    from apps.core.models import Website

    Website.objects.create(id=WEBSITE_ID, user_id=ADMIN_USER_ID, name="S", is_deleted=False)
    dashboard = create_new_dashboard(ADMIN_USER_ID, WEBSITE_ID, "Openable", config={"version": 2})
    resp = authenticated_client.get("/dashboards/")
    assert resp.status_code == 200
    # The list must link each dashboard to its rendered detail view (name + Open).
    assert f"/dashboards/{dashboard['id']}/".encode() in resp.content


def test_api_rejects_invalid_config(api_auth, client):
    from tests.conftest import API_TOKEN

    resp = client.post(
        "/api/dashboards/create/",
        data={"name": "X", "website_id": WEBSITE_ID, "config": {"widgets": [{"type": "bogus"}]}},
        content_type="application/json",
        HTTP_AUTHORIZATION=API_TOKEN,
    )
    assert resp.status_code == 400
