"""Django models for the Mantecato analytics platform — privacy-first, cookieless.

Mantecato is cookieless and stores no persistent per-person identifier. It does
produce **exact** daily unique-visitor/visit/bounce counts via a compute-and-
discard scheme: each request's (IP + User-Agent) is hashed with a random daily
salt into an ephemeral digest used only to deduplicate within the day; the salt
and digests are deleted by the nightly rollup, leaving only anonymous integer
aggregates. No referrer/UTM tracking, no cross-day or cross-site linkage.

Model layout:

- :class:`MantecatoUser`: custom user (``AbstractBaseUser``) with UUID primary key.
- :class:`Team`, :class:`TeamUser`: team membership.
- :class:`Website`: tracked sites.
- :class:`WebsiteEvent`: anonymous pageview/custom-event rows (no session_id,
  no visit_id, no referrer, no UTM, no click IDs, no event payload).
- :class:`VisitorDaySalt`, :class:`VisitorDayState`: ephemeral compute-and-
  discard state for exact same-day visitor/visit counting (deleted at rollup).
- :class:`VisitorDaily`: permanent, fully anonymous daily count aggregates.
- :class:`Report`: polymorphic configuration table.  Discriminated by the
  :attr:`Report.type` column whose allowed values are enumerated in
  :class:`ReportType`.
- :class:`Dashboard`, :class:`ApiKey`, :class:`BotConfig`,
  :class:`ScheduledExport`: proxy models over
  :class:`Report`, each combining :class:`ReportProxyMixin` (reflective
  ``to_dict``) with :class:`ReportProxyManager` (auto-filtered queryset).
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
    """Return a UUID primary-key field with a fresh ``uuid4`` default."""
    return models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


def _visitor_sketch_registers() -> bytes:
    """Return empty HyperLogLog registers for anonymous reach estimation."""
    return bytes(128)


def _iso(value: datetime | None) -> str | None:
    """Render a datetime as an ISO-8601 string, or ``None``."""
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------


class MantecatoUserManager(BaseUserManager):
    """Manager that hashes passwords before persisting a ``MantecatoUser``."""

    def create_user(
        self,
        username: str,
        password: str | None = None,
        role: str = "user",
        **extra: Any,
    ) -> MantecatoUser:
        if not username:
            raise ValueError("Username is required.")
        user = self.model(username=username, role=role, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, username: str, password: str | None = None, **extra: Any
    ) -> MantecatoUser:
        extra.setdefault("role", "admin")
        return self.create_user(username, password, **extra)


class MantecatoUser(AbstractBaseUser):
    """Custom user model with UUID primary key and role-based admin flag."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=255, unique=True)
    role = models.CharField(max_length=50, default="user")
    password_is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = MantecatoUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None

    @property
    def is_staff(self) -> bool:
        return self.role == "admin"

    @property
    def is_superuser(self) -> bool:
        return self.role == "admin"

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        return self.is_superuser

    def has_module_perms(self, app_label: str) -> bool:
        return self.is_superuser

    class Meta:
        db_table = "mantecato_user"

    def __str__(self) -> str:
        return self.username


# ---------------------------------------------------------------------------
# Team membership
# ---------------------------------------------------------------------------


class Team(models.Model):
    """A team that groups users for shared website access."""

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
    """Membership row linking a :class:`MantecatoUser` to a :class:`Team`."""

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
    """A tracked website whose pageviews are collected by the tracker."""

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


class WebsiteEvent(models.Model):
    """An anonymous pageview event — the core aggregate analytics data unit.

    Every row is an independent, standalone pageview or custom-event count. No
    session_id, visit_id, referrer, UTM parameters, click IDs, or event payload
    data is stored.

    Device/browser metadata is stored directly on the event for aggregate
    breakdown queries (no session join needed). Geo data comes from IP
    resolution at ingestion time.
    """

    event_id = _uuid_pk()
    website_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    url_path = models.CharField(max_length=500)
    url_query = models.CharField(max_length=500, null=True, blank=True)
    page_title = models.CharField(max_length=500, null=True, blank=True)
    event_type = models.IntegerField(default=1)
    event_name = models.CharField(max_length=100, null=True, blank=True)
    hostname = models.CharField(max_length=100, null=True, blank=True)
    # Device/browser metadata for aggregate breakdowns and bot detection
    browser = models.CharField(max_length=20, null=True, blank=True)
    os = models.CharField(max_length=20, null=True, blank=True)
    device = models.CharField(max_length=20, null=True, blank=True)
    # Geo: country-only (ISO 3166-1 alpha-2) to prevent re-identification
    country = models.CharField(max_length=2, null=True, blank=True)
    # Aggregate bot classification. The raw User-Agent is never stored.
    is_bot = models.BooleanField(default=False)
    bot_reason = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        db_table = "website_event"
        indexes = [
            models.Index(
                fields=["website_id", "created_at", "event_type"],
                name="idx_we_website_created_type",
            ),
            models.Index(
                fields=["website_id", "-created_at"],
                include=["url_path", "is_bot"],
                condition=models.Q(event_type=1),
                name="idx_we_pageview_hot",
            ),
            models.Index(
                fields=["website_id", "is_bot", "-created_at"],
                condition=models.Q(event_type=1),
                name="idx_we_bot_hot",
            ),
            models.Index(
                fields=["website_id", "event_name", "-created_at"],
                condition=models.Q(event_type=2),
                name="idx_we_event_name_hot",
            ),
        ]

    def __str__(self) -> str:
        return str(self.event_id)


