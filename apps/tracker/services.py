"""Tracker ingestion services -- write events, event data, revenue, and session data.

This module is the write-path core of the analytics pipeline. It receives
validated payloads from :mod:`apps.tracker.views` and inserts rows into the
analytics tables (``website_event``, ``event_data``, ``revenue``,
``session_data``) using raw SQL via :func:`core.mantecato_core.database.raw_query`.

Data flow:
    1. ``IngestView.post()`` calls :func:`ingest_event` or :func:`ingest_identify`.
    2. :func:`ingest_event` parses the URL/referrer/UTM fields, inserts a
       ``website_event`` row, and optionally writes ``event_data`` and
       ``revenue`` rows in the same transaction.
    3. :func:`ingest_identify` updates the session's ``distinct_id`` and
       writes key-value pairs into ``session_data``.

All inserts use parameterized queries with Mantecato's ``{{param}}`` template
syntax (processed by the raw_query engine into proper ``$1, $2, ...`` bind
params for psycopg3). This prevents SQL injection on untrusted tracker input.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from django.db import transaction
from django.utils import timezone

from core.mantecato_core.database import raw_query

# Standard UTM campaign tracking parameters extracted from the page URL.
_UTM_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")

# Ad platform click identifiers -- each ad network injects its own click ID
# into the landing page URL for conversion attribution.
_CLICK_ID_PARAMS = ("gclid", "fbclid", "msclkid", "ttclid", "twclid", "li_fat_id")

# Mantecato uses Umami's ``data_type`` enum for the ``event_data`` and
# ``session_data`` tables: 1 = string, 2 = number, 3 = date (date is unused
# in the current ingestion path but reserved for future use).
_DATA_TYPE_STRING = 1
_DATA_TYPE_NUMBER = 2


def _coerce_event_value(value: object) -> tuple[str | None, float | int | None, int]:
    """Coerce an arbitrary event-data value into ``(string_val, number_val, data_type)``.

    Mirrors the Umami contract: numeric values are stored in ``number_value``
    with ``data_type = 2``; everything else (including booleans, normalised
    to lowercase strings) goes into ``string_value`` with ``data_type = 1``,
    truncated to 500 chars to match the column width.
    """
    # NB: ``isinstance(True, int)`` is True; check ``bool`` first so booleans
    # are coerced to "true"/"false" rather than 1/0.
    if isinstance(value, bool):
        return str(value).lower(), None, _DATA_TYPE_STRING
    if isinstance(value, (int, float)):
        return None, value, _DATA_TYPE_NUMBER
    if value is None:
        return None, None, _DATA_TYPE_STRING
    return str(value)[:500], None, _DATA_TYPE_STRING


def _parse_url(url: str) -> dict[str, str | None]:
    """Parse a page URL into its path and query string components.

    Handles several edge cases from real-world tracker payloads:
    - Empty URLs default to ``/`` (e.g. single-page apps that send no URL).
    - The literal path ``/undefined`` (sent by some broken JS trackers) is
      normalised to ``/``.
    - URL fragments (``#hash``) are appended to the path because they are
      significant for SPA routing (e.g. ``/app#/settings``).
    - Percent-encoded characters are decoded for human-readable storage.
    - Both path and query are truncated to 500 chars to match column width.

    Args:
        url: The raw page URL from the tracker payload (may be empty).

    Returns:
        A dict with ``url_path`` (always a non-empty string) and
        ``url_query`` (the query string without ``?``, or ``None``).
    """
    if not url:
        return {"url_path": "/", "url_query": None}
    parsed = urlparse(url)
    path = parsed.path or "/"
    # Some broken tracker implementations send "/undefined" as the path
    if path == "/undefined":
        path = "/"
    # Preserve hash fragments -- they carry routing state in SPAs
    if parsed.fragment:
        path = f"{path}#{parsed.fragment}"
    path = unquote(path)
    query = parsed.query or None
    return {"url_path": path[:500], "url_query": query[:500] if query else None}


def _parse_referrer(referrer: str) -> dict[str, str | None]:
    """Parse a referrer URL into domain, path, and query components.

    The ``www.`` prefix is stripped from the domain so that
    ``www.google.com`` and ``google.com`` are aggregated together in
    source reports.

    Args:
        referrer: The raw ``document.referrer`` value from the tracker
            payload. Empty or absent referrers represent direct traffic.

    Returns:
        A dict with ``referrer_domain`` (netloc without ``www.``),
        ``referrer_path``, and ``referrer_query``. All values are ``None``
        when the referrer is empty (direct traffic).
    """
    if not referrer:
        return {"referrer_path": None, "referrer_query": None, "referrer_domain": None}
    parsed = urlparse(referrer)
    domain = parsed.netloc or None
    # Strip "www." prefix so referrer aggregation groups both variants together
    if domain and domain.startswith("www."):
        domain = domain[4:]
    return {
        "referrer_path": (parsed.path or None),
        "referrer_query": (parsed.query or None),
        "referrer_domain": domain,
    }


def _extract_utm_and_clicks(url: str) -> dict[str, str | None]:
    """Extract UTM campaign parameters and ad-platform click IDs from a URL.

    Parses the query string of the page URL to pull out marketing attribution
    data. UTM values are truncated to 50 chars and click IDs to 100 chars to
    match the column widths in ``website_event``.

    Args:
        url: The raw page URL. An empty URL yields all-``None`` values
            (representing organic/direct traffic with no campaign tags).

    Returns:
        A dict keyed by parameter name (e.g. ``"utm_source"``, ``"gclid"``)
        with the extracted string value or ``None`` if the param was absent.
    """
    result: dict[str, str | None] = {}
    if not url:
        # No URL means no query string -- all params are absent
        for key in _UTM_PARAMS + _CLICK_ID_PARAMS:
            result[key] = None
        return result

    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=False)

    # UTM params are capped at 50 chars (standard campaign tag length)
    for param in _UTM_PARAMS:
        vals = qs.get(param, [])
        result[param] = vals[0][:50] if vals else None

    # Click IDs are longer opaque tokens -- cap at 100 chars
    for param in _CLICK_ID_PARAMS:
        vals = qs.get(param, [])
        result[param] = vals[0][:100] if vals else None

    return result


@transaction.atomic
def ingest_event(
    website_id: str,
    session_id: str,
    visit_id: str,
    payload: dict[str, Any],
    device_info: dict[str, str | None],
    geo_info: tuple[str | None, str | None, str | None],
) -> None:
    """Insert a pageview or custom event with its associated data in one transaction.

    This is the primary write-path entry point for the tracker. It inserts a
    single row into ``website_event`` and, when the payload includes custom
    properties or revenue data, also writes to ``event_data`` and ``revenue``
    respectively. All inserts are wrapped in a single DB transaction so that
    partial writes never occur.

    The Umami wire protocol distinguishes pageviews (``event_type = 1``) from
    named custom events (``event_type = 2``) by the presence of a ``name``
    field in the payload.

    Args:
        website_id: UUID of the website this event belongs to.
        session_id: UUID of the resolved session (deterministic, see
            :mod:`apps.tracker.session`).
        visit_id: UUID of the current visit within the session.
        payload: The ``payload`` object from the tracker wire format. Expected
            keys include ``url``, ``referrer``, ``title``, ``name`` (for custom
            events), ``hostname``, ``screen``, ``language``, ``tag``, ``data``
            (custom properties dict), and ``revenue`` (revenue dict).
        device_info: Dict with ``browser``, ``os``, ``device`` from UA parsing.
        geo_info: Tuple of ``(country, region, city)`` ISO codes from geo
            resolution.
    """
    event_id = str(uuid.uuid4())
    now = timezone.now()

    event_name = payload.get("name")
    # Umami convention: type 1 = pageview (no name), type 2 = custom event (has name)
    event_type = 2 if event_name else 1

    # Parse the page URL, referrer, and marketing attribution params
    url_info = _parse_url(payload.get("url", ""))
    ref_info = _parse_referrer(payload.get("referrer", ""))
    utm_clicks = _extract_utm_and_clicks(payload.get("url", ""))
    country, region, city = geo_info

    raw_query(
        """
        INSERT INTO website_event
            (event_id, website_id, session_id, visit_id, created_at,
             url_path, url_query, referrer_path, referrer_query, referrer_domain,
             page_title, event_type, event_name, tag, hostname,
             browser, os, device, screen, language,
             country, region, city,
             utm_source, utm_medium, utm_campaign, utm_content, utm_term,
             gclid, fbclid, msclkid, ttclid, twclid, li_fat_id)
        VALUES
            ({{eventId::uuid}}, {{websiteId::uuid}}, {{sessionId::uuid}},
             {{visitId::uuid}}, {{createdAt::timestamptz}},
             {{urlPath}}, {{urlQuery}}, {{referrerPath}}, {{referrerQuery}},
             {{referrerDomain}}, {{pageTitle}}, {{eventType}}, {{eventName}},
             {{tag}}, {{hostname}},
             {{browser}}, {{os}}, {{device}}, {{screen}}, {{language}},
             {{country}}, {{region}}, {{city}},
             {{utmSource}}, {{utmMedium}}, {{utmCampaign}}, {{utmContent}},
             {{utmTerm}}, {{gclid}}, {{fbclid}}, {{msclkid}}, {{ttclid}},
             {{twclid}}, {{liFatId}})
        """,
        {
            "eventId": event_id,
            "websiteId": website_id,
            "sessionId": session_id,
            "visitId": visit_id,
            "createdAt": now,
            "urlPath": url_info["url_path"],
            "urlQuery": url_info["url_query"],
            "referrerPath": ref_info["referrer_path"],
            "referrerQuery": ref_info["referrer_query"],
            "referrerDomain": ref_info["referrer_domain"],
            "pageTitle": unquote(payload.get("title") or "")[:500] or None,
            "eventType": event_type,
            "eventName": (event_name or "")[:50] or None,
            "tag": (payload.get("tag") or "")[:50] or None,
            "hostname": ((payload.get("hostname") or "").removeprefix("www."))[:100] or None,
            "browser": device_info.get("browser"),
            "os": device_info.get("os"),
            "device": device_info.get("device"),
            "screen": (payload.get("screen") or "")[:11] or None,
            "language": (payload.get("language") or "")[:35] or None,
            "country": country,
            "region": region,
            "city": city,
            "utmSource": utm_clicks["utm_source"],
            "utmMedium": utm_clicks["utm_medium"],
            "utmCampaign": utm_clicks["utm_campaign"],
            "utmContent": utm_clicks["utm_content"],
            "utmTerm": utm_clicks["utm_term"],
            "gclid": utm_clicks["gclid"],
            "fbclid": utm_clicks["fbclid"],
            "msclkid": utm_clicks["msclkid"],
            "ttclid": utm_clicks["ttclid"],
            "twclid": utm_clicks["twclid"],
            "liFatId": utm_clicks["li_fat_id"],
        },
    )

    # Write custom event properties (key-value pairs) if the tracker sent any.
    # The ``data`` field is an arbitrary dict attached to the event by the
    # site's JS code via ``mantecato.track("event", { data: {...} })``.
    data = payload.get("data")
    if data and isinstance(data, dict):
        _insert_event_data(website_id, event_id, data, now)

    # Write revenue data if the tracker sent a ``revenue`` object.
    # Revenue events link an amount+currency to the event for e-commerce analytics.
    revenue_data = payload.get("revenue")
    if revenue_data and isinstance(revenue_data, dict):
        _insert_revenue(website_id, session_id, event_id, event_name, revenue_data, now)


def _insert_event_data(website_id: str, event_id: str, data: dict[str, Any], now: Any) -> None:
    """Write custom event properties as key-value rows into ``event_data``.

    Each key in the ``data`` dict becomes a separate row in ``event_data``,
    with the value coerced into either ``string_value`` or ``number_value``
    depending on its Python type (see :func:`_coerce_event_value`).

    To prevent abuse from untrusted tracker input, the number of keys is
    capped at 50 and each key name is truncated to 500 characters.

    The insert is done as a single multi-row ``INSERT`` statement for
    performance (one round-trip instead of N). Each row gets a fresh UUID
    as its primary key.

    Args:
        website_id: UUID of the website the event belongs to.
        event_id: UUID of the parent ``website_event`` row.
        data: Arbitrary key-value dict from the tracker payload's ``data``
            field. Values can be strings, numbers, booleans, or None.
        now: Timezone-aware datetime for the ``created_at`` column.
    """
    if not data:
        return
    # Cap at 50 keys to bound query size from untrusted input
    if len(data) > 50:
        data = dict(list(data.items())[:50])

    # Build a multi-row VALUES clause with parameterized placeholders.
    # Each key-value pair gets its own indexed set of params (did0, dk0, sv0, etc.)
    # to avoid name collisions while keeping everything in a single INSERT.
    value_clauses: list[str] = []
    params: dict[str, Any] = {
        "websiteId": website_id,
        "eventId": event_id,
        "createdAt": now,
    }
    for i, (key, value) in enumerate(data.items()):
        string_val, number_val, data_type = _coerce_event_value(value)
        value_clauses.append(
            f"({{{{did{i}::uuid}}}}, {{{{websiteId::uuid}}}},"
            f" {{{{eventId::uuid}}}}, {{{{dk{i}}}}},"
            f" {{{{sv{i}}}}}, {{{{nv{i}}}}}, NULL,"
            f" {{{{dt{i}}}}}, {{{{createdAt::timestamptz}}}})"
        )
        params[f"did{i}"] = str(uuid.uuid4())
        params[f"dk{i}"] = key[:500]
        params[f"sv{i}"] = string_val
        params[f"nv{i}"] = number_val
        params[f"dt{i}"] = data_type

    raw_query(
        "INSERT INTO event_data"
        " (event_data_id, website_id, website_event_id, data_key,"
        "  string_value, number_value, date_value, data_type, created_at)"
        f" VALUES {', '.join(value_clauses)}",
        params,
    )


def _insert_revenue(
    website_id: str,
    session_id: str,
    event_id: str,
    event_name: str | None,
    revenue_data: dict[str, Any],
    now: Any,
) -> None:
    """Insert a revenue record linked to the triggering event and session.

    Revenue events are used by e-commerce sites to track monetary value
    associated with custom events (e.g. "purchase", "add-to-cart"). The
    ``amount`` field is required; if absent, the insert is silently skipped.

    The currency code is stored as-is (truncated to 3 chars to match ISO 4217)
    but no validation is performed -- the revenue analytics queries aggregate
    by currency, so mixed currencies are handled at display time.

    Args:
        website_id: UUID of the website.
        session_id: UUID of the session that generated this revenue.
        event_id: UUID of the parent ``website_event`` row.
        event_name: Name of the custom event (e.g. ``"purchase"``), or
            ``None`` for pageview-associated revenue.
        revenue_data: Dict with ``amount`` (required numeric) and
            ``currency`` (optional str, defaults to ``"USD"``).
        now: Timezone-aware datetime for the ``created_at`` column.
    """
    amount = revenue_data.get("amount")
    currency = revenue_data.get("currency", "USD")
    # amount is required -- silently skip if the tracker didn't send one
    if amount is None:
        return

    revenue_id = str(uuid.uuid4())
    raw_query(
        """
        INSERT INTO revenue
            (revenue_id, website_id, session_id, event_id, event_name,
             revenue, currency, created_at)
        VALUES
            ({{revenueId::uuid}}, {{websiteId::uuid}}, {{sessionId::uuid}},
             {{eventId::uuid}}, {{eventName}}, {{amount}}, {{currency}},
             {{createdAt::timestamptz}})
        """,
        {
            "revenueId": revenue_id,
            "websiteId": website_id,
            "sessionId": session_id,
            "eventId": event_id,
            "eventName": (event_name or "")[:50] or None,
            "amount": amount,
            "currency": currency[:3],
            "createdAt": now,
        },
    )


@transaction.atomic
def ingest_identify(website_id: str, session_id: str, payload: dict[str, Any]) -> None:
    """Process an ``identify`` call: link a distinct user ID and properties to a session.

    The ``identify`` wire format lets site JS associate a known user identity
    (e.g. ``"user_42"``) and custom properties (e.g. ``{"plan": "pro"}``)
    with the current anonymous session. This enables user-level analytics
    and segmentation without requiring login-gated tracking.

    Two writes happen in a single transaction:
    1. If ``payload.id`` is present, the session's ``distinct_id`` column is
       updated (capped at 50 chars).
    2. If ``payload.data`` is a dict, each key-value pair is inserted into
       ``session_data`` (one row per key, similar to ``event_data``).

    Args:
        website_id: UUID of the website this session belongs to.
        session_id: UUID of the session to update.
        payload: The ``payload`` object from the tracker wire format.
            Expected keys: ``id`` (optional distinct user identifier),
            ``data`` (optional dict of custom session properties).
    """
    now = timezone.now()
    data = payload.get("data")
    identify_id = payload.get("id")

    # Step 1: Link a distinct user ID to the anonymous session
    if identify_id:
        raw_query(
            """
            UPDATE session SET distinct_id = {{distinctId}}
            WHERE session_id = {{sessionId::uuid}}
            """,
            {"distinctId": str(identify_id)[:50], "sessionId": session_id},
        )

    # Step 2: Write custom session properties as individual rows.
    # Each key-value pair is inserted separately (unlike event_data which
    # uses a multi-row INSERT) because identify calls typically carry fewer
    # properties and the simplicity of individual inserts is preferred.
    if data and isinstance(data, dict):
        distinct_id = str(identify_id)[:50] if identify_id else None
        for key, value in data.items():
            string_val, number_val, data_type = _coerce_event_value(value)
            raw_query(
                """
                INSERT INTO session_data
                    (session_data_id, website_id, session_id, data_key,
                     string_value, number_value, date_value, data_type,
                     distinct_id, created_at)
                VALUES
                    ({{dataId::uuid}}, {{websiteId::uuid}}, {{sessionId::uuid}},
                     {{dataKey}}, {{stringValue}}, {{numberValue}},
                     {{dateValue::timestamptz}}, {{dataType}},
                     {{distinctId}}, {{createdAt::timestamptz}})
                """,
                {
                    "dataId": str(uuid.uuid4()),
                    "websiteId": website_id,
                    "sessionId": session_id,
                    "dataKey": key[:500],
                    "stringValue": string_val,
                    "numberValue": number_val,
                    "dateValue": None,
                    "dataType": data_type,
                    "distinctId": distinct_id,
                    "createdAt": now,
                },
            )
