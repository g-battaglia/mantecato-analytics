"""Django models for the Mantecato analytics platform.

Mantecato owns the entire database schema.  All models are managed by Django
and have proper migrations.  Table and column names match the original Umami
schema so the raw-SQL query engine works without changes.

Model layout:

- :class:`MantecatoUser`: custom user (``AbstractBaseUser``) with UUID primary key.
- :class:`Team`, :class:`TeamUser`: team membership.
- :class:`Website`: tracked sites.
- :class:`Session`, :class:`WebsiteEvent`, :class:`EventData`, :class:`SessionData`,
  :class:`Revenue`, :class:`Segment`: analytics data (written by the tracker,
  read by the raw-SQL query engine).
- :class:`Report`: polymorphic configuration table.  Discriminated by the
  :attr:`Report.type` column whose allowed values are enumerated in
  :class:`ReportType`.
- :class:`Dashboard`, :class:`ApiKey`, :class:`BotConfig`,
  :class:`ScheduledExport`: proxy models over
  :class:`Report`, each combining :class:`ReportProxyMixin` (reflective
  ``to_dict``) with :class:`ReportProxyManager` (auto-filtered queryset).

The proxy unification keeps all six discriminated configuration entities on
the same physical ``report`` row while sharing one ``Manager`` implementation
and one ``to_dict`` implementation — driven by declarative class attributes
(``json_fields`` / ``json_params`` / ``json_renames``) instead of bespoke
methods per proxy.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from datetime import datetime


def _uuid_pk() -> models.UUIDField:
    """Return a UUID primary-key field with a fresh ``uuid4`` default.

    Centralised so every model uses the same field configuration. The
    ``editable=False`` flag prevents the admin or forms from exposing
    the PK for user input.

    Returns:
        A :class:`~django.db.models.UUIDField` configured as a primary key.
    """
    return models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


def _iso(value: datetime | None) -> str | None:
    """Render a datetime as an ISO-8601 string, or ``None``.

    Used by :meth:`ReportProxyMixin.to_dict` to serialise timestamps into
    the camelCase JSON shape consumed by the web UI and the JSON API.

    Args:
        value: A datetime instance, or ``None``.

    Returns:
        The ISO-formatted string, or ``None`` when *value* is falsy.
    """
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------


class MantecatoUserManager(BaseUserManager):
    """Manager that hashes passwords before persisting a ``MantecatoUser``.

    Provides the ``create_user`` / ``create_superuser`` contract expected
    by ``django.contrib.auth`` and by the ``createsuperuser`` management
    command.
    """

    def create_user(
        self,
        username: str,
        password: str | None = None,
        role: str = "user",
        **extra: Any,
    ) -> MantecatoUser:
        """Create and save a user with the given username and password.

        The password is hashed via ``set_password`` (PBKDF2 by default) so
        the raw value never touches the database.

        Args:
            username: Unique login identifier.
            password: Raw password string. ``None`` marks the account as
                unusable (no password login).
            role: ``"user"`` or ``"admin"``.
            **extra: Additional model fields forwarded to the constructor.

        Returns:
            The newly created :class:`MantecatoUser` instance.

        Raises:
            ValueError: If *username* is empty.
        """
        if not username:
            raise ValueError("Username is required.")
        user = self.model(username=username, role=role, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, username: str, password: str | None = None, **extra: Any
    ) -> MantecatoUser:
        """Create a user with ``role="admin"`` (staff + superuser privileges).

        Args:
            username: Unique login identifier.
            password: Raw password string.
            **extra: Additional model fields forwarded to ``create_user``.

        Returns:
            The newly created admin :class:`MantecatoUser` instance.
        """
        extra.setdefault("role", "admin")
        return self.create_user(username, password, **extra)


class MantecatoUser(AbstractBaseUser):
    """Custom user model with UUID primary key and role-based admin flag.

    ``is_staff`` / ``is_superuser`` are derived from ``role == "admin"`` to
    avoid the extra columns that Django's stock ``User`` requires; we never
    use the Django admin (see :mod:`mantecato.settings`).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=255, unique=True)
    role = models.CharField(max_length=50, default="user")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = MantecatoUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    @property
    def is_active(self) -> bool:
        """A user is active as long as they have not been soft-deleted."""
        return self.deleted_at is None

    @property
    def is_staff(self) -> bool:
        """Map the ``role`` column to Django's ``is_staff`` contract.

        Only ``"admin"`` role grants staff access. This drives
        :class:`~apps.common.mixins.OwnedReportQuerysetMixin` and the
        template ``{% if user.is_staff %}`` checks.
        """
        return self.role == "admin"

    @property
    def is_superuser(self) -> bool:
        """Alias for :attr:`is_staff` -- admins get full permissions."""
        return self.role == "admin"

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        """Return ``True`` for superusers (admins). Required by Django auth."""
        return self.is_superuser

    def has_module_perms(self, app_label: str) -> bool:
        """Return ``True`` for superusers (admins). Required by Django auth."""
        return self.is_superuser

    class Meta:
        db_table = "mantecato_user"

    def __str__(self) -> str:
        return self.username


