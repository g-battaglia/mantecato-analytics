"""Add the PostgreSQL GIN index for content-group membership lookups.

The operation is isolated in a non-atomic migration because PostgreSQL cannot
build an index concurrently inside a transaction. Both directions use
``IF [NOT] EXISTS``, so deployment can safely retry an interrupted migration.
SQLite skips the index because its query path uses the ORM fallback.
"""

from django.db import migrations

_INDEX_NAME = "idx_we_content_groups"

CREATE_INDEX = (
    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME} "
    "ON website_event USING GIN (content_groups)"
)
DROP_INDEX = f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_NAME}"


def create_index(apps, schema_editor):
    """Replace any partial index left by an interrupted concurrent build."""
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DROP_INDEX)
        cursor.execute(CREATE_INDEX)


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DROP_INDEX)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("core", "0021_websiteevent_content_groups"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
