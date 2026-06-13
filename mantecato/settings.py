"""Django settings for Mantecato v3.

Settings are loaded from environment variables (via ``.env`` file) with
sensible defaults for local development. See ``mantecato/config.py`` for
the database URL resolution and safety validation logic.

Sections:
    1. Environment helpers
    2. Core Django settings (DEBUG, SECRET_KEY, ALLOWED_HOSTS)
    3. Installed apps and middleware
    4. URL and template configuration
    5. Database configuration
    6. Authentication and session settings
    7. Internationalisation
    8. Static files
    9. Security hardening (HSTS, CSRF, SSL)
    10. Logging
"""

from __future__ import annotations

import logging
import os
import sys

import dj_database_url
from dotenv import load_dotenv

from mantecato.config import (
    BASE_DIR,
    get_database_url,
    get_secret_key,
    open_hosts_warning,
    require_database_url,
    validate_database_host,
)

# Load .env file before reading any environment variables.
load_dotenv(BASE_DIR / ".env")


# ============================================================================
# 1. Environment variable helpers
# ============================================================================


def _env_bool(name: str, *, default: bool = False) -> bool:
    """Read an environment variable as a boolean.

    Accepts ``true/1/yes`` (case-insensitive) as truthy and ``false/0/no``
    as falsy. Unset or unrecognised values return *default*.

    Args:
        name: Environment variable name.
        default: Fallback value if the variable is unset or unrecognised.

    Returns:
        The parsed boolean value.
    """
    val = os.environ.get(name, "").strip().lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def _env_str(name: str, default: str = "") -> str:
    """Read an environment variable as a string with optional default.

    Args:
        name: Environment variable name.
        default: Fallback value if the variable is unset.

    Returns:
        The environment variable's value, or *default*.
    """
    return os.environ.get(name, default)