# ---------------------------------------------------------------------------
# Team membership
# ---------------------------------------------------------------------------


class Team(models.Model):
    """A team that groups users for shared website access.

    Teams use an ``access_code`` (unique invite token) for self-service
    joining. Membership is tracked in :class:`TeamUser`.
    """

    id = _uuid_pk()
    name = models.CharField(max_length=50)
    access_code = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "team"

    def __str__(self) -> str:
        return self.name


class TeamUser(models.Model):
    """Membership row linking a :class:`MantecatoUser` to a :class:`Team`.

    Uses plain ``UUIDField`` references (not ``ForeignKey``) to maintain
    compatibility with the raw-SQL query engine that joins by UUID.
    """

    team_user_id = _uuid_pk()
    team_id = models.UUIDField()
    user_id = models.UUIDField()
    role = models.CharField(max_length=50, default="member")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "team_user"

    def __str__(self) -> str:
        return str(self.team_user_id)


# ---------------------------------------------------------------------------
# Analytics data tables
# ---------------------------------------------------------------------------


class Website(models.Model):
    """A tracked website whose events are collected by the JS tracker.

    The ``is_deleted`` flag enables soft deletion so historical analytics
    joins keep resolving. The ``share_id`` enables public dashboard links.
    """

    id = _uuid_pk()
    name = models.CharField(max_length=100)
    domain = models.CharField(max_length=500, null=True, blank=True)
    share_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    reset_at = models.DateTimeField(null=True, blank=True)
    user_id = models.UUIDField(null=True, blank=True)
    team_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "website"

    def __str__(self) -> str:
        return self.name


