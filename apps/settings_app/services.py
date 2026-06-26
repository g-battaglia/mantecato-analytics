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

import hashlib
import secrets
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.contrib.auth.hashers import check_password
from django.db import connection, transaction
from django.utils import timezone

from apps.core.api_keys import VALID_SCOPES, generate_key, hash_key
from apps.core.models import (
    ApiKey,
    BotConfig,
    MantecatoUser,
    ScheduledExport,
    UmamiImportJob,
    Website,
    merge_bot_config,
)
from apps.core.services import run_umami_import_job


class UserActionError(Exception):
    """Raised when a user-management operation violates a business rule."""


def _active_admin_count() -> int:
    """Return the number of active (non-deleted) admin users."""
    return MantecatoUser.objects.filter(role="admin", deleted_at__isnull=True).count()

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
        scopes: Permission scopes (default ``["read", "write"]``). Every
            entry must be one of :data:`~apps.core.api_keys.VALID_SCOPES`;
            unknown scopes raise ``ValueError`` (mass-assignment guard).
            Authorization for privileged scopes (e.g. ``admin``) is enforced
            by the caller, not here.

    Returns:
        A dict containing ``id``, ``name``, ``key`` (raw), ``prefix``,
        ``scopes``, and ``createdAt``.

    Raises:
        ValueError: when *scopes* contains an unrecognised scope string.
    """
    scopes = scopes if scopes is not None else ["read", "write"]
    unknown = [s for s in scopes if s not in VALID_SCOPES]
    if unknown:
        raise ValueError(f"Unknown scope(s): {', '.join(sorted(unknown))}")
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
        # Serialise concurrent first-saves for the same website so two requests
        # can't both miss the existing row and create duplicate BotConfig rows
        # (there is no unique constraint on the shared report table). On SQLite
        # the single-writer lock already serialises writes.
        if connection.vendor == "postgresql":
            lock_key = int.from_bytes(
                hashlib.sha256(f"bot_config:{website_id}".encode()).digest()[:8],
                "big",
                signed=True,
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
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


def generate_share_id() -> str:
    """Return a random URL-safe public share id for a site's badge.

    ~32 chars (fits ``Website.share_id`` max_length=64); unguessable so the
    public ``/api/badge`` endpoint can't be enumerated.
    """
    return secrets.token_urlsafe(24)


def set_website_badge(
    site_id: str,
    user_id: str,
    is_admin: bool = False,
    *,
    action: str = "enable",
) -> dict[str, Any] | None:
    """Enable / regenerate / disable a site's public badge (its ``share_id``).

    ``enable`` sets a fresh ``share_id`` only if none exists; ``regenerate``
    always rotates it (invalidating the old badge URL); ``disable`` clears it
    (the badge endpoint then 404s). Ownership is enforced unless *is_admin*.

    Returns a dict with ``id``, ``name`` and the resulting ``share_id`` (``None``
    after disable), or ``None`` if the site was not found / not owned.
    """
    qs = Website.objects.filter(id=site_id, is_deleted=False)
    if not is_admin:
        qs = qs.filter(user_id=user_id)
    site = qs.first()
    if site is None:
        return None

    if action == "disable":
        site.share_id = None
    elif action == "regenerate" or not site.share_id:
        # The unique constraint makes a collision astronomically unlikely; retry
        # a few times defensively rather than surfacing an IntegrityError.
        for _ in range(5):
            candidate = generate_share_id()
            if not Website.objects.filter(share_id=candidate).exists():
                site.share_id = candidate
                break
    site.save(update_fields=["share_id"])
    return {"id": str(site.id), "name": site.name, "share_id": site.share_id}


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


def purge_website_data(
    site_id: str,
    user_id: str,
    is_admin: bool = False,
) -> dict[str, Any] | None:
    """Delete ALL tracking data (events + visitor counters) for a website.

    Removes the website's events plus its exact-visitor rows (both the ephemeral
    same-day state and the permanent daily aggregates). The shared per-day salt
    is global, not per-site, so it is left untouched. Returns a summary dict on
    success, or ``None`` if the site was not found / not owned by the user.
    """
    from apps.core.models import (
        VisitorDaily,
        VisitorDayState,
        VisitorPeriod,
        VisitorScopeState,
        WebsiteEvent,
    )

    qs = Website.objects.filter(id=site_id, is_deleted=False)
    if not is_admin:
        qs = qs.filter(user_id=user_id)
    site = qs.first()
    if site is None:
        return None

    with transaction.atomic():
        deleted_events, _ = WebsiteEvent.objects.filter(website_id=site.id).delete()
        visitor_rows = 0
        for model in (VisitorDayState, VisitorScopeState, VisitorDaily, VisitorPeriod):
            n, _ = model.objects.filter(website_id=site.id).delete()
            visitor_rows += n
        site.reset_at = timezone.now()
        site.save(update_fields=["reset_at"])

    return {
        "name": site.name,
        "events": deleted_events,
        "visitor_rows": visitor_rows,
    }


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


# ---------------------------------------------------------------------------
# User management (admin CRUD + self-service password change)
# ---------------------------------------------------------------------------


def get_all_users() -> list[dict[str, Any]]:
    """Return all active (non-deleted) users ordered by username.

    Returns:
        A list of dicts with ``id``, ``username``, ``role``, ``is_admin``,
        ``last_login``, ``created_at`` keys.
    """
    users = MantecatoUser.objects.filter(deleted_at__isnull=True).order_by("username")
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "role": u.role,
            "is_admin": u.role == "admin",
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "password_is_default": u.password_is_default,
        }
        for u in users
    ]


def get_user(user_id: str) -> dict[str, Any] | None:
    """Return a single active user by id, or ``None``.

    Args:
        user_id: UUID string of the user.

    Returns:
        A dict with ``id``, ``username``, ``role``, ``is_admin`` keys.
    """
    user = MantecatoUser.objects.filter(id=user_id, deleted_at__isnull=True).first()
    if user is None:
        return None
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "is_admin": user.role == "admin",
        "password_is_default": user.password_is_default,
    }


def create_user_account(username: str, role: str, password: str) -> dict[str, Any]:
    """Create a new user account.

    Args:
        username: Unique login identifier.
        role: ``"user"`` or ``"admin"``.
        password: Raw password string.

    Returns:
        A dict with ``id``, ``username``, ``role`` keys.

    Raises:
        UserActionError: If the username is already taken by an active user.
    """
    if MantecatoUser.objects.filter(username=username, deleted_at__isnull=True).exists():
        raise UserActionError(f"User '{username}' already exists.")
    user = MantecatoUser.objects.create_user(username=username, password=password, role=role)
    return {"id": str(user.id), "username": user.username, "role": user.role}


def update_user_account(
    user_id: str,
    *,
    role: str | None = None,
    new_password: str | None = None,
    acting_user_id: str,
) -> None:
    """Update a user's role and/or password.

    Applies **anti-lockout guards**: cannot demote the last active admin.

    Args:
        user_id: UUID string of the user to update.
        role: New role (``"user"`` or ``"admin"``), or ``None`` to keep.
        new_password: New raw password, or ``None`` to keep.
        acting_user_id: UUID string of the admin performing the action.

    Raises:
        UserActionError: On duplicate username or last-admin demotion.
    """
    user = MantecatoUser.objects.filter(id=user_id, deleted_at__isnull=True).first()
    if user is None:
        raise UserActionError("User not found.")

    if role is not None and role != user.role:
        # Demoting from admin to user: check last-admin guard.
        if user.role == "admin" and role == "user" and _active_admin_count() <= 1:
            raise UserActionError("Cannot demote the last admin.")
        user.role = role

    if new_password:
        user.set_password(new_password)
        user.password_is_default = False

    user.save(update_fields=["role", "password", "password_is_default", "updated_at"])


def soft_delete_user(user_id: str, acting_user_id: str) -> str:
    """Soft-delete a user by setting ``deleted_at``.

    Applies **anti-lockout guards**: cannot delete self or the last admin.

    Args:
        user_id: UUID string of the user to delete.
        acting_user_id: UUID string of the admin performing the action.

    Returns:
        The deleted user's username (for flash messages).

    Raises:
        UserActionError: On self-delete or last-admin deletion.
    """
    if user_id == acting_user_id:
        raise UserActionError("You cannot delete your own account.")

    user = MantecatoUser.objects.filter(id=user_id, deleted_at__isnull=True).first()
    if user is None:
        raise UserActionError("User not found.")

    if user.role == "admin" and _active_admin_count() <= 1:
        raise UserActionError("Cannot delete the last admin.")

    user.deleted_at = timezone.now()
    user.save(update_fields=["deleted_at", "updated_at"])
    return user.username


def change_own_password(user: MantecatoUser, current_password: str, new_password: str) -> None:
    """Change the password for the given user after verifying the current one.

    Also clears the ``password_is_default`` flag.

    Args:
        user: The authenticated ``MantecatoUser`` instance.
        current_password: The current password for verification.
        new_password: The new raw password.

    Raises:
        UserActionError: If the current password is incorrect.
    """
    if not check_password(current_password, user.password):
        raise UserActionError("Current password is incorrect.")
    user.set_password(new_password)
    user.password_is_default = False
    user.save(update_fields=["password", "password_is_default", "updated_at"])
