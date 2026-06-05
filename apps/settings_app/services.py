"""Settings CRUD — ORM operations on the ``report`` table and ``website`` table.

API keys, bot config, and scheduled exports are all ``report`` rows
discriminated by ``type``, accessed through the proxy models in
:mod:`apps.core.models`.  Website management uses the ``Website`` model
directly, with soft-delete (``is_deleted=True``) to preserve analytics joins.

Multi-step service functions (e.g. ``save_bot_config``) are wrapped in
:func:`~django.db.transaction.atomic` so a failure between the
read and the write step rolls back cleanly. Update functions use
``save(update_fields=[...])`` to UPDATE only the columns that actually changed
— shaving WAL noise and making the SQL log easier to audit.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.db import transaction

from apps.core.api_keys import generate_key, hash_key
from apps.core.models import (
    ApiKey,
    BotConfig,
    ScheduledExport,
    UmamiImportJob,
    Website,
    merge_bot_config,
)
from apps.core.services import run_umami_import_job

if TYPE_CHECKING:
    from typing import Any

# API keys are not scoped to a website; the report row uses a placeholder id.
_API_KEY_WEBSITE_ID = "00000000-0000-0000-0000-000000000000"


# ── API Keys ──────────────────────────────────────────────────────────────


def get_api_keys_for_user(user_id: str) -> list[dict[str, Any]]:
    """Return all API keys owned by *user_id* (newest-created first).

    Args:
        user_id: UUID string of the key owner.

    Returns:
        A list of serialized key dicts (without the raw key -- only
        the prefix and metadata are included).
    """
    keys = ApiKey.objects.filter(user_id=user_id).order_by("-created_at")
    return [k.to_dict() for k in keys]


def generate_new_api_key(
    user_id: str,
    name: str,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Create an API key; the returned dict includes the raw key (shown once).

    The raw key is generated via :func:`~apps.core.api_keys.generate_key`,
    then its SHA-256 hash is stored in ``report.parameters.keyHash``. The
    raw key is returned only in this response -- afterwards it cannot be
    recovered.

    Args:
        user_id: UUID string of the key's owner.
        name: Human-readable label for the key.
        scopes: Permission scopes (default ``["read", "write"]``).

    Returns:
        A dict containing ``id``, ``name``, ``key`` (raw), ``prefix``,
        ``scopes``, and ``createdAt``.
    """
    scopes = scopes if scopes is not None else ["read", "write"]
    key = generate_key()
    # Store a truncated prefix for display in the key list UI (the full
    # key is never persisted).
    prefix = key[:12] + "..."
    created_at = datetime.now(UTC).isoformat()
    api_key = ApiKey.objects.create(
        user_id=user_id,
        # API keys are not scoped to a website; use the placeholder UUID.
        website_id=_API_KEY_WEBSITE_ID,
        name=name,
        description="",
        parameters={
            "keyHash": hash_key(key),
            "prefix": prefix,
            "scopes": scopes,
            "createdAt": created_at,
            "lastUsedAt": None,
        },
    )
    return {
        "id": str(api_key.id),
        "name": name,
        "key": key,
        "prefix": prefix,
        "scopes": scopes,
        "createdAt": created_at,
    }


def remove_api_key(key_id: str, user_id: str) -> bool:
    """Revoke an API key; return ``True`` if a row was actually deleted.

    Args:
        key_id: UUID string of the API key row.
        user_id: UUID string of the expected owner.

    Returns:
        ``True`` when exactly one row was deleted, ``False`` otherwise.
    """
    deleted, _ = ApiKey.objects.filter(id=key_id, user_id=user_id).delete()
    return deleted > 0


# ── Bot Config ──────────────────────────────────────────────────────────────


def get_bot_config(website_id: str) -> dict[str, Any]:
    """Return the website's bot config, or a full-defaults payload when unset.

    When no row exists yet the returned dict carries ``id=None`` and
    ``config`` filled with :func:`merge_bot_config` defaults so the form
    always receives a complete object.

    Args:
        website_id: UUID string of the website.

    Returns:
        A serialized bot-config dict (same shape as
        :meth:`BotConfig.to_dict`).
    """
    config = BotConfig.objects.filter(website_id=website_id).first()
    if config is not None:
        return config.to_dict()
    # No config saved yet -- return a synthetic dict with all defaults
    # so the form renders every field with its default value.
    return {
        "id": None,
        "websiteId": website_id,
        "config": merge_bot_config({}),
        "createdAt": None,
        "updatedAt": None,
    }


