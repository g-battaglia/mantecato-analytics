"""Offline, bounded authentication/audit cleanup, independent of visitor rollup."""

import math
import time
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.deletion import ProtectedError
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone

from apps.ai_connections.models import AIActivity, AIConnection, OAuthClient, OAuthCredential

_CLEANUP_LOCK = int.from_bytes(b"AIcleanu", "big")


def cleanup(*, max_runtime=120, batch_size=500, timeout_ms=5000, dry_run=False):
    if (
        not math.isfinite(max_runtime)
        or max_runtime <= 0
        or not 1 <= batch_size <= 5000
        or timeout_ms <= 0
    ):
        raise ValueError("Invalid cleanup budget")
    now = timezone.now()
    cutoff = now - timedelta(days=settings.AI_AUDIT_RETENTION_DAYS)
    pending = OAuthCredential.objects.annotate(
        client_ref=KeyTextTransform("client_id", "payload")
    ).filter(
        kind="request",
        consumed_at__isnull=True,
        expires_at__gt=now,
        client_ref=OuterRef("pk"),
    )
    phases = [
        (
            "credentials",
            OAuthCredential.objects.filter(
                Q(expires_at__lte=now) | Q(connection__user__deleted_at__isnull=False)
            ),
        ),
        (
            "activity",
            AIActivity.objects.filter(Q(created_at__lt=cutoff) | Q(user__deleted_at__isnull=False)),
        ),
        (
            "connections",
            AIConnection.objects.filter(
                Q(user__deleted_at__isnull=False)
                | Q(expires_at__lt=cutoff)
                | Q(revoked_at__lt=cutoff)
            ),
        ),
        (
            "clients",
            OAuthClient.objects.filter(
                created_at__lt=now - timedelta(days=1), aiconnection__isnull=True
            ).filter(~Exists(pending)),
        ),
    ]
    result = {
        "status": "dry_run" if dry_run else "completed",
        "deleted": {name: 0 for name, _ in phases},
    }
    deadline = time.monotonic() + max_runtime
    for name, query in phases:
        while True:
            if time.monotonic() >= deadline:
                result["status"] = "budget_exhausted"
                return result
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('statement_timeout', %s, true)", [str(timeout_ms)]
                    )
                    cursor.execute(
                        "SELECT set_config('lock_timeout', %s, true)", [str(min(timeout_ms, 1000))]
                    )
                    if not dry_run:
                        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [_CLEANUP_LOCK])
                        if not cursor.fetchone()[0]:
                            result["status"] = "busy"
                            return result
                if dry_run:
                    result["deleted"][name] = query.count()
                    break
                ids = list(
                    query.select_for_update(skip_locked=True, of=("self",))
                    .order_by(
                        "expires_at" if name in ("credentials", "connections") else "created_at",
                        "pk",
                    )
                    .values_list("pk", flat=True)[:batch_size]
                )
                if not ids:
                    break
                try:
                    _, detail = query.model.objects.filter(pk__in=ids).delete()
                except ProtectedError:
                    # A newly authorized connection can make an orphan client
                    # ineligible after selection. Re-evaluate on the next run.
                    result["status"] = "busy"
                    return result
                result["deleted"][name] += detail.get(query.model._meta.label, 0)
    return result
