"""Remove region and city from WebsiteEvent — country-only geo for privacy.

Region and city data, combined with timestamps and URL paths, can
re-identify individuals in low-traffic scenarios. Only the ISO country
code is retained for aggregate geographic breakdowns.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_privacy_first_aggregate_only"),
    ]

    operations = [
        migrations.RemoveField(model_name="websiteevent", name="region"),
        migrations.RemoveField(model_name="websiteevent", name="city"),
    ]
