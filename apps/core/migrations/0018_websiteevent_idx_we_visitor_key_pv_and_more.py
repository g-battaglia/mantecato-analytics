# Add partial indexes covering the visitor_key read path (unique visitors,
# visits, realtime DISTINCT). See apps/core/models.py WebsiteEvent.Meta.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_visitordaily_bot_bounces_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="websiteevent",
            index=models.Index(
                condition=models.Q(("event_type", 1), ("visitor_key__isnull", False)),
                fields=["website_id", "visitor_key", "created_at"],
                name="idx_we_visitor_key_pv",
            ),
        ),
        migrations.AddIndex(
            model_name="websiteevent",
            index=models.Index(
                condition=models.Q(("event_type", 2), ("visitor_key__isnull", False)),
                fields=["website_id", "visitor_key", "created_at"],
                name="idx_we_visitor_key_evt",
            ),
        ),
    ]