class Session(models.Model):
    """A visitor session, created on first pageview by the tracker.

    Carries device/browser/geo metadata snapshotted at session creation.
    Referenced by :class:`WebsiteEvent` rows via ``session_id``.
    """

    session_id = _uuid_pk()
    website_id = models.UUIDField()
    browser = models.CharField(max_length=20, null=True, blank=True)
    os = models.CharField(max_length=20, null=True, blank=True)
    device = models.CharField(max_length=20, null=True, blank=True)
    screen = models.CharField(max_length=11, null=True, blank=True)
    language = models.CharField(max_length=35, null=True, blank=True)
    country = models.CharField(max_length=2, null=True, blank=True)
    region = models.CharField(max_length=20, null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    distinct_id = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "session"
        indexes = [
            models.Index(fields=["country", "device"], name="idx_session_country_device"),
            models.Index(fields=["website_id"], name="idx_session_website_id"),
        ]

    def __str__(self) -> str:
        return str(self.session_id)


class WebsiteEvent(models.Model):
    """A pageview or custom event recorded by the JS tracker.

    ``event_type=1`` is a pageview; ``event_type=2`` is a custom event
    (identified by ``event_name``). The denormalised device/browser/geo
    columns duplicate the session data for query performance -- the raw
    SQL analytics queries can filter without joining ``session``.
    """

    event_id = _uuid_pk()
    website_id = models.UUIDField()
    session_id = models.UUIDField()
    visit_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    url_path = models.CharField(max_length=500)
    url_query = models.CharField(max_length=500, null=True, blank=True)
    referrer_path = models.CharField(max_length=500, null=True, blank=True)
    referrer_query = models.CharField(max_length=500, null=True, blank=True)
    referrer_domain = models.CharField(max_length=500, null=True, blank=True)
    page_title = models.CharField(max_length=500, null=True, blank=True)
    event_type = models.IntegerField(default=1)
    event_name = models.CharField(max_length=50, null=True, blank=True)
    tag = models.CharField(max_length=50, null=True, blank=True)
    hostname = models.CharField(max_length=100, null=True, blank=True)
    browser = models.CharField(max_length=20, null=True, blank=True)
    os = models.CharField(max_length=20, null=True, blank=True)
    device = models.CharField(max_length=20, null=True, blank=True)
    screen = models.CharField(max_length=11, null=True, blank=True)
    language = models.CharField(max_length=35, null=True, blank=True)
    country = models.CharField(max_length=2, null=True, blank=True)
    region = models.CharField(max_length=20, null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    utm_source = models.CharField(max_length=50, null=True, blank=True)
    utm_medium = models.CharField(max_length=50, null=True, blank=True)
    utm_campaign = models.CharField(max_length=50, null=True, blank=True)
    utm_content = models.CharField(max_length=50, null=True, blank=True)
    utm_term = models.CharField(max_length=50, null=True, blank=True)
    gclid = models.CharField(max_length=100, null=True, blank=True)
    fbclid = models.CharField(max_length=100, null=True, blank=True)
    msclkid = models.CharField(max_length=100, null=True, blank=True)
    ttclid = models.CharField(max_length=100, null=True, blank=True)
    twclid = models.CharField(max_length=100, null=True, blank=True)
    li_fat_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "website_event"
        indexes = [
            models.Index(
                fields=["website_id", "created_at", "event_type"],
                name="idx_we_website_created_type",
            ),
            models.Index(fields=["session_id"], name="idx_we_session_id"),
            models.Index(fields=["visit_id"], name="idx_we_visit_id"),
            # Partial covering index for pageview queries (event_type=1 is
            # ~95% of all analytics WHERE clauses).  ``INCLUDE`` lets the
            # planner serve common aggregations from the index alone.
            models.Index(
                fields=["website_id", "-created_at"],
                include=["visit_id", "session_id", "url_path"],
                condition=models.Q(event_type=1),
                name="idx_we_pageview_hot",
            ),
            # Partial index for custom events; ``event_name`` is added so
            # the planner can satisfy ``GROUP BY event_name`` directly.
            models.Index(
                fields=["website_id", "-created_at", "event_name"],
                condition=models.Q(event_type=2),
                name="idx_we_event_hot",
            ),
            # Supports LEAD/ROW_NUMBER PARTITION BY visit_id ORDER BY created_at
            # used by pageviews.py and engagement.py for in-visit sequences.
            models.Index(
                fields=["visit_id", "created_at"],
                condition=models.Q(event_type=1),
                name="idx_we_visit_created_pv",
            ),
        ]

    def __str__(self) -> str:
        return str(self.event_id)


class EventData(models.Model):
    """Key-value property attached to a :class:`WebsiteEvent`.

    Stores custom event properties sent via
    ``data-mantecato-event-*`` attributes. The ``data_type`` column
    determines which value column (``string_value``, ``number_value``,
    or ``date_value``) holds the actual data.
    """

    event_data_id = _uuid_pk()
    website_id = models.UUIDField()
    website_event_id = models.UUIDField()
    data_key = models.CharField(max_length=500)
    string_value = models.CharField(max_length=500, null=True, blank=True)
    number_value = models.DecimalField(null=True, blank=True, max_digits=30, decimal_places=10)
    date_value = models.DateTimeField(null=True, blank=True)
    data_type = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_data"
        indexes = [
            models.Index(fields=["website_event_id"], name="idx_ed_website_event_id"),
            models.Index(fields=["website_id", "created_at"], name="idx_ed_website_created"),
        ]

    def __str__(self) -> str:
        return str(self.event_data_id)


class SessionData(models.Model):
    """Key-value property attached to a :class:`Session`.

    Populated by the ``identify()`` call in the JS tracker, which lets
    sites associate session-level properties (e.g. plan tier, user role)
    with a visitor.
    """

    session_data_id = _uuid_pk()
    website_id = models.UUIDField()
    session_id = models.UUIDField()
    data_key = models.CharField(max_length=500)
    string_value = models.CharField(max_length=500, null=True, blank=True)
    number_value = models.DecimalField(null=True, blank=True, max_digits=30, decimal_places=10)
    date_value = models.DateTimeField(null=True, blank=True)
    data_type = models.IntegerField()
    distinct_id = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "session_data"
        indexes = [
            models.Index(fields=["session_id"], name="idx_sd_session_id"),
            # Without this, filtering session_data by website_id (used in
            # analytics joins) degrades to a sequential scan.
            models.Index(fields=["website_id"], name="idx_sd_website_id"),
        ]

    def __str__(self) -> str:
        return str(self.session_data_id)


class Revenue(models.Model):
    """Revenue event tied to a session and optionally to a specific event.

    Tracks monetary conversions with a decimal ``revenue`` amount and
    a 3-letter ISO ``currency`` code.
    """

    revenue_id = _uuid_pk()
    website_id = models.UUIDField()
    session_id = models.UUIDField()
    event_id = models.UUIDField(null=True, blank=True)
    event_name = models.CharField(max_length=50, null=True, blank=True)
    revenue = models.DecimalField(max_digits=30, decimal_places=10)
    currency = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "revenue"
        indexes = [
            # Revenue events are filtered by (website, date range) in every
            # analytics query; without this the table is fully scanned.
            models.Index(
                fields=["website_id", "-created_at"], name="idx_rev_website_created"
            ),
            # Join key when correlating revenue rows back to sessions.
            models.Index(fields=["website_id", "session_id"], name="idx_rev_session"),
        ]

    def __str__(self) -> str:
        return str(self.revenue_id)


class Segment(models.Model):
    """User segment definition for filtered analytics views.

    Segments store a set of filter rules (``name_filters`` JSON) that
    narrow the analytics data to a cohort of visitors matching certain
    criteria.
    """

    id = _uuid_pk()
    website_id = models.UUIDField()
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=100)
    name_filters = models.JSONField()
    modifier = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "segment"

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Umami import jobs (background, UI-triggered)
# ---------------------------------------------------------------------------


class UmamiImportJob(models.Model):
    """State of a UI-triggered, data-only Umami import running in a thread.

    The web UI starts a background import (see
    :func:`apps.core.services.run_umami_import_job`) and polls this row via
    HTMX to render a progress bar. State lives in the database — not in
    process memory — so any gunicorn worker can serve the poll regardless of
    which worker runs the import thread.

    Security: the source database DSN is **never** stored here. Only the
    non-sensitive parameters (the website UUIDs, the optional ``since`` cutoff
    and the ``replace`` flag) and progress counters are persisted.
    """

    id = _uuid_pk()
    user_id = models.UUIDField()
    status = models.CharField(max_length=20, default="pending")  # pending|running|success|error
    # Non-sensitive parameters (single-site remap). No DSN, ever.
    target_website_id = models.UUIDField()
    source_website_id = models.UUIDField()
    since = models.DateField(null=True, blank=True)
    replace = models.BooleanField(default=False)
    # Progress, written by the DBProgress adapter.
    current_table = models.CharField(max_length=50, null=True, blank=True)
    total_rows = models.BigIntegerField(default=0)
    imported_rows = models.BigIntegerField(default=0)
    error_message = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "umami_import_job"
        indexes = [models.Index(fields=["user_id", "-created_at"], name="idx_uij_user_created")]

    def __str__(self) -> str:
        return f"UmamiImportJob({self.id}, {self.status})"

    @property
    def is_active(self) -> bool:
        """Return ``True`` while the job is still pending or running.

        Drives the HTMX polling trigger in the progress partial: once the
        job reaches a terminal state (``success``/``error``) the trigger is
        dropped and polling stops on its own.
        """
        return self.status in ("pending", "running")


# ---------------------------------------------------------------------------
# Report table (polymorphic configuration store)
# ---------------------------------------------------------------------------


class ReportType(models.TextChoices):
    """Discriminator values for the polymorphic ``report.type`` column.

    Each member maps a typed Python identifier to the legacy string value
    persisted in the database. Use ``ReportType.DASHBOARD.value`` to obtain
    the raw string for ``WHERE type = ...`` clauses or ORM filters.

    Cross-refs:
        - :class:`ReportProxyManager`
        - :class:`Dashboard`, :class:`ApiKey`, :class:`BotConfig`,
          :class:`ScheduledExport`
    """

    DASHBOARD = "mantecato-dashboard", _("Dashboard")
    API_KEY = "api-key", _("API key")
    BOT_CONFIG = "mantecato-bot-config", _("Bot detection config")
    SCHEDULED_EXPORT = "mantecato-scheduled-export", _("Scheduled export")


# Public string aliases kept for any consumer that still imports the legacy
# constants. They simply forward to the enum so there is a single source of
# truth.
REPORT_TYPE_DASHBOARD = ReportType.DASHBOARD.value
REPORT_TYPE_API_KEY = ReportType.API_KEY.value
REPORT_TYPE_BOT_CONFIG = ReportType.BOT_CONFIG.value
REPORT_TYPE_SCHEDULED_EXPORT = ReportType.SCHEDULED_EXPORT.value


# Default bot-detection settings, merged into every BotConfig payload so the
# UI always receives a complete object even when only a few keys have been
# saved to the database.
# Mirrors ``DEFAULT_BOT_CONFIG`` from mantecato v2
# (``../mantecato/frontend/src/hooks/use-bot-config.ts``) so a site
# inherits the same baseline heuristics it had before upgrading.  The
# heavier subqueries (``clusterDetection``, ``highVelocityThreshold``) are
# on by default to preserve the v2 user experience; operators can dial
# them down per-site from the Bot Detection settings page if the cost
# becomes noticeable on large traffic volumes.
BOT_CONFIG_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "knownBots": True,
    "emptyUa": True,
    "clusterDetection": True,
    "clusterBounceThreshold": 90,
    "clusterMinSize": 100,
    "zeroEngagement": False,
    "minDuration": 0,
    "missingScreen": False,
    "missingLanguage": False,
    "highVelocityThreshold": 60,
    "excludedCountries": [],
}


