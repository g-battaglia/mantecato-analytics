from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import VisitorSketch, Website, WebsiteEvent


class Command(BaseCommand):
    help = "Permanently delete ALL tracking data (events + visitor sketches) for a website."

    def add_arguments(self, parser):
        parser.add_argument("website_id", help="UUID of the website to purge.")
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Skip the interactive confirmation (use in scripts/CI).",
        )

    def handle(self, *args, **options):
        website_id = options["website_id"]

        try:
            site = Website.objects.get(id=website_id, is_deleted=False)
        except Website.DoesNotExist:
            raise CommandError(f"No active website found with id={website_id}")

        event_count = WebsiteEvent.objects.filter(website_id=site.id).count()
        sketch_count = VisitorSketch.objects.filter(website_id=site.id).count()

        if event_count == 0 and sketch_count == 0:
            self.stdout.write(self.style.WARNING(f"No tracking data found for '{site.name}' ({site.domain})."))
            return

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("  IRREVERSIBLE DATA DELETION"))
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write("")
        self.stdout.write(f"  Website:  {site.name}")
        self.stdout.write(f"  Domain:   {site.domain}")
        self.stdout.write(f"  ID:       {site.id}")
        self.stdout.write("")
        self.stdout.write(f"  Events to delete:          {event_count:,}")
        self.stdout.write(f"  Visitor sketches to delete: {sketch_count:,}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("  This action CANNOT be undone. Make a backup first."))
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write("")

        if not options["no_input"]:
            self.stdout.write(f'  To confirm, type the full site name: {self.style.NOTICE(site.name)}')
            self.stdout.write("")
            confirm = input("  > ").strip()
            if confirm != site.name:
                raise CommandError("Confirmation did not match. Aborted.")

        deleted_events, _ = WebsiteEvent.objects.filter(website_id=site.id).delete()
        deleted_sketches, _ = VisitorSketch.objects.filter(website_id=site.id).delete()

        site.reset_at = timezone.now()
        site.save(update_fields=["reset_at"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  Purged {deleted_events:,} events + {deleted_sketches:,} sketches."))
        self.stdout.write(self.style.SUCCESS(f"  reset_at set to {site.reset_at.isoformat()}"))
