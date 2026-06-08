"""Privacy-first schema migration — remove session tracking, simplify website_event.

Removes Session, SessionData, Revenue, Segment, EventData models and drops
columns from WebsiteEvent that are no longer needed in aggregate-only mode:
session_id, visit_id, referrer fields, UTM fields, click ID fields,
event_name, tag, screen, language.

Adds a new simplified index structure for anonymous pageview queries.
"""

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_add_password_is_default"),
    ]

    operations = [
        # Remove WebsiteEvent indexes that reference columns dropped below.
        migrations.RemoveIndex(model_name="websiteevent", name="idx_we_session_id"),
        migrations.RemoveIndex(model_name="websiteevent", name="idx_we_visit_id"),
        migrations.RemoveIndex(model_name="websiteevent", name="idx_we_pageview_hot"),
        migrations.RemoveIndex(model_name="websiteevent", name="idx_we_event_hot"),
        migrations.RemoveIndex(model_name="websiteevent", name="idx_we_visit_created_pv"),
        # Drop tables that are no longer needed
        migrations.DeleteModel(name="Segment"),
        migrations.DeleteModel(name="Revenue"),
        migrations.DeleteModel(name="SessionData"),
        migrations.DeleteModel(name="EventData"),
        migrations.DeleteModel(name="Session"),
        # Remove columns from WebsiteEvent that violate privacy-first principles
        migrations.RemoveField(model_name="websiteevent", name="session_id"),
        migrations.RemoveField(model_name="websiteevent", name="visit_id"),
        migrations.RemoveField(model_name="websiteevent", name="referrer_path"),
        migrations.RemoveField(model_name="websiteevent", name="referrer_query"),
        migrations.RemoveField(model_name="websiteevent", name="referrer_domain"),
        migrations.RemoveField(model_name="websiteevent", name="event_name"),
        migrations.RemoveField(model_name="websiteevent", name="tag"),
        migrations.RemoveField(model_name="websiteevent", name="screen"),
        migrations.RemoveField(model_name="websiteevent", name="language"),
        migrations.RemoveField(model_name="websiteevent", name="utm_source"),
        migrations.RemoveField(model_name="websiteevent", name="utm_medium"),
        migrations.RemoveField(model_name="websiteevent", name="utm_campaign"),
        migrations.RemoveField(model_name="websiteevent", name="utm_content"),
        migrations.RemoveField(model_name="websiteevent", name="utm_term"),
        migrations.RemoveField(model_name="websiteevent", name="gclid"),
        migrations.RemoveField(model_name="websiteevent", name="fbclid"),
        migrations.RemoveField(model_name="websiteevent", name="msclkid"),
        migrations.RemoveField(model_name="websiteevent", name="ttclid"),
        migrations.RemoveField(model_name="websiteevent", name="twclid"),
        migrations.RemoveField(model_name="websiteevent", name="li_fat_id"),
    ]