def save_bot_config(
    user_id: str,
    website_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create or update the website's bot config and return it.

    The incoming *config* is merged with :data:`BOT_CONFIG_DEFAULTS` via
    :func:`merge_bot_config` so unknown keys are dropped and missing keys
    receive their defaults. The entire operation is wrapped in
    ``transaction.atomic`` so the SELECT-then-UPDATE sequence is
    consistent under concurrent writes.

    Args:
        user_id: UUID string of the acting user (used only on first create).
        website_id: UUID string of the website.
        config: Partial config dict from the form / API.

    Returns:
        The serialized :meth:`BotConfig.to_dict` after persisting.
    """
    merged = merge_bot_config(config)
    with transaction.atomic():
        existing = BotConfig.objects.filter(website_id=website_id).first()
        if existing is not None:
            existing.parameters = merged
            existing.save(update_fields=["parameters", "updated_at"])
            return existing.to_dict()
        # First save for this website -- create the config row.
        created = BotConfig.objects.create(
            user_id=user_id,
            website_id=website_id,
            name="Bot Detection Config",
            description="",
            parameters=merged,
        )
        return created.to_dict()


# ── Scheduled Exports ────────────────────────────────────────────────────────


def get_scheduled_exports_for_user(user_id: str) -> list[dict[str, Any]]:
    """Return scheduled exports owned by *user_id* (newest-updated first).

    Args:
        user_id: UUID string of the export owner.

    Returns:
        A list of serialized export dicts. Empty when none exist.
    """
    exports = ScheduledExport.objects.filter(user_id=user_id).order_by("-updated_at")
    return [e.to_dict() for e in exports]


def get_scheduled_export_detail(report_id: str, user_id: str) -> dict[str, Any] | None:
    """Return a single scheduled export owned by *user_id*, or ``None``.

    Args:
        report_id: UUID string of the scheduled export row.
        user_id: UUID string of the expected owner.

    Returns:
        The serialized dict, or ``None`` when not found.
    """
    export = ScheduledExport.objects.filter(id=report_id, user_id=user_id).first()
    return export.to_dict() if export else None


def remove_scheduled_export(report_id: str, user_id: str) -> bool:
    """Delete a scheduled export; return ``True`` if a row was actually removed.

    Args:
        report_id: UUID string of the scheduled export to delete.
        user_id: UUID string of the expected owner.

    Returns:
        ``True`` when exactly one row was deleted, ``False`` otherwise.
    """
    deleted, _ = ScheduledExport.objects.filter(id=report_id, user_id=user_id).delete()
    return deleted > 0


# ---------------------------------------------------------------------------
# Websites (managed via the Website model, not the report table)
# ---------------------------------------------------------------------------


def create_website(
    name: str,
    user_id: str,
    domain: str | None = None,
    share_id: str | None = None,
) -> dict[str, Any]:
    """Create a new tracked website and stamp it with the owner's user ID.

    Unlike report-table entities, websites live in their own table and
    are soft-deletable (``is_deleted`` flag).  The ``user_id`` field
    determines ownership for non-admin users.

    Args:
        name: Human-readable display name.
        user_id: UUID string of the creating user (becomes the owner).
        domain: Optional domain hint (e.g. ``"example.com"``).
        share_id: Optional public share identifier.

    Returns:
        A dict with ``id``, ``name``, ``domain`` keys for the newly
        created website.
    """

    site = Website.objects.create(
        name=name,
        domain=domain or "",
        share_id=share_id or None,
        user_id=user_id,
    )
    return {"id": str(site.id), "name": site.name, "domain": site.domain}


def soft_delete_website(
    site_id: str,
    user_id: str,
    is_admin: bool = False,
) -> str | None:
    """Soft-delete a website by setting ``is_deleted=True``.

    Soft deletion preserves the row so that historical analytics joins
    (events referencing this ``website_id``) keep resolving.  Only the
    ``is_deleted`` column is flipped — no data is removed.

    Args:
        site_id: UUID string of the website to delete.
        user_id: UUID string of the acting user.
        is_admin: When ``True``, skip the ownership check (admins can
            delete any site).

    Returns:
        The site name on success (for flash messages), or ``None`` if
        the site was not found or not owned by the user.
    """

    qs = Website.objects.filter(id=site_id, is_deleted=False)
    if not is_admin:
        qs = qs.filter(user_id=user_id)
    site = qs.first()
    if site is None:
        return None
    site.is_deleted = True
    site.save(update_fields=["is_deleted"])
    return site.name


# ---------------------------------------------------------------------------
# Umami import (background, data-only, single-site)
# ---------------------------------------------------------------------------


def start_umami_import_job(
    *,
    user_id: str,
    target_website: str,
    source_website: str,
    source_dsn: str,
    since_date: datetime | None,
    replace: bool,
) -> dict[str, Any]:
    """Create a :class:`UmamiImportJob` and start the background import thread.

    The job row stores only non-sensitive parameters and progress counters; the
    *source_dsn* is handed straight to the worker thread and **never persisted**.
    The thread is a daemon so it never blocks interpreter shutdown, and the
    importer runs data-only/single-site (see
    :func:`apps.core.services.run_umami_import_job`).

    Args:
        user_id: UUID string of the admin starting the import.
        target_website: Existing Mantecato ``website_id`` to remap rows onto.
        source_website: Umami ``website_id`` to import.
        source_dsn: Source Umami PostgreSQL DSN (not stored).
        since_date: Optional ``created_at`` cutoff.
        replace: Whether to delete the target site's analytics rows first.

    Returns:
        A dict with the new job ``id`` (string).
    """
    job = UmamiImportJob.objects.create(
        user_id=user_id,
        status="pending",
        target_website_id=target_website,
        source_website_id=source_website,
        since=since_date.date() if since_date else None,
        replace=replace,
    )
    thread = threading.Thread(
        target=run_umami_import_job,
        args=(str(job.id), source_dsn),
        kwargs={
            "target_website": target_website,
            "source_website": source_website,
            "since_date": since_date,
            "replace": replace,
        },
        daemon=True,
    )
    thread.start()
    return {"id": str(job.id)}


def get_umami_import_job(job_id: str, user_id: str) -> UmamiImportJob | None:
    """Return the user's import job by id, or ``None`` when not found/owned."""
    return UmamiImportJob.objects.filter(id=job_id, user_id=user_id).first()


def get_latest_umami_import_job(user_id: str) -> UmamiImportJob | None:
    """Return the user's most recently created import job, or ``None``."""
    return UmamiImportJob.objects.filter(user_id=user_id).order_by("-created_at").first()