class VisitorDaySalt(models.Model):
    """Per-UTC-day random salt for the exact compute-and-discard counter.

    The salt keys the HMAC that turns a request's (IP + User-Agent) into a
    daily, site-scoped dedup digest. It is created lazily on the first event of
    each day and **deleted** by the nightly rollup once that day is finalised,
    so past digests can never be recomputed (forward secrecy). The salt is
    independent from ``SECRET_KEY``.
    """

    day = models.DateField(primary_key=True)
    salt = models.BinaryField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "visitor_day_salt"

    def __str__(self) -> str:
        return f"salt:{self.day}"


class VisitorDayState(models.Model):
    """Ephemeral per-visitor, per-day state for **exact** visit/bounce counting.

    One row per distinct daily visitor digest. Holds only aggregate counters
    and timestamps needed to compute exact unique visitors, visits, bounce
    rate, pages-per-visit and on-site duration for the day. It stores **no** IP,
    User-Agent, or reversible identifier — only the salted ``visitor_key`` whose
    salt is discarded at rollup. Rows are deleted by the nightly rollup after
    being aggregated into :class:`VisitorDaily`.
    """

    id = _uuid_pk()
    website_id = models.UUIDField()
    day = models.DateField()
    # Hex-encoded HMAC-SHA256 digest (salt discarded daily → not reversible).
    visitor_key = models.CharField(max_length=64)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    # Completed-visit counters plus the in-progress ("cur") visit.
    visits = models.IntegerField(default=1)
    bounces = models.IntegerField(default=0)
    cur_visit_pageviews = models.IntegerField(default=1)
    cur_visit_duration_s = models.IntegerField(default=0)
    total_pageviews = models.IntegerField(default=1)
    total_duration_s = models.IntegerField(default=0)

    class Meta:
        db_table = "visitor_day_state"
        constraints = [
            models.UniqueConstraint(
                fields=["website_id", "day", "visitor_key"],
                name="uniq_visitor_day_key",
            )
        ]
        indexes = [
            models.Index(fields=["website_id", "day"], name="idx_vds_site_day"),
            models.Index(fields=["day"], name="idx_vds_day"),
        ]

    def __str__(self) -> str:
        return f"{self.website_id}:{self.day}:{self.visitor_key[:8]}"


class VisitorDaily(models.Model):
    """Permanent, fully anonymous daily aggregate — the rollup target.

    Stores only integer counts per website/day/scope. There is nothing
    per-person here: it is the irreversible result of discarding the daily
    digests. ``scope='site'`` holds the headline totals; page/section/entry
    scopes (added later) hold per-page breakdowns.
    """

    id = _uuid_pk()
    website_id = models.UUIDField()
    day = models.DateField()
    scope = models.CharField(max_length=20, default="site")
    scope_value = models.CharField(max_length=500, blank=True, default="")
    unique_visitors = models.IntegerField(default=0)
    visits = models.IntegerField(default=0)
    bounces = models.IntegerField(default=0)
    total_pageviews = models.IntegerField(default=0)
    total_duration_s = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "visitor_daily"
        constraints = [
            models.UniqueConstraint(
                fields=["website_id", "day", "scope", "scope_value"],
                name="uniq_visitor_daily_scope",
            )
        ]
        indexes = [
            models.Index(
                fields=["website_id", "scope", "day"],
                name="idx_vd_site_scope_day",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.website_id}:{self.day}:{self.scope}:{self.scope_value}"


# ---------------------------------------------------------------------------
# Umami import jobs (background, UI-triggered)
# ---------------------------------------------------------------------------


class UmamiImportJob(models.Model):
    """State of a UI-triggered, data-only Umami import running in a thread.

    Imports only aggregate pageview data (url_path, url_query, page_title,
    hostname, device/browser/geo metadata). No session, visitor, referrer,
    UTM, or click ID data is imported.
    """

    id = _uuid_pk()
    user_id = models.UUIDField()
    status = models.CharField(max_length=20, default="pending")  # pending|running|success|error
    target_website_id = models.UUIDField()
    source_website_id = models.UUIDField()
    since = models.DateField(null=True, blank=True)
    replace = models.BooleanField(default=False)
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
        return self.status in ("pending", "running")


# ---------------------------------------------------------------------------
# Report table (polymorphic configuration store)
# ---------------------------------------------------------------------------


class ReportType(models.TextChoices):
    """Discriminator values for the polymorphic ``report.type`` column."""

    DASHBOARD = "mantecato-dashboard", _("Dashboard")
    API_KEY = "api-key", _("API key")
    BOT_CONFIG = "mantecato-bot-config", _("Bot detection config")
    SCHEDULED_EXPORT = "mantecato-scheduled-export", _("Scheduled export")


REPORT_TYPE_DASHBOARD = ReportType.DASHBOARD.value
REPORT_TYPE_API_KEY = ReportType.API_KEY.value
REPORT_TYPE_BOT_CONFIG = ReportType.BOT_CONFIG.value
REPORT_TYPE_SCHEDULED_EXPORT = ReportType.SCHEDULED_EXPORT.value


BOT_CONFIG_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "knownBots": True,
    "emptyUa": True,
    "excludedCountries": [],
}


