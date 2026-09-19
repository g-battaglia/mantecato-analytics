"""Contract and HTTP tests for the additive API v1."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from apps.api.v1.contracts import ContractError, parse_compare, parse_query
from apps.api.v1.queries.analytics import _aggregate_sql
from apps.api.v1.services import _limit_rows
from apps.core.models import Website, WebsiteEvent

_USER_ID = "a0000000-0000-0000-0000-000000000001"
_WEBSITE_ID = "b0000000-0000-0000-0000-000000000002"
_AUTH = {"HTTP_AUTHORIZATION": "Bearer mtk_test_token_1234567890"}


@pytest.fixture
def client() -> Client:
    return Client()


def test_explicit_dates_are_half_open_and_utc() -> None:
    spec = parse_query(
        {
            "website_id": _WEBSITE_ID,
            "operation": "timeseries",
            "start": "2026-03-28",
            "end": "2026-03-30",
            "timezone": "Europe/Rome",
            "granularity": "day",
        },
        now=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert spec.date_range.start.isoformat() == "2026-03-27T23:00:00+00:00"
    assert spec.date_range.end.isoformat() == "2026-03-29T22:00:00+00:00"


def test_open_calendar_range_is_marked_partial() -> None:
    spec = parse_query(
        {
            "website_id": _WEBSITE_ID,
            "operation": "timeseries",
            "range": "today",
            "granularity": "day",
        },
        now=datetime(2026, 6, 6, 10, 53, tzinfo=UTC),
    )
    assert spec.date_range.partial is True
    assert spec.date_range.end == datetime(2026, 6, 6, 10, 53, tzinfo=UTC)


def test_unknown_request_field_is_rejected() -> None:
    with pytest.raises(ContractError) as exc:
        parse_query({"website_id": _WEBSITE_ID, "granularty": "day"})
    assert exc.value.field == "granularty"


def test_invalid_website_uuid_is_rejected_before_database_access() -> None:
    with pytest.raises(ContractError) as exc:
        parse_query({"website_id": "not-a-uuid"})
    assert exc.value.field == "website_id"


def test_invalid_filter_is_rejected_instead_of_dropped() -> None:
    with pytest.raises(ContractError) as exc:
        parse_query({"website_id": _WEBSITE_ID, "filters": ["country:IT"]})
    assert exc.value.code == "INVALID_FILTER"


def test_segment_style_filter_groups_remain_separate() -> None:
    spec = parse_query(
        {
            "website_id": _WEBSITE_ID,
            "filters": ["country:in:US,GB"],
            "filter_groups": [["country:eq:US"]],
        }
    )
    assert len(spec.filter_groups) == 2


def test_dimensioned_timeseries_limit_applies_to_series_not_rows() -> None:
    spec = parse_query(
        {
            "website_id": _WEBSITE_ID,
            "operation": "timeseries",
            "granularity": "day",
            "dimensions": ["country"],
            "metrics": ["pageviews"],
            "limit": 1,
        }
    )
    rows = [
        {"time": "2026-01-01", "country": "US", "pageviews": 10},
        {"time": "2026-01-01", "country": "GB", "pageviews": 2},
        {"time": "2026-01-02", "country": "US", "pageviews": 8},
        {"time": "2026-01-02", "country": "GB", "pageviews": 1},
    ]
    selected, truncated = _limit_rows(spec, rows)
    assert truncated is True
    assert len(selected) == 2
    assert {row["country"] for row in selected} == {"US"}


def test_generated_sql_uses_half_open_bounds_and_safe_identifiers() -> None:
    spec = parse_query(
        {
            "website_id": _WEBSITE_ID,
            "operation": "timeseries",
            "dimensions": ["country"],
            "granularity": "day",
        }
    )
    sql, _params = _aggregate_sql(spec, hard_limit=10)
    assert "we.created_at >= %s::timestamptz" in sql
    assert "we.created_at < %s::timestamptz" in sql
    assert '""country""' not in sql
    assert "INSERT" not in sql and "UPDATE" not in sql and "DELETE" not in sql


def test_zero_baseline_is_not_coerced_by_contract() -> None:
    spec = parse_compare(
        {
            "website_id": _WEBSITE_ID,
            "dimension": "country",
            "dimensions": ["country"],
            "metric": "pageviews",
            "start": "2026-01-02",
            "end": "2026-01-03",
            "previous_start": "2026-01-01",
            "previous_end": "2026-01-02",
        },
        now=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert spec.previous.end == spec.query.date_range.start


def test_capabilities_requires_auth(client: Client) -> None:
    response = client.get("/api/v1/capabilities/")
    assert response.status_code == 401


@patch("mantecato.middleware.validate_api_key")
def test_capabilities_are_machine_readable(mock_validate: MagicMock, client: Client) -> None:
    mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
    response = client.get("/api/v1/capabilities/", **_AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1"
    assert "daily_unique_visitors" in body["metrics"]


@patch("mantecato.middleware.validate_api_key")
def test_invalid_query_returns_structured_400(mock_validate: MagicMock, client: Client) -> None:
    mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
    response = client.post(
        "/api/v1/analytics/query/",
        data=json.dumps({"website_id": _WEBSITE_ID, "filters": ["country:IT"]}),
        content_type="application/json",
        **_AUTH,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


@patch("apps.api.v1.views.analytics_transaction")
@patch("apps.api.v1.views.Website.objects")
@patch("apps.api.v1.views.run_query")
@patch("mantecato.middleware.validate_api_key")
def test_query_checks_site_then_returns_envelope(
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_websites: MagicMock,
    mock_transaction: MagicMock,
    client: Client,
) -> None:
    mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
    mock_websites.filter.return_value.filter.return_value.exists.return_value = True
    mock_run.return_value = {
        "schema_version": "1",
        "query": {},
        "comparison": None,
        "totals": {"pageviews": 0},
        "rows": [],
    }
    response = client.post(
        "/api/v1/analytics/query/",
        data=json.dumps({"website_id": _WEBSITE_ID}),
        content_type="application/json",
        **_AUTH,
    )
    assert response.status_code == 200
    assert response.json()["schema_version"] == "1"


@patch("apps.api.v1.views.analytics_transaction")
@patch("apps.api.v1.views.Website.objects")
@patch("apps.api.v1.views.run_query")
@patch("mantecato.middleware.validate_api_key")
def test_v1_bearer_post_does_not_require_csrf_cookie(
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_websites: MagicMock,
    mock_transaction: MagicMock,
) -> None:
    mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
    mock_websites.filter.return_value.filter.return_value.exists.return_value = True
    mock_run.return_value = {
        "schema_version": "1",
        "query": {},
        "comparison": None,
        "totals": {},
        "rows": [],
    }
    csrf_client = Client(enforce_csrf_checks=True)
    response = csrf_client.post(
        "/api/v1/analytics/query/",
        data=json.dumps({"website_id": _WEBSITE_ID}),
        content_type="application/json",
        **_AUTH,
    )
    assert response.status_code == 200


def _event(
    website_id: object,
    when: datetime,
    *,
    path: str,
    visitor: str,
    country: str,
    groups: list[str] | None = None,
) -> None:
    event = WebsiteEvent.objects.create(
        website_id=website_id,
        url_path=path,
        event_type=1,
        visitor_key=visitor,
        country=country,
        content_groups=groups,
    )
    WebsiteEvent.objects.filter(pk=event.pk).update(created_at=when)


@pytest.mark.django_db
@patch("mantecato.middleware.validate_api_key")
def test_v1_query_executes_real_postgresql_aggregates(
    mock_validate: MagicMock,
    client: Client,
) -> None:
    mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
    website = Website.objects.create(
        id=_WEBSITE_ID,
        name="API v1 test",
        user_id=_USER_ID,
        is_deleted=False,
    )
    _event(
        website.id,
        datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        path="/a",
        visitor="visitor-a",
        country="US",
        groups=["family:a", "topic:x"],
    )
    _event(
        website.id,
        datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
        path="/b",
        visitor="visitor-a",
        country="US",
        groups=["family:b", "topic:x"],
    )
    _event(
        website.id,
        datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
        path="/lost",
        visitor="visitor-b",
        country="GB",
        groups=["family:b"],
    )
    _event(
        website.id,
        datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        path="/a",
        visitor="visitor-a",
        country="US",
        groups=["family:a"],
    )

    response = client.post(
        "/api/v1/analytics/query/",
        data=json.dumps(
            {
                "website_id": _WEBSITE_ID,
                "operation": "totals",
                "start": "2026-06-01T00:00:00Z",
                "end": "2026-06-03T00:00:00Z",
                "metrics": [
                    "pageviews",
                    "daily_unique_visitors",
                    "visits",
                    "bounces",
                ],
            }
        ),
        content_type="application/json",
        **_AUTH,
    )
    assert response.status_code == 200, response.content
    totals = response.json()["totals"]
    assert totals == {
        "pageviews": 4,
        "daily_unique_visitors": 3,
        "visits": 3,
        "bounces": 2,
    }

    grouped = client.post(
        "/api/v1/analytics/query/",
        data=json.dumps(
            {
                "website_id": _WEBSITE_ID,
                "operation": "breakdown",
                "start": "2026-06-01",
                "end": "2026-06-03",
                "dimensions": ["content_group"],
                "dimension_prefix": "family:",
                "metrics": ["pageviews"],
            }
        ),
        content_type="application/json",
        **_AUTH,
    )
    assert grouped.status_code == 200, grouped.content
    assert grouped.json()["query"]["rows_are_overlapping"] is True
    assert {row["content_group"] for row in grouped.json()["rows"]} == {
        "family:a",
        "family:b",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("dimensions", "filters", "expected_pageviews", "expected_rows"),
    [
        (["referrer_domain"], [], 2, 2),
        (["country"], ["country:neq:GB", "country:eq:US"], 1, 1),
        (["country"], ["country:eq:US", "country:neq:GB"], 1, 1),
    ],
)
@patch("mantecato.middleware.validate_api_key")
def test_v1_referrer_and_mixed_filters_execute_on_postgresql(
    mock_validate: MagicMock,
    client: Client,
    dimensions: list[str],
    filters: list[str],
    expected_pageviews: int,
    expected_rows: int,
) -> None:
    mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
    Website.objects.create(id=_WEBSITE_ID, name="Review test", user_id=_USER_ID)
    for country in ("US", "GB"):
        _event(
            _WEBSITE_ID,
            datetime(2026, 6, 1, 10, tzinfo=UTC),
            path="/docs",
            visitor=country,
            country=country,
        )
    WebsiteEvent.objects.filter(website_id=_WEBSITE_ID, country="US").update(
        referrer_domain="search.example"
    )
    response = client.post(
        "/api/v1/analytics/query/",
        data=json.dumps(
            {
                "website_id": _WEBSITE_ID,
                "operation": "breakdown",
                "start": "2026-06-01",
                "end": "2026-06-02",
                "dimensions": dimensions,
                "filters": filters,
                "metrics": ["pageviews"],
            }
        ),
        content_type="application/json",
        **_AUTH,
    )
    assert response.status_code == 200, response.content
    assert response.json()["totals"]["pageviews"] == expected_pageviews
    assert len(response.json()["rows"]) == expected_rows
    if filters:
        assert response.json()["rows"][0]["country"] == "US"


@pytest.mark.django_db
@patch("mantecato.middleware.validate_api_key")
def test_v1_compare_keeps_dimensions_that_fell_to_zero(
    mock_validate: MagicMock,
    client: Client,
) -> None:
    mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
    website = Website.objects.create(
        id=_WEBSITE_ID,
        name="API comparison test",
        user_id=_USER_ID,
        is_deleted=False,
    )
    _event(
        website.id,
        datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        path="/lost",
        visitor="visitor-a",
        country="US",
    )
    _event(
        website.id,
        datetime(2026, 6, 2, 10, 0, tzinfo=UTC),
        path="/kept",
        visitor="visitor-b",
        country="US",
    )

    response = client.post(
        "/api/v1/analytics/compare/",
        data=json.dumps(
            {
                "website_id": _WEBSITE_ID,
                "dimensions": ["url_path"],
                "metric": "pageviews",
                "start": "2026-06-02",
                "end": "2026-06-03",
                "previous_start": "2026-06-01",
                "previous_end": "2026-06-02",
                "direction": "losses",
            }
        ),
        content_type="application/json",
        **_AUTH,
    )
    assert response.status_code == 200, response.content
    rows = response.json()["rows"]
    assert any(
        row["url_path"] == "/lost"
        and row["current"] == 0
        and row["previous"] == 1
        and row["absolute_change"] == -1
        for row in rows
    )
