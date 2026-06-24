"""Django models for the Mantecato analytics platform — privacy-first, cookieless.

Mantecato is cookieless and stores no persistent per-person identifier. It does
produce **exact** daily unique-visitor/visit/bounce counts via a compute-and-
discard scheme: each request's (IP + User-Agent) is hashed with a random daily
salt into an ephemeral digest used only to deduplicate within the day; the salt
and digests are deleted by the nightly rollup, leaving only anonymous integer
aggregates. Only the referrer **domain** is kept (no full URL/UTM/click IDs); no
cross-day or cross-site linkage.

Model layout:

- :class:`MantecatoUser`: custom user (``AbstractBaseUser``) with UUID primary key.
- :class:`Team`, :class:`TeamUser`: team membership.
- :class:`Website`: tracked sites.
- :class:`WebsiteEvent`: anonymous pageview/custom-event rows (no session_id,
  no visit_id, no referrer, no UTM, no click IDs, no event payload).
- :class:`VisitorSalt`, :class:`VisitorDayState`, :class:`VisitorScopeState`:
  ephemeral compute-and-discard state for exact visitor/visit counting over the
  configured exactness window (deleted at rollup).
- :class:`VisitorDaily`, :class:`VisitorPeriod`: permanent, fully anonymous
  per-day and per-window count aggregates.
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
    """A pageview event — the core analytics data unit.

    Every row is an independent pageview or custom-event count. No session_id,
    visit_id, full referrer URL, UTM parameters, click IDs, or event payload
    data is stored, and no IP/User-Agent. Only the referrer **domain** is kept
    (for aggregate traffic-source breakdowns). The only per-person field is
    ``visitor_key``, an ephemeral window-salted dedup digest (not derived-
    reversibly from stored data) that the rollup NULLs once the window is
    finalised — so finalised rows are fully anonymous. It exists only to count
    exact unique visitors at any time granularity within the live window.

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
    is_bot = models.BooleanField(default=False, db_default=False)
    bot_reason = models.CharField(max_length=80, null=True, blank=True)
    # Ephemeral, window-salted dedup digest (NOT an IP/UA). Enables exact unique
    # visitors at ANY granularity (e.g. per hour) and realtime visitors-online.
    # NULLed by the rollup once the window is finalised → anonymous thereafter.
    visitor_key = models.CharField(max_length=64, null=True, blank=True)
    # Referrer **domain only** (e.g. "google.com") for aggregate traffic-source
    # breakdowns. The full referrer URL, path and query string are parsed
    # transiently at ingestion and never stored; same-site referrals are dropped
    # to NULL (counted as direct). No UTM/click IDs are collected.
    referrer_domain = models.CharField(max_length=255, null=True, blank=True)

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
            models.Index(
                fields=["website_id", "referrer_domain", "-created_at"],
                condition=models.Q(event_type=1),
                name="idx_we_referrer_hot",
            ),
            # The visitor read path orders/groups by visitor_key (unique visitors,
            # visits, realtime COUNT(DISTINCT)). Partial on the live (non-NULLed)
            # rows so the index stays small once the rollup discards keys past
            # retention. One per scope: pageviews (type 1) and custom events (type 2).
            models.Index(
                fields=["website_id", "visitor_key", "created_at"],
                condition=models.Q(event_type=1, visitor_key__isnull=False),
                name="idx_we_visitor_key_pv",
            ),
            models.Index(
                fields=["website_id", "visitor_key", "created_at"],
                condition=models.Q(event_type=2, visitor_key__isnull=False),
                name="idx_we_visitor_key_evt",
            ),
            # Retention sweep (``discard_expired_digests``) NULLs digests by age
            # alone — ``created_at < cutoff AND visitor_key IS NOT NULL``, no
            # ``website_id``/``event_type`` predicate — so it can't use the
            # website-led indexes above. This partial index is led by
            # ``created_at`` and scoped to the live (non-NULLed) rows, letting the
            # periodic UPDATE range-seek the expiring rows instead of scanning.
            models.Index(
                fields=["created_at"],
                condition=models.Q(visitor_key__isnull=False),
                name="idx_we_visitor_key_expiry",
            ),
        ]

    def __str__(self) -> str:
        return str(self.event_id)


class VisitorSalt(models.Model):
    """Per-exactness-window random salt for the compute-and-discard counter.

    The salt keys the HMAC that turns a request's (truncated IP + User-Agent) into
    an ephemeral, site-scoped dedup digest. ``period`` is the fixed monthly window
    key (e.g. ``"2026-06"``; legacy rows may carry ``"2026-W23"`` / ``"2026-06-08"``).
    The salt is created lazily on the first event of the month and **deleted** by the
    rollup once the month is finalised, so past digests can never be recomputed
    (forward secrecy). The salt is independent from ``SECRET_KEY``.
    """

    period = models.CharField(max_length=16, primary_key=True)
    salt = models.BinaryField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "visitor_salt"

    def __str__(self) -> str:
        return f"salt:{self.period}"


