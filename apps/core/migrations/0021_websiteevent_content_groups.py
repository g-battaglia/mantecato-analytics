"""Add ``WebsiteEvent.content_groups``.

``AddField`` on a nullable column is a catalog-only change — no table rewrite,
so it is instant even on a large ``website_event``. The concurrent PostgreSQL
index is created separately in migration 0022 so an interrupted index build can
be retried without attempting to add this column again.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_websiteevent_idx_we_visitor_key_expiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="websiteevent",
            name="content_groups",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