def _env_int(name: str, *, default: int = 0) -> int:
    """Read an environment variable as an integer.

    Returns *default* if the variable is unset, empty, or not a valid integer.

    Args:
        name: Environment variable name.
        default: Fallback value if parsing fails.

    Returns:
        The parsed integer value.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, *, default: list[str] | None = None) -> list[str]:
    """Read an environment variable as a comma-separated list of strings.

    Whitespace around each item is stripped, and empty items are discarded.

    Args:
        name: Environment variable name.
        default: Fallback list if the variable is unset or empty.

    Returns:
        A list of non-empty, stripped strings.
    """
    raw = os.environ.get(name, "")
    if not raw:
        return default or []
    return [item.strip() for item in raw.split(",") if item.strip()]


# ============================================================================
# 2. Core Django settings
# ============================================================================

DEBUG = _env_bool("DEBUG", default=True)
# Warn (once, at startup) when DEBUG is on. It defaults to True for a friction-free
# local setup, but DEBUG in production leaks tracebacks/settings on errors — the
# deploy configs set DEBUG=False explicitly, so this surfaces a forgotten override.
if DEBUG:
    logging.getLogger("mantecato.security").warning(
        "DEBUG is enabled — do not run with DEBUG=True in production (it exposes "
        "tracebacks and settings on errors). Set DEBUG=0 for any public deployment."
    )

SECRET_KEY = get_secret_key()

# ALLOWED_HOSTS: open ("*") by default so a fresh deploy works without
# host configuration. Set the ALLOWED_HOSTS env var (comma-separated) to
# restrict. Note: "*" disables Django's Host-header validation; same-origin
# POSTs still work (Django matches Origin against the request host) — only
# cross-origin requests need CSRF_TRUSTED_ORIGINS (see below).
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS") or ["*"]

# Warn (once, at startup) when host validation is disabled. On Railway the
# message includes the exact value to set, derived from RAILWAY_PUBLIC_DOMAIN.
_hosts_warning = open_hosts_warning(ALLOWED_HOSTS)
if _hosts_warning:
    logging.getLogger("mantecato.security").warning(_hosts_warning)

# ============================================================================
# 3. Installed apps and middleware
# ============================================================================

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.common",
    "apps.core",
    "apps.analytics",
    "apps.dashboards",
    "apps.settings_app",
    "apps.api",
    "apps.tracker",
]

# Middleware stack order matters: security and compression first, then session,
# CSRF, auth, and finally the custom API key middleware at the end so it can
# read the already-authenticated user if present.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
]

# WhiteNoise serves static files in production (no separate nginx needed).
if not DEBUG:
    MIDDLEWARE.append("whitenoise.middleware.WhiteNoiseMiddleware")

MIDDLEWARE += [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom middleware: authenticates CLI/MCP requests via Bearer token.
    "mantecato.middleware.ApiKeyMiddleware",
    # Captures per-request DB query timings; adds Server-Timing header in DEBUG.
    "mantecato.middleware.QueryTimingMiddleware",
]

# Slow-query log threshold in milliseconds.  Queries exceeding this value
# are logged with WARNING by ``core.mantecato_core.database.raw_query``.
# Set to 0 to log every query (useful during local profiling), or raise it
# in production to reduce log noise.
SLOW_QUERY_THRESHOLD_MS = _env_int("SLOW_QUERY_THRESHOLD_MS", default=100)

# Exactness window for cookieless unique-visitor counting: "day" | "week" |
# "month". The dedup salt is stable for this window, so a visitor is counted
# once per window. Default "day" → unique visitors over a range = sum of daily
# uniques (the conventional, Umami-aligned figure). Use "month" for true
# monthly uniques (lower, no cross-day double counting). See docs/privacy.md.
VISITOR_EXACT_WINDOW = _env_str("VISITOR_EXACT_WINDOW", "day").strip().lower()

# How long the per-event dedup digest (``website_event.visitor_key``) is kept so
# exact visitor/visit/bounce counts can be computed — and **filtered** (by country,
# device, bot rules) — at read time, like the session-based product. After this the
# rollup folds the data into permanent anonymous aggregates and NULLs the digest.
# Default ≈13 months: the CNIL ceiling for a consent-free audience-measurement
# identifier. The window salt is still discarded at window end, so digests older
# than their window are no longer re-linkable to an IP/UA. See docs/privacy.md.
VISITOR_KEY_RETENTION_DAYS = _env_int("VISITOR_KEY_RETENTION_DAYS", default=396)

# A single-pageview visit counts as a bounce only if its real on-page (active)
# time stays below this many seconds — the "engaged bounce" definition powered by
# engagement beacons. Set to 0 for the classic Umami rule (single pageview =
# bounce regardless of time). The active time also drives accurate avg duration.
BOUNCE_ENGAGEMENT_THRESHOLD_S = _env_int("BOUNCE_ENGAGEMENT_THRESHOLD_S", default=10)

# Flag requests from known cloud/datacenter IP ranges as bots at ingestion (the
# IP is used transiently and never stored). Uses a bundled CIDR list with no
# external calls. Extend the list via DATACENTER_CIDRS (comma-separated CIDRs).
DETECT_DATACENTER_IPS = _env_bool("DETECT_DATACENTER_IPS", default=True)
DATACENTER_CIDRS = _env_list("DATACENTER_CIDRS", default=[])

# Trusted reverse-proxy configuration for client-IP extraction. The client IP
# is the input to the cookieless visitor digest, so a spoofable IP lets callers
# poison visitor counts and bypass datacenter-bot detection (see apps/tracker/ip.py).
#
#   TRUST_PROXY_HEADERS=False → ignore all forwarding headers and use the raw
#       socket peer (REMOTE_ADDR). Correct when the app is exposed directly.
#   TRUSTED_PROXY_COUNT=N (>0) → the app sits behind exactly N trusted proxies;
#       the real client is read spoof-resistantly from the right of the
#       X-Forwarded-For chain (and trusted CDN/custom headers are honoured).
#
# The default (headers trusted, count 0) preserves zero-config accuracy on PaaS
# like Railway, but X-Forwarded-For is then spoofable — the startup warning below
# recommends setting TRUSTED_PROXY_COUNT to harden visitor-IP handling.
TRUST_PROXY_HEADERS = _env_bool("TRUST_PROXY_HEADERS", default=True)
TRUSTED_PROXY_COUNT = _env_int("TRUSTED_PROXY_COUNT", default=0)
# Operator-configured single-valued client-IP header (e.g. for non-standard
# proxies). Read once here rather than per-request from os.environ.
CLIENT_IP_HEADER = _env_str("CLIENT_IP_HEADER", "").strip()
if TRUST_PROXY_HEADERS and TRUSTED_PROXY_COUNT <= 0:
    logging.getLogger("mantecato.security").warning(
        "Client-IP extraction trusts forwarding headers but TRUSTED_PROXY_COUNT is 0 "
        "— X-Forwarded-For is spoofable. Set TRUSTED_PROXY_COUNT to the number of "
        "reverse proxies in front of Mantecato (or TRUST_PROXY_HEADERS=0 if exposed "
        "directly) to harden visitor-IP handling."
    )

# Server-side privacy opt-out enforcement on the ingest endpoint. The browser
# tracker also checks these, but a non-cooperative client (curl, a forked
# script, the server SDK) can bypass that — so the guarantee is enforced here too.
#   RESPECT_GPC: honour the Global Privacy Control signal (``Sec-GPC: 1``). On by
#     default — GPC is a legally recognised opt-out and a core product promise.
#   RESPECT_DNT: honour the legacy Do-Not-Track header (``DNT: 1``). Opt-in, since
#     some browsers send DNT=1 by default which would drop most legitimate traffic.
RESPECT_GPC = _env_bool("RESPECT_GPC", default=True)
RESPECT_DNT = _env_bool("RESPECT_DNT", default=False)

# Reject ingest requests whose body exceeds this many bytes before parsing.
# Legitimate tracker payloads are well under 16 KB; the cap blocks memory-DoS
# via huge bodies on the unauthenticated /api/send endpoint.
INGEST_MAX_BODY_BYTES = _env_int("INGEST_MAX_BODY_BYTES", default=16384)

# Best-effort, per-process, per-client-IP rate limit (requests/minute) on the
# ingest endpoint. 0 disables it (default). NOTE: the limit is per gunicorn
# worker and keyed on the extracted client IP, so it is only meaningful once
# TRUSTED_PROXY_COUNT is set correctly (otherwise all traffic may share one IP);
# prefer a proxy/CDN-level limiter in production.
INGEST_RATE_LIMIT_PER_MINUTE = _env_int("INGEST_RATE_LIMIT_PER_MINUTE", default=0)

# ============================================================================
# 4. URL and template configuration
# ============================================================================

ROOT_URLCONF = "mantecato.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.default_password_warning",
            ],
        },
    },
]

WSGI_APPLICATION = "mantecato.wsgi.application"

# ============================================================================
# 5. Database configuration
# ============================================================================

DATABASE_URL = get_database_url(debug=DEBUG)
# Refuse the silent SQLite fallback in production: Mantecato is PostgreSQL-only.
# Skip during build-time commands (collectstatic) that don't need a database.
_is_build_command = len(sys.argv) > 1 and sys.argv[1] in ("collectstatic", "help", "version")
if not _is_build_command:
    require_database_url(DATABASE_URL, debug=DEBUG)
if DATABASE_URL:
    validate_database_host(DATABASE_URL, DEBUG)

# PostgreSQL when DATABASE_URL is set, otherwise SQLite for quick local setup.
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        engine="django.db.backends.postgresql",
    )
    if DATABASE_URL
    else {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "mantecato.sqlite3",
    },
}

if DATABASE_URL:
    # 5-second connect timeout to fail fast on unreachable hosts.
    DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = 5
    # Keep connections alive for 10 minutes to reduce per-request overhead.
    DATABASES["default"]["CONN_MAX_AGE"] = 600

# ============================================================================
# 6. Authentication and session settings
# ============================================================================

# Signed-cookie sessions: no server-side session table needed. The session
# payload is stored in the cookie itself, signed with SECRET_KEY.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

# Custom user model with UUID PK, username/password/role fields.
AUTH_USER_MODEL = "core.MantecatoUser"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# BCrypt preferred for password hashing (slower = more resistant to brute force).
# PBKDF2 kept as fallback for any legacy hashes during migration.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.BCryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# No password validators -- the platform is self-hosted and admin-managed.
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# ============================================================================
# 7. Internationalisation
# ============================================================================

LANGUAGE_CODE = _env_str("LANGUAGE_CODE", "en-us")

TIME_ZONE = _env_str("TIME_ZONE", "UTC")

USE_I18N = True

# Always use timezone-aware datetimes (critical for analytics date ranges).
USE_TZ = True

# ============================================================================
# 8. Static files
# ============================================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# In production, WhiteNoise serves compressed static files with cache-busting
# manifest hashes, eliminating the need for a separate static file server.
if not DEBUG:
    STORAGES = {
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# ============================================================================
# 9. Security hardening
# ============================================================================

CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")
# SSL and cookie security: enabled by default in production (DEBUG=False),
# disabled in development to allow plain HTTP on localhost.
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", default=not DEBUG)
# Exempt the health endpoint from the HTTPS redirect: platform health checkers
# (e.g. Railway) hit /health/ internally over plain HTTP without the
# X-Forwarded-Proto header, so a 301 redirect would be read as a failed check.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", default=not DEBUG)

# HSTS: 1 year in production, disabled in development.
SECURE_HSTS_SECONDS = _env_int("SECURE_HSTS_SECONDS", default=31536000 if not DEBUG else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=not DEBUG,
)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", default=False)

# For deployments behind a reverse proxy that terminates SSL (e.g. nginx,
# Cloudflare), trust the X-Forwarded-Proto header to detect HTTPS.
if _env_bool("USE_SECURE_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ============================================================================
# 10. Logging
# ============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG" if DEBUG else "INFO",
    },
}

# Default primary key type for Django models (BigAutoField = 64-bit integer).
# Note: the core analytics models use UUID PKs instead (managed by raw SQL).
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
