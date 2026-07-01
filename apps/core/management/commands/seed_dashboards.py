"""Seed Custom Dashboards from a JSON config — or a minimal generic example.

Idempotent config-as-code: validates every dashboard ``config`` with
``validate_dashboard_config`` then upserts (matched by owner+website+name).
Nothing deployment-specific is baked in — the built-in example is a generic
"Overview". Callers bring their own dashboards via ``--config``.

Usage::

    # From a JSON file (a list of {"website", "name", "description"?, "config"}):
    python manage.py seed_dashboards --config dashboards.json

    # Or a built-in generic Overview for a single website:
    python manage.py seed_dashboards --website <uuid>

    # Owner (defaults to the first admin) + preview:
    python manage.py seed_dashboards --website <uuid> --user admin --dry-run
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.dashboards.services import create_new_dashboard
from apps.dashboards.widgets import validate_dashboard_config


def _example_overview(website: str) -> list[dict[str, Any]]:
    """A minimal, generic starter dashboard for one website (no assumptions)."""
    return [{
        "website": website,
        "name": "Overview",
        "description": "Traffic, top pages, sources and events.",
        "config": {
            "version": 2, "layout": {"columns": 12}, "dateRange": "30d", "filters": [],
            "widgets": [
                {"id": "k1", "type": "kpi", "metric": "visitors", "title": "Visitors", "grid": {"x": 0, "y": 0, "w": 3, "h": 1}},
                {"id": "k2", "type": "kpi", "metric": "pageviews", "title": "Pageviews", "grid": {"x": 3, "y": 0, "w": 3, "h": 1}},
                {"id": "k3", "type": "kpi", "metric": "bounce_rate", "title": "Bounce rate", "grid": {"x": 6, "y": 0, "w": 3, "h": 1}},
                {"id": "k4", "type": "kpi", "metric": "avg_duration", "title": "Avg duration", "grid": {"x": 9, "y": 0, "w": 3, "h": 1}},
                {"id": "ts", "type": "timeseries", "title": "Traffic", "grid": {"x": 0, "y": 1, "w": 12, "h": 3}},
                {"id": "pg", "type": "breakdown", "source": "pages", "title": "Top pages", "grid": {"x": 0, "y": 4, "w": 6, "h": 4}},
                {"id": "src", "type": "breakdown", "source": "sources", "chart": "pie", "title": "Sources", "grid": {"x": 6, "y": 4, "w": 6, "h": 4}},
                {"id": "ev", "type": "breakdown", "source": "events", "title": "Top events", "grid": {"x": 0, "y": 8, "w": 6, "h": 4}},
                {"id": "sec", "type": "breakdown", "source": "sections", "depth": 1, "title": "Sections", "grid": {"x": 6, "y": 8, "w": 6, "h": 4}},
            ],
        },
    }]


def _load_config(path: str) -> list[dict[str, Any]]:
    """Parse ``--config`` into normalized dashboard definitions."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"Could not read --config {path}: {exc}") from exc
    if not isinstance(data, list):
        raise CommandError("--config must be a JSON list of {website, name, config} objects.")
    defs: list[dict[str, Any]] = []
    for i, d in enumerate(data):
        if not isinstance(d, dict) or not d.get("website") or not d.get("name") or not isinstance(d.get("config"), dict):
            raise CommandError(f"config[{i}]: needs 'website', 'name' and an object 'config'.")
        defs.append({
            "website": str(d["website"]),
            "name": str(d["name"]),
            "description": str(d.get("description") or ""),
            "config": d["config"],
        })
    return defs


class Command(BaseCommand):
    help = "Seed Custom Dashboards from a JSON config, or a generic example (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--config", default=None, help="Path to a JSON list of dashboard definitions.")
        parser.add_argument("--website", default=None, help="Seed the built-in generic Overview for this website id.")
        parser.add_argument("--user", default=None, help="Owner username (defaults to the first admin).")
        parser.add_argument("--user-id", default=None, help="Owner user UUID (overrides --user).")
        parser.add_argument("--dry-run", action="store_true", help="Validate + report without writing.")

    def handle(self, *args, **options):
        from apps.core.models import Dashboard, MantecatoUser

        if options["config"]:
            defs = _load_config(options["config"])
        elif options["website"]:
            defs = _example_overview(options["website"])
        else:
            raise CommandError("Provide --config <file.json> or --website <uuid>.")

        # Fail fast on any invalid config before touching the DB.
        for d in defs:
            errors = validate_dashboard_config(d["config"])
            if errors:
                raise CommandError(f"'{d['name']}' has an invalid config: {'; '.join(errors[:5])}")

        if options["dry_run"]:
            for d in defs:
                self.stdout.write(f"  [validated] {d['name']} → {d['website']}")
            self.stdout.write(self.style.SUCCESS(f"{len(defs)} dashboards validated (dry-run, nothing written)"))
            return

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

        created = updated = 0
        for d in defs:
            existing = Dashboard.objects.filter(user_id=user_id, website_id=d["website"], name=d["name"]).first()
            if existing:
                existing.name = d["name"]
                existing.description = d["description"]
                existing.parameters = d["config"]
                existing.save()
                updated += 1
                self.stdout.write(self.style.WARNING(f"  updated  {d['name']}"))
            else:
                create_new_dashboard(
                    user_id=user_id, website_id=d["website"],
                    name=d["name"], description=d["description"], config=d["config"],
                )
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  created  {d['name']}"))

        self.stdout.write(self.style.SUCCESS(
            f"{len(defs)} dashboards — {created} created, {updated} updated (owner {user_id})"
        ))