def merge_bot_config(params: dict[str, Any]) -> dict[str, Any]:
    """Overlay *params* onto :data:`BOT_CONFIG_DEFAULTS`, dropping unknown keys.

    Args:
        params: Partial bot-config dict (typically from a form or JSON body).

    Returns:
        A new dict with every default key present, overlaid by the values
        from *params* when keys match. Keys not present in the defaults are
        silently discarded — this keeps the persisted config bounded.
    """
    merged = {**BOT_CONFIG_DEFAULTS}
    for key, value in params.items():
        if key in merged:
            merged[key] = value
    return merged


class Report(models.Model):
    """Polymorphic configuration row discriminated by :attr:`type`.

    Every per-user, per-website setting in Mantecato (dashboards, saved
    views, annotations, API keys, bot config, scheduled exports) is stored
    here. The proxy models below add type-specific managers and
    serialization without ever introducing new physical tables.
    """

    id = _uuid_pk()
    user_id = models.UUIDField()
    website_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=100, choices=ReportType.choices)
    description = models.CharField(max_length=500, null=True, blank=True)
    parameters = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "report"
        indexes = [
            models.Index(fields=["user_id", "type"], name="idx_report_user_type"),
            models.Index(fields=["website_id", "type"], name="idx_report_website_type"),
        ]

    def __str__(self) -> str:
        return f"{self.type}: {self.name}"


