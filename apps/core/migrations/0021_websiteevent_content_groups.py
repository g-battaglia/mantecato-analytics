"""Add ``WebsiteEvent.content_groups`` plus its Postgres containment index.

``AddField`` on a nullable column is a catalog-only change — no table rewrite,
so it is instant even on a large ``website_event``. The GIN index backs the
``content_group`` filter's ``?|`` key-existence lookups; it uses the default
``jsonb_ops`` opclass, which supports them (``jsonb_path_ops`` would be smaller
but only answers ``@>``). It is built ``CONCURRENTLY`` — hence
``atomic = False`` — so the migration never takes a write lock on a live table.
SQLite deployments skip the index: the ORM fallback path scans in Python there
anyway.
"""

from django.db import migrations, models

_INDEX_NAME = "idx_we_content_groups"

CREATE_INDEX = (
    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME} "
    "ON website_event USING GIN (content_groups)"
)
DROP_INDEX = f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_NAME}"


def _run_if_postgres(sql):
    """Return a RunPython callable that executes *sql* only on PostgreSQL."""

    def _inner(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(sql)

    return _inner


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    atomic = False

    dependencies = [
        ("core", "0020_websiteevent_idx_we_visitor_key_expiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="websiteevent",
            name="content_groups",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.RunPython(
            _run_if_postgres(CREATE_INDEX),
            _run_if_postgres(DROP_INDEX),
        ),
    ]
