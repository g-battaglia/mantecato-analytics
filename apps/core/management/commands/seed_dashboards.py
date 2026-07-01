"""Seed a curated set of Custom Dashboards for a "landing + app" property pair.

Idempotent config-as-code: builds a small, opinionated set of dashboards for a
landing site (``www``) and a plan-tiered app, validates every config with
``validate_dashboard_config``, then upserts them (matched by owner+website+name).
Both website ids are required arguments — nothing deployment-specific is baked in.

Usage::

    python manage.py seed_dashboards --app-website <uuid> --www-website <uuid>
    python manage.py seed_dashboards --app-website <uuid> --www-website <uuid> --user admin
    python manage.py seed_dashboards --app-website <uuid> --www-website <uuid> --dry-run

The app tier is expected as the first URL segment (``/anon /free /trial /pro
/lifetime/…``), so cohort dashboards scope with ``url_path:starts_with:/<tier>/``
and the "by tier" breakdown groups sections at ``depth=1``.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.dashboards.services import create_new_dashboard
from apps.dashboards.widgets import validate_dashboard_config

# Cohorts to generate a per-tier dashboard for on the app.
APP_TIERS = ("free", "trial", "pro", "lifetime")


# ── Widget builders ──────────────────────────────────────────────────────────


def _kpi(wid: str, metric: str, title: str, x: int, w: int = 3) -> dict[str, Any]:
    return {"id": wid, "type": "kpi", "metric": metric, "title": title,
            "grid": {"x": x, "y": 0, "w": w, "h": 1}}


def _timeseries(wid: str, title: str, y: int) -> dict[str, Any]:
    return {"id": wid, "type": "timeseries", "title": title,
            "grid": {"x": 0, "y": y, "w": 12, "h": 3}}


def _breakdown(wid: str, source: str, title: str, x: int, y: int, w: int = 6,
               *, chart: str = "bar", depth: int | None = None) -> dict[str, Any]:
    widget: dict[str, Any] = {"id": wid, "type": "breakdown", "source": source,
                              "title": title, "chart": chart,
                              "grid": {"x": x, "y": y, "w": w, "h": 4}}
    if depth is not None:
        widget["depth"] = depth
    return widget


# ── Dashboard configs ────────────────────────────────────────────────────────


def _www_overview() -> dict[str, Any]:
    return {
        "version": 2, "layout": {"columns": 12}, "dateRange": "30d", "filters": [],
        "widgets": [
            _kpi("k1", "visitors", "Visitors", 0),
            _kpi("k2", "pageviews", "Pageviews", 3),
            _kpi("k3", "bounce_rate", "Bounce rate", 6),
            _kpi("k4", "avg_duration", "Avg duration", 9),
            _timeseries("ts", "Traffic", 1),
            _breakdown("pg", "pages", "Top pages", 0, 4),
            _breakdown("src", "sources", "Sources", 6, 4, chart="pie"),
            _breakdown("geo", "country", "Geography", 0, 8),
            _breakdown("dev", "device", "Devices", 6, 8, chart="pie"),
        ],
    }


def _app_overview() -> dict[str, Any]:
    return {
        "version": 2, "layout": {"columns": 12}, "dateRange": "30d", "filters": [],
        "widgets": [
            _kpi("k1", "visitors", "Visitors", 0),
            _kpi("k2", "pageviews", "Pageviews", 3),
            _kpi("k3", "visits", "Visits", 6),
            _kpi("k4", "pages_per_visit", "Pages / visit", 9),
            _timeseries("ts", "Activity", 1),
            _breakdown("tier", "sections", "Traffic by tier", 0, 4, depth=1),
            _breakdown("ev", "events", "Top events", 6, 4),
            _breakdown("pg", "pages", "Top pages", 0, 8, w=12),
        ],
    }


def _app_cohort(tier: str) -> dict[str, Any]:
    """A per-tier cohort dashboard scoped to ``/<tier>/*``."""
    return {
        "version": 2, "layout": {"columns": 12}, "dateRange": "30d",
        "filters": [f"url_path:starts_with:/{tier}/"],
        "widgets": [
            _kpi("k1", "visitors", "Visitors", 0, w=4),
            _kpi("k2", "visits", "Visits", 4, w=4),
            _kpi("k3", "avg_duration", "Avg duration", 8, w=4),
            _timeseries("ts", f"{tier.capitalize()} activity", 1),
            _breakdown("ev", "events", "Feature usage", 0, 4),
            _breakdown("pg", "pages", "Top pages", 6, 4),
        ],
    }


def _plan(app_website: str, www_website: str) -> list[tuple[str, str, str, dict]]:
    """Return the (website_id, name, description, config) tuples to upsert."""
    plan: list[tuple[str, str, str, dict]] = [
        (www_website, "Landing — Overview", "Traffic, sources and geography for the marketing site.", _www_overview()),
        (app_website, "App — Overview", "App-wide KPIs, activity and traffic split by plan tier.", _app_overview()),
    ]
    for tier in APP_TIERS:
        plan.append((
            app_website,
            f"App — {tier.capitalize()} cohort",
            f"What {tier} users do — activity, feature usage and pages (scoped to /{tier}/).",
            _app_cohort(tier),
        ))
    return plan


class Command(BaseCommand):
    help = "Seed curated Custom Dashboards for the www + app properties (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--user", default=None, help="Owner username (defaults to the first admin).")
        parser.add_argument("--user-id", default=None, help="Owner user UUID (overrides --user).")
        parser.add_argument("--app-website", required=True, help="Website id for the app property.")
        parser.add_argument("--www-website", required=True, help="Website id for the www/landing property.")
        parser.add_argument("--dry-run", action="store_true", help="Validate + report without writing.")

    def handle(self, *args, **options):
        from apps.core.models import Dashboard, MantecatoUser

        user_id = options["user_id"]
        if not user_id:
            qs = MantecatoUser.objects.all()
            if options["user"]:
                user = qs.filter(username=options["user"]).first()
            else:
                user = qs.filter(role="admin").order_by("created_at").first() or qs.order_by("created_at").first()
            if user is None:
                raise CommandError("No owner user found. Create one (createuser) or pass --user-id.")
            user_id = str(user.id)

        plan = _plan(options["app_website"], options["www_website"])

        # Fail fast on any invalid config before touching the DB.
        for _wid, name, _desc, config in plan:
            errors = validate_dashboard_config(config)
            if errors:
                raise CommandError(f"'{name}' produced an invalid config: {'; '.join(errors[:5])}")

        if options["dry_run"]:
            for website_id, name, _desc, _config in plan:
                self.stdout.write(f"  [validated] {name} → {website_id}")
            self.stdout.write(self.style.SUCCESS(f"{len(plan)} dashboards validated (dry-run, nothing written)"))
            return

        created = updated = 0
        for website_id, name, description, config in plan:
            existing = Dashboard.objects.filter(user_id=user_id, website_id=website_id, name=name).first()
            if existing:
                existing.name = name
                existing.description = description
                existing.parameters = config
                existing.save()
                updated += 1
                self.stdout.write(self.style.WARNING(f"  updated  {name}"))
            else:
                create_new_dashboard(
                    user_id=user_id, website_id=str(website_id),
                    name=name, description=description, config=config,
                )
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  created  {name}"))

        self.stdout.write(self.style.SUCCESS(
            f"{len(plan)} dashboards — {created} created, {updated} updated (owner {user_id})"
        ))