# ---------------------------------------------------------------------------
# Proxy infrastructure (manager + serialization mixin)
# ---------------------------------------------------------------------------


class ReportProxyManager(models.Manager):
    """Manager that filters by a specific :class:`ReportType` discriminator.

    One instantiation per proxy model replaces what used to be six near-identical
    ``_ReportTypeManager`` subclasses. Both the queryset filter and the ``create()``
    helper auto-set ``type`` so callers never have to think about the
    discriminator.

    Args:
        report_type: The :class:`ReportType` member identifying the proxy's rows.

    Example:
        .. code-block:: python

            class Dashboard(ReportProxyMixin, Report):
                objects = ReportProxyManager(ReportType.DASHBOARD)
                class Meta:
                    proxy = True

            Dashboard.objects.create(user_id=..., website_id=..., name="...")
            # The generated INSERT carries type='mantecato-dashboard'.
    """

    def __init__(self, report_type: ReportType) -> None:
        super().__init__()
        # Store the raw string once; this is what hits the DB column.
        self._report_type: str = report_type.value

    def get_queryset(self) -> models.QuerySet[Report]:
        """Return a queryset pre-filtered to the manager's discriminator."""
        return super().get_queryset().filter(type=self._report_type)

    def create(self, **kwargs: Any) -> Report:
        """Auto-set ``type`` to the manager's discriminator on every insert."""
        kwargs.setdefault("type", self._report_type)
        return super().create(**kwargs)