def merge_bot_config(params: dict[str, Any]) -> dict[str, Any]:
    """Overlay *params* onto :data:`BOT_CONFIG_DEFAULTS`, dropping unknown keys."""
    merged = {**BOT_CONFIG_DEFAULTS}
    for key, value in params.items():
        if key in merged:
            merged[key] = value
    return merged


class Report(models.Model):
    """Polymorphic configuration row discriminated by :attr:`type`."""

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
    """Manager that filters by a specific :class:`ReportType` discriminator."""

    def __init__(self, report_type: ReportType) -> None:
        super().__init__()
        self._report_type: str = report_type.value

    def get_queryset(self) -> models.QuerySet[Report]:
        return super().get_queryset().filter(type=self._report_type)

    def create(self, **kwargs: Any) -> Report:
        kwargs.setdefault("type", self._report_type)
        return super().create(**kwargs)


class ReportProxyMixin:
    """Reflective ``to_dict()`` driven by class-level metadata."""

    json_fields: ClassVar[tuple[str, ...]] = ()
    json_params: ClassVar[tuple[tuple[str, Any], ...]] = ()
    json_renames: ClassVar[dict[str, str]] = {}
    include_timestamps: ClassVar[bool] = True

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field in self.json_fields:
            key = self.json_renames.get(field, field)
            value = getattr(self, field)
            if hasattr(value, "hex"):
                out[key] = str(value)
            else:
                out[key] = value or ""
        params = getattr(self, "parameters", None) or {}
        for key, default in self.json_params:
            out[key] = params.get(key, default)
        out.update(self.extra_dict_fields())
        if self.include_timestamps:
            out.setdefault("createdAt", _iso(getattr(self, "created_at", None)))
            out.setdefault("updatedAt", _iso(getattr(self, "updated_at", None)))
        return out

    def extra_dict_fields(self) -> dict[str, Any]:
        return {}


# ---------------------------------------------------------------------------
# Report proxy models
# ---------------------------------------------------------------------------


class Dashboard(ReportProxyMixin, Report):
    """Custom dashboard (``report.type='mantecato-dashboard'``)."""

    json_fields = ("id", "name", "description", "user_id", "website_id")
    json_renames = {
        "user_id": "userId",
        "website_id": "websiteId",
    }
    json_params: ClassVar[tuple[tuple[str, Any], ...]] = ()
    objects = ReportProxyManager(ReportType.DASHBOARD)

    class Meta:
        proxy = True

    def extra_dict_fields(self) -> dict[str, Any]:
        return {"config": self.parameters or {}}


class ApiKey(ReportProxyMixin, Report):
    """API key (``report.type='api-key'``)."""

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
    """Per-website bot-detection config (``report.type='mantecato-bot-config'``)."""

    json_fields = ("id", "website_id")
    json_renames = {"website_id": "websiteId"}
    objects = ReportProxyManager(ReportType.BOT_CONFIG)

    class Meta:
        proxy = True

    def extra_dict_fields(self) -> dict[str, Any]:
        return {"config": merge_bot_config(self.parameters or {})}


class ScheduledExport(ReportProxyMixin, Report):
    """Scheduled CSV/JSON export job (``report.type='mantecato-scheduled-export'``)."""

    json_fields = ("id", "name", "description", "user_id", "website_id")
    json_renames = {
        "user_id": "userId",
        "website_id": "websiteId",
    }
    objects = ReportProxyManager(ReportType.SCHEDULED_EXPORT)

    class Meta:
        proxy = True

    def extra_dict_fields(self) -> dict[str, Any]:
        return {"config": self.parameters or {}}
