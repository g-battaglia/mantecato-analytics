"""Behavioural bot classification on the cookieless ``visitor_key`` digest.

The session-based product (Mantecato v2/v3) excludes whole bot **sessions** from
visitor/visit/bounce counts using behavioural heuristics computed at read time
(zero-engagement, high-velocity, datacentre clusters) plus cheap signals
(bot/empty browser, excluded countries).

:func:`compute_bot_visitor_keys` ports that logic 1:1 onto ``visitor_key`` using
only the anonymous fields already on ``website_event`` (coarse browser/os/device,
country, pageview count, and on-page duration), returning a set of digests to
exclude. Driven by the per-site :class:`BotConfig`.

STATUS — NOT YET WIRED IN. This is scaffolding for behavioural bot filtering on
the cookieless counts; it has no production callers today. The shipped v4 bot
filter is the cheaper read-time event-level exclusion (bot UA / datacentre IP /
excluded countries via ``filters.build_bot_filter_sql`` and the read paths in
``core/mantecato_core/queries/visitors.py``); the behavioural heuristics here do
not run. Before relying on it, wire it into the read/rollup path and cover it
with tests — turning it on will change visitor/visit/bounce counts.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

# Matches the bot/automation tokens of ``filters.BOT_BROWSER_PATTERN`` against the
# coarse parsed browser family (v3 matches the same tokens on ``session.browser``).
_BOT_BROWSER_RE = re.compile(
    r"bot|crawler|spider|scraper|headless|phantom|selenium|puppeteer"
    r"|wget|curl|python|go-http|java|libwww|fetcher|slurp"
    r"|googlebot|bingbot|yandex|baidu|facebookexternalhit"
    r"|twitterbot|linkedinbot|whatsapp|telegrambot|discordbot"
    r"|applebot|semrush|ahrefs|mj12bot|dotbot|petalbot"
    r"|bytespider|gptbot|claudebot|chatgpt|searchbot",
    re.IGNORECASE,
)


def get_bot_config(website_id: str) -> dict[str, Any]:
    """Return the saved per-site bot-detection config (defaults if none).

    Unlike :func:`apps.core.models.merge_bot_config` this keeps **all** saved
    keys, including the behavioural-heuristic keys (``zeroEngagement``,
    ``highVelocityThreshold``, ``clusterDetection``…) that the v2/v3 config
    carried but the trimmed v4 defaults do not enumerate. Honors the saved
    ``enabled`` flag.

    When bot detection is enabled but the config does not pin ``zeroEngagement``
    (the trimmed v4 UI doesn't expose it), it defaults to **on** — that is the
    rule that classifies single-pageview / no-engagement hits as bots, the v2/v3
    baseline that produces the visible visitor/visit reduction. Engagement beacons
    keep real single-page readers (active time > 0) from being flagged.
    """
    from apps.core.models import BOT_CONFIG_DEFAULTS, BotConfig

    try:
        row = BotConfig.objects.filter(website_id=website_id).first()
    except Exception:  # noqa: BLE001 — never block aggregation on config lookup
        return dict(BOT_CONFIG_DEFAULTS)
    params = row.parameters if (row is not None and isinstance(row.parameters, dict)) else {}
    cfg = {**BOT_CONFIG_DEFAULTS, **params}
    if cfg.get("enabled") and "zeroEngagement" not in params:
        cfg["zeroEngagement"] = True
    return cfg


def compute_bot_visitor_keys(
    website_id: str,
    start_date: datetime | None,
    end_date: datetime | None,
    config: dict[str, Any],
    *,
    engaged_dur_by_key: dict[str, float] | None = None,
) -> set[str]:
    """Return the ``visitor_key`` digests classified as bots for *website_id*.

    Mirrors v3's session-level bot filter on the cookieless digest:

    - **knownBots** — coarse browser family matches a bot/automation token;
    - **emptyUa** — both browser and os empty;
    - **excludedCountries** — country in the configured deny-list;
    - **zeroEngagement** — single pageview with on-page duration below
      ``minDuration`` (or exactly 0 when unset);
    - **highVelocityThreshold** — more than N pageviews in under 60s;
    - **clusterDetection** — single-page/zero-duration digest inside a large
      ``(country, device)`` cluster dominated by such bounces.

    ``dur`` is the digest's last-minus-first event time; when
    *engaged_dur_by_key* is given (live data with engagement beacons) it
    overrides that for the zero-engagement test so genuinely engaged single-page
    readers are not misclassified. Returns an empty set when bot detection is
    disabled.
    """
    if not config.get("enabled", False):
        return set()

    from itertools import groupby

    from apps.core.models import WebsiteEvent

    qs = WebsiteEvent.objects.filter(
        website_id=website_id, event_type=1, visitor_key__isnull=False
    )
    if start_date is not None:
        qs = qs.filter(created_at__gte=start_date)
    if end_date is not None:
        qs = qs.filter(created_at__lte=end_date)

    rows = qs.order_by("visitor_key", "created_at").values_list(
        "visitor_key", "created_at", "browser", "os", "country", "device"
    )

    # One summary tuple per digest: (key, pv, dur, country, device, browser, os).
    sessions: list[tuple[str, int, float, str, str, str, str]] = []
    for key, grp in groupby(rows.iterator(), key=lambda r: r[0]):
        evs = list(grp)
        pv = len(evs)
        gap_dur = float((evs[-1][1] - evs[0][1]).total_seconds())
        dur = gap_dur
        if engaged_dur_by_key is not None and key in engaged_dur_by_key:
            dur = max(gap_dur, float(engaged_dur_by_key[key]))
        first = evs[0]  # visitor_key, created_at, browser, os, country, device
        sessions.append(
            (key, pv, dur, first[4] or "", first[5] or "", first[2] or "", first[3] or "")
        )

    known_bots = config.get("knownBots", True)
    empty_ua = config.get("emptyUa", True)
    excluded = {
        c.upper()
        for c in (config.get("excludedCountries") or [])
        if isinstance(c, str) and len(c) == 2
    }
    zero_eng = bool(config.get("zeroEngagement", False))
    min_dur = int(config.get("minDuration", 0) or 0)
    velocity = int(config.get("highVelocityThreshold", 0) or 0)
    use_cluster = bool(config.get("clusterDetection", False))
    bounce_threshold = max(50, min(100, int(config.get("clusterBounceThreshold", 90)))) / 100.0
    min_cluster = max(10, min(500, int(config.get("clusterMinSize", 100))))

    cluster_total: dict[tuple[str, str], int] = defaultdict(int)
    cluster_bounce: dict[tuple[str, str], int] = defaultdict(int)
    if use_cluster:
        for _key, pv, dur, country, device, _b, _o in sessions:
            cluster_total[(country, device)] += 1
            if pv == 1 and dur == 0:
                cluster_bounce[(country, device)] += 1

    def _is_bot(pv: int, dur: float, country: str, device: str, browser: str, os_: str) -> bool:
        if known_bots and browser and _BOT_BROWSER_RE.search(browser):
            return True
        if empty_ua and not browser and not os_:
            return True
        if excluded and country.upper() in excluded:
            return True
        if zero_eng and pv == 1 and (dur < min_dur if min_dur > 0 else dur == 0):
            return True
        if velocity > 0 and pv > velocity and dur < 60:
            return True
        if use_cluster and pv == 1 and dur == 0:
            total = cluster_total[(country, device)]
            ratio = cluster_bounce[(country, device)] / total if total else 0
            return total >= min_cluster and ratio > bounce_threshold
        return False

    return {
        key
        for key, pv, dur, country, device, browser, os_ in sessions
        if _is_bot(pv, dur, country, device, browser, os_)
    }
