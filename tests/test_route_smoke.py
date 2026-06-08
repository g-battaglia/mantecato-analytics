"""End-to-end route smoke tests — render every analytics page for real.

Unlike the per-page tests that mock the service layer, these drive the full
view -> service -> query-engine -> template stack against an empty Postgres
test database. They catch template/context regressions (missing ``{% load %}``,
wrong context keys, removed helpers) that mocked-render tests cannot.

Requires Postgres (raw_query path); on SQLite the query engine takes the ORM
fallback, which is also exercised here when the test DB is SQLite.
"""

from __future__ import annotations

import pytest

from apps.core.models import Website
from tests.conftest import WEBSITE_ID

pytestmark = pytest.mark.django_db

# Every privacy-first analytics route that renders a full page or HTMX partial.
ROUTES = [
    "/",
    "/pages/",
    "/sections/",
    "/events/",
    "/devices/",
    "/geo/",
    "/compare/",
    "/heatmap/",
    "/realtime/",
    "/realtime/partial/",
    "/overview/tab/?tab=pages",
    "/overview/tab/?tab=events",
    "/overview/tab/?tab=devices",
    "/overview/tab/?tab=geo",
]


@pytest.fixture
def _seed_website() -> None:
    Website.objects.create(
        id=WEBSITE_ID,
        user_id=WEBSITE_ID,
        name="Smoke Site",
        domain="smoke.example.com",
        is_deleted=False,
    )


@pytest.mark.parametrize("route", ROUTES)
def test_route_renders(authenticated_client, _seed_website, route: str) -> None:
    """Each route renders without a 500 for an authenticated admin."""
    sep = "&" if "?" in route else "?"
    response = authenticated_client.get(f"{route}{sep}website={WEBSITE_ID}")
    assert response.status_code == 200, f"{route} returned {response.status_code}"