class VisitorDayState(models.Model):
    """Ephemeral per-visitor, per-day visit state for **exact** counting.

    One row per ``(site, day, visitor_key)``. ``visitor_key`` is stable for the
    whole exactness window (see :class:`VisitorSalt`), so counting distinct keys
    across the window's days yields exact window-unique visitors, while per-day
    rows keep visit/bounce/duration exact per day. Holds only aggregate counters
    and timestamps — **no** IP, User-Agent, or reversible identifier. Rows are
    deleted by the rollup once their window is finalised.
    """

    id = _uuid_pk()
    website_id = models.UUIDField()
    day = models.DateField()
    period = models.CharField(max_length=16, default="")
    # Hex-encoded HMAC-SHA256 digest (salt discarded at rollup → not reversible).
    visitor_key = models.CharField(max_length=64)
    # Entry (landing) path of the in-progress visit, for per-landing bounce rate.
    entry_path = models.CharField(max_length=500, null=True, blank=True)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    # Completed-visit counters plus the in-progress ("cur") visit.
    visits = models.IntegerField(default=1)
    bounces = models.IntegerField(default=0)
    cur_visit_pageviews = models.IntegerField(default=1)
    cur_visit_duration_s = models.IntegerField(default=0)
    # Cumulative active (engaged) seconds already credited for the CURRENT page,
    # advanced by engagement beacons; reset to 0 on each new pageview. Lets a
    # single-page visit accrue real on-page time (accurate duration + bounce).
    cur_page_engaged_s = models.IntegerField(default=0)
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
            models.Index(fields=["website_id", "period"], name="idx_vds_site_period"),
            models.Index(fields=["period"], name="idx_vds_period"),
        ]

    def __str__(self) -> str:
        return f"{self.website_id}:{self.day}:{self.visitor_key[:8]}"


class VisitorScopeState(models.Model):
    """Ephemeral per-(visitor, scope) presence for **exact** per-scope uniques.

    One row per ``(site, period, scope, scope_value, visitor_key)`` — i.e. "this
    visitor was seen on this page/section/event during this window". Counting
    distinct keys per ``scope_value`` gives exact per-page/section/event unique
    visitors for the window. Period-grained (not per-day) to bound storage to
    visitors×content. Deleted by the rollup; only integer counts survive in
    :class:`VisitorPeriod`.
    """

    id = _uuid_pk()
    website_id = models.UUIDField()
    period = models.CharField(max_length=16)
    scope = models.CharField(max_length=20)
    scope_value = models.CharField(max_length=500)
    visitor_key = models.CharField(max_length=64)

    class Meta:
        db_table = "visitor_scope_state"
        constraints = [
            models.UniqueConstraint(
                fields=["website_id", "period", "scope", "scope_value", "visitor_key"],
                name="uniq_visitor_scope_key",
            )
        ]
        indexes = [
            models.Index(
                fields=["website_id", "period", "scope"], name="idx_vss_site_period_scope"
            ),
            models.Index(fields=["period"], name="idx_vss_period"),
        ]

    def __str__(self) -> str:
        return f"{self.website_id}:{self.period}:{self.scope}:{self.scope_value}"


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
    # Reserved for a future bot-filter toggle beyond the retention window: the
    # intent is to store bot contribution separately so ``off`` shows human + bot
    # and ``on`` shows human only without re-deriving from the discarded digests.
    # NOT YET POPULATED — the rollup currently stores humans + bots combined and
    # the bot filter is applied at read time on the within-retention event rows
    # (see core/mantecato_core/queries/visitors.py). These stay 0 until wired up.
    bot_unique_visitors = models.IntegerField(default=0)
    bot_visits = models.IntegerField(default=0)
    bot_bounces = models.IntegerField(default=0)
    bot_total_pageviews = models.IntegerField(default=0)
    bot_total_duration_s = models.IntegerField(default=0)
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


class VisitorPeriod(models.Model):
    """Permanent, fully anonymous per-window aggregate — exact window uniques.

    ``unique_visitors`` is the exact distinct-visitor count for the whole
    exactness window (``period_start`` = first day of the window), computed at
    rollup before the digests are discarded. ``scope='site'`` holds the headline;
    ``page``/``section``/``event`` hold per-scope window uniques and ``landing``
    holds per-entry-page visits/bounces. Integer-only; nothing per-person.
    """

    id = _uuid_pk()
    website_id = models.UUIDField()
    period_start = models.DateField()
    scope = models.CharField(max_length=20, default="site")
    scope_value = models.CharField(max_length=500, blank=True, default="")
    unique_visitors = models.IntegerField(default=0)
    visits = models.IntegerField(default=0)
    bounces = models.IntegerField(default=0)
    total_pageviews = models.IntegerField(default=0)
    total_duration_s = models.IntegerField(default=0)
    # Reserved for a future bot-filter toggle beyond retention (see
    # :class:`VisitorDaily`). NOT YET POPULATED — stays 0 until wired into the rollup.
    bot_unique_visitors = models.IntegerField(default=0)
    bot_visits = models.IntegerField(default=0)
    bot_bounces = models.IntegerField(default=0)
    bot_total_pageviews = models.IntegerField(default=0)
    bot_total_duration_s = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "visitor_period"
        constraints = [
            models.UniqueConstraint(
                fields=["website_id", "period_start", "scope", "scope_value"],
                name="uniq_visitor_period_scope",
            )
        ]
        indexes = [
            models.Index(
                fields=["website_id", "scope", "period_start"],
                name="idx_vp_site_scope_period",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.website_id}:{self.period_start}:{self.scope}:{self.scope_value}"


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
    "datacenterIps": True,
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
