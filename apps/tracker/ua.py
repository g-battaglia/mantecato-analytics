"""User-Agent parsing — browser, OS, device, and bot classification."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_BOT_PATTERNS = (
    "bot",
    "crawler",
    "spider",
    "scraper",
    "headless",
    "phantom",
    "selenium",
    "puppeteer",
    "wget",
    "curl",
    "python-requests",
    "go-http-client",
    "java/",
    "libwww",
    "fetcher",
    "slurp",
    "googlebot",
    "bingbot",
    "yandex",
    "baiduspider",
    "facebookexternalhit",
    "twitterbot",
    "linkedinbot",
    "whatsapp",
    "telegrambot",
    "discordbot",
    "applebot",
    "semrush",
    "ahrefs",
    "mj12bot",
    "dotbot",
    "petalbot",
    "bytespider",
    "gptbot",
    "claudebot",
    "chatgpt",
)
_BOT_RE = re.compile("|".join(re.escape(p) for p in _BOT_PATTERNS), re.I)

# Lazy-loaded parser module. The ``_parser_loaded`` flag distinguishes
# "not yet attempted" from "attempted but failed (ImportError)".
_parser = None
_parser_loaded = False


def _get_parser():
    """Return the ``ua_parser.user_agent_parser`` module, loading it lazily.

    The parser is loaded once on first call. If ``ua-parser`` is not installed,
    a warning is logged and ``None`` is returned (all subsequent calls also
    return ``None`` without retrying the import).

    Returns:
        The ``user_agent_parser`` module, or ``None`` if the package is
        not installed.
    """
    global _parser, _parser_loaded
    if _parser_loaded:
        return _parser

    _parser_loaded = True
    try:
        from ua_parser import user_agent_parser

        _parser = user_agent_parser
    except ImportError:
        logger.warning("ua-parser not installed — UA fields will be empty")
    return _parser


def parse_user_agent(ua_string: str) -> dict[str, str | None]:
    """Parse a User-Agent string into browser, OS, and device type.

    Extracts three fields used for device analytics:
    - ``browser``: The browser family name (e.g. ``"Chrome"``, ``"Safari"``).
    - ``os``: The operating system family (e.g. ``"Windows"``, ``"iOS"``).
    - ``device``: The device category (``"desktop"``, ``"mobile"``, or
      ``"tablet"``).

    All values are truncated to 20 characters to match column widths.
    The ``"Other"`` sentinel returned by ``ua-parser`` for unrecognised
    strings is mapped to ``None`` so it appears as unknown in analytics.

    When the parser library is unavailable or the UA string is empty, all
    fields are ``None``.

    Args:
        ua_string: The raw ``User-Agent`` header value.

    Returns:
        A dict with keys ``browser``, ``os``, and ``device``, each
        containing a string or ``None``.
    """
    if not ua_string:
        return {"browser": None, "os": None, "device": None}

    parser = _get_parser()
    if parser is None:
        return {"browser": None, "os": None, "device": None}

    try:
        parsed = parser.Parse(ua_string)
    except Exception:
        return {"browser": None, "os": None, "device": None}

    # Extract browser family, normalising "Other" to None
    ua = parsed.get("user_agent", {})
    browser = ua.get("family")
    if browser == "Other":
        browser = None
    if browser and len(browser) > 20:
        browser = browser[:20]

    # Extract OS family, normalising "Other" to None
    os_data = parsed.get("os", {})
    os_name = os_data.get("family")
    if os_name == "Other":
        os_name = None
    if os_name and len(os_name) > 20:
        os_name = os_name[:20]

    # Determine device type. When ua-parser returns a specific device family
    # (e.g. "iPhone"), classify it as mobile/desktop. When the family is
    # unknown ("Other" or empty), fall back to keyword matching on the raw UA.
    device_data = parsed.get("device", {})
    device_family = device_data.get("family", "")
    if device_family in ("Other", ""):
        device = _infer_device_type(ua_string)
    else:
        device = "mobile" if _is_mobile_device(device_family) else "desktop"
    if device and len(device) > 20:
        device = device[:20]

    return {"browser": browser, "os": os_name, "device": device}


def classify_bot_user_agent(ua_string: str) -> tuple[bool, str | None]:
    """Classify a request as bot/non-bot without storing the raw User-Agent.

    The classifier emits only coarse reasons suitable for aggregate filtering.
    It deliberately avoids creating a client key or any persistent identifier.
    """
    if not ua_string:
        return True, "empty_user_agent"
    if _BOT_RE.search(ua_string):
        return True, "known_bot_user_agent"
    return False, None


def _is_mobile_device(family: str) -> bool:
    """Check whether a ua-parser device family string represents a mobile device.

    Uses keyword matching against common mobile device identifiers. Tablets
    are classified as mobile here because the ``_infer_device_type`` fallback
    handles the tablet distinction separately.

    Args:
        family: The device family string from ``ua-parser`` (e.g. ``"iPhone"``).

    Returns:
        ``True`` if the family contains a mobile-related keyword.
    """
    mobile_keywords = ("iphone", "ipad", "android", "mobile", "tablet", "phone")
    return any(kw in family.lower() for kw in mobile_keywords)


def _infer_device_type(ua: str) -> str:
    """Infer the device type from the raw User-Agent string using keyword heuristics.

    This is the fallback when ``ua-parser`` cannot identify the device family.
    The check order matters: mobile keywords are tested before tablet keywords
    because some User-Agents contain both (e.g. ``"Mobile Safari"`` on iPad).

    Args:
        ua: The raw User-Agent header string.

    Returns:
        One of ``"mobile"``, ``"tablet"``, or ``"desktop"``.
    """
    ua_lower = ua.lower()
    if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
        return "mobile"
    if "tablet" in ua_lower or "ipad" in ua_lower:
        return "tablet"
    return "desktop"