class ReportProxyMixin:
    """Reflective ``to_dict()`` driven by class-level metadata.

    Subclasses declare three class attributes:

    Attributes:
        json_fields (tuple[str, ...]): names of model fields to copy verbatim
            to the dict (UUID fields are stringified; ``None`` becomes
            ``""``).
        json_params (tuple[tuple[str, Any], ...]): pairs of
            ``(key, default)`` taken from the ``parameters`` JSON column.
        json_renames (dict[str, str]): rename map applied after ``json_fields``
            copying (e.g. ``{"name": "label"}``).

    ``createdAt`` and ``updatedAt`` are always appended (ISO-8601 strings).
    Subclasses may override :meth:`extra_dict_fields` to inject computed keys
    (used by :class:`BotConfig` to merge defaults).

    Example:
        .. code-block:: python

            class ApiKey(ReportProxyMixin, Report):
                json_fields = ("id", "name")
                json_params = (
                    ("prefix", "mtk_???"),
                    ("scopes", ["read"]),
                    ("createdAt", ""),
                    ("lastUsedAt", None),
                )
                objects = ReportProxyManager(ReportType.API_KEY)
                class Meta:
                    proxy = True
    """

    json_fields: ClassVar[tuple[str, ...]] = ()
    json_params: ClassVar[tuple[tuple[str, Any], ...]] = ()
    json_renames: ClassVar[dict[str, str]] = {}
    include_timestamps: ClassVar[bool] = True

    def to_dict(self) -> dict[str, Any]:
        """Serialise the proxy instance to a camelCase dict for API/template use.

        The serialisation is driven entirely by the three class-level
        declarations (:attr:`json_fields`, :attr:`json_params`,
        :attr:`json_renames`) so adding a new proxy model requires zero
        serialisation code -- just declare the metadata.

        Returns:
            A JSON-safe dict with stringified UUIDs, extracted
            ``parameters`` keys, computed fields from
            :meth:`extra_dict_fields`, and ISO timestamps.
        """
        out: dict[str, Any] = {}
        # Step 1: Copy declared model fields, applying renames (e.g.
        # "user_id" -> "userId") and stringifying UUIDs.
        for field in self.json_fields:
            key = self.json_renames.get(field, field)
            value = getattr(self, field)
            if hasattr(value, "hex"):  # UUID objects expose .hex
                out[key] = str(value)
            else:
                out[key] = value or ""
        # Step 2: Extract declared keys from the JSON ``parameters`` column,
        # falling back to the declared default when a key is missing.
        params = getattr(self, "parameters", None) or {}
        for key, default in self.json_params:
            out[key] = params.get(key, default)
        # Step 3: Let subclasses inject computed keys (e.g. merged config).
        out.update(self.extra_dict_fields())
        # Step 4: Append timestamps unless the proxy opts out (ApiKey does).
        if self.include_timestamps:
            out.setdefault("createdAt", _iso(getattr(self, "created_at", None)))
            out.setdefault("updatedAt", _iso(getattr(self, "updated_at", None)))
        return out

    def extra_dict_fields(self) -> dict[str, Any]:
        """Hook for proxies that need computed keys (e.g. merged config)."""
        return {}


