"""Add database-level defaults for timestamp columns.

Django's auto_now_add sets timestamps in Python but doesn't add DB defaults.
Raw SQL INSERT queries in the query engine omit these columns, so we need
database-level defaults to avoid NOT NULL violations.
"""

from django.db import migrations

_TABLES_WITH_TIMESTAMPS = [
    ("mantecato_user", ["created_at", "updated_at"]),
    ("team", ["created_at", "updated_at"]),
    ("website", ["created_at"]),
    ("session", ["created_at"]),
    ("website_event", ["created_at"]),
    ("event_data", ["created_at"]),
    ("session_data", ["created_at"]),
    ("team_user", ["created_at"]),
    ("revenue", ["created_at"]),
    ("segment", ["created_at", "updated_at"]),
    ("report", ["created_at", "updated_at"]),
]


def _apply_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for stmt in _build_sql("forward"):
            cursor.execute(stmt)


def _remove_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for stmt in _build_sql("reverse"):
            cursor.execute(stmt)


def _build_sql(direction):
    stmts = []
    for table, columns in _TABLES_WITH_TIMESTAMPS:
        for col in columns:
            if direction == "forward":
                stmts.append(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{col}" SET DEFAULT now();'
                )
            else:
                stmts.append(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{col}" DROP DEFAULT;'
                )
    return stmts


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply_defaults, _remove_defaults),
    ]