# ---------------------------------------------------------------------------
# Report proxy models
# ---------------------------------------------------------------------------


class Dashboard(ReportProxyMixin, Report):
    """Custom dashboard (``report.type='mantecato-dashboard'``).

    ``parameters`` JSON shape::

        {
            "version": 1,
            "columns": 2,
            "widgets": [...],
            "dateRange": "30d"
        }

    Consumed by :mod:`apps.dashboards.views` and the JSON API CRUD endpoints
    in :mod:`apps.api.views`.
    """

    json_fields = ("id", "name", "description", "user_id", "website_id")
    json_renames = {
        "user_id": "userId",
        "website_id": "websiteId",
    }
    # Dashboard does not extract individual keys from parameters -- the
    # entire dict is exposed as "config" via extra_dict_fields.
    json_params: ClassVar[tuple[tuple[str, Any], ...]] = ()
    objects = ReportProxyManager(ReportType.DASHBOARD)

    class Meta:
        proxy = True

    def extra_dict_fields(self) -> dict[str, Any]:
        """Expose the full ``parameters`` dict as the ``config`` key."""
        return {"config": self.parameters or {}}


class ApiKey(ReportProxyMixin, Report):
    """API key (``report.type='api-key'``).

    ``parameters`` JSON shape::

        {
            "keyHash": "<sha256>",
            "prefix": "mtk_xxxxxxxx",
            "scopes": ["read", "write", "admin"],
            "createdAt": "YYYY-MM-DDTHH:MM:SSZ",
            "lastUsedAt": "YYYY-MM-DDTHH:MM:SSZ" | None
        }

    The raw key is shown to the user only once at creation time
    (:func:`apps.settings_app.services.generate_new_api_key`); afterwards the
    hash is what authenticates the request (see
    :func:`apps.core.api_keys.validate_api_key`).
    """

    json_fields = ("id", "name")
    json_params = (
        ("prefix", "mtk_???"),
        ("scopes", ["read"]),
        ("createdAt", ""),
        ("lastUsedAt", None),
    )
    include_timestamps = False
    objects = ReportProxyManager(ReportType.API_KEY)

    class Meta:
        proxy = True


class BotConfig(ReportProxyMixin, Report):
    """Per-website bot-detection config (``report.type='mantecato-bot-config'``).

    The dict returned by :meth:`to_dict` always carries the full set of keys
    defined in :data:`BOT_CONFIG_DEFAULTS` (via :func:`merge_bot_config`) so
    the form / JSON consumers never have to handle missing fields.
    """

    json_fields = ("id", "website_id")
    json_renames = {"website_id": "websiteId"}
    objects = ReportProxyManager(ReportType.BOT_CONFIG)

    class Meta:
        proxy = True

    def extra_dict_fields(self) -> dict[str, Any]:
        """Merge stored parameters with defaults so all keys are always present.

        This guarantees the form / JSON consumers never have to handle
        missing fields -- every key from :data:`BOT_CONFIG_DEFAULTS` is
        present in the returned ``config`` dict.

        Returns:
            A dict with a ``"config"`` key containing the merged config.
        """
        return {"config": merge_bot_config(self.parameters or {})}


class ScheduledExport(ReportProxyMixin, Report):
    """Scheduled CSV/JSON export job (``report.type='mantecato-scheduled-export'``).

    ``parameters`` holds the export specification (cadence, format, recipients).
    """

    json_fields = ("id", "name", "description", "user_id", "website_id")
    json_renames = {
        "user_id": "userId",
        "website_id": "websiteId",
    }
    objects = ReportProxyManager(ReportType.SCHEDULED_EXPORT)

    class Meta:
        proxy = True

    def extra_dict_fields(self) -> dict[str, Any]:
        """Expose the full ``parameters`` dict as the ``config`` key."""
        return {"config": self.parameters or {}}
