"""Bot detection configuration endpoint methods for the Mantecato Python SDK.

Provides get and save operations for per-website bot detection settings.
The config controls which user-agent patterns and IP ranges are classified
as bot traffic and filtered from analytics results.  Stored as a ``report``
row with ``type='mantecato-bot-config'``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mantecato_client._client import MantecatoClient


class BotConfigEndpoints:
    """Bot detection configuration methods.

    Accessed via ``client.bot_config`` on a :class:`MantecatoClient` instance.

    Example::

        config = client.bot_config.get(website_id="uuid")
        config["config"]["block_known_bots"] = True
        client.bot_config.save(website_id="uuid", config=config["config"])
    """

    def __init__(self, client: MantecatoClient) -> None:
        """Initialize with a reference to the parent client.

        Args:
            client: The :class:`MantecatoClient` instance that owns this
                endpoint group.
        """
        self._client = client

    def get(self, *, website_id: str) -> dict[str, Any]:
        """Retrieve the current bot detection configuration for a website.

        Args:
            website_id: UUID of the website to get bot config for.

        Returns:
            Dict with a ``config`` key containing the bot detection
            settings (blocked UA patterns, IP ranges, etc.).
        """
        return self._client._get("/api/bot-config/", {"website": website_id})

    def save(self, *, website_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Save (create or update) bot detection configuration for a website.

        Args:
            website_id: UUID of the website to configure.
            config: JSON-serializable dict with bot detection settings
                (e.g. ``{"block_known_bots": True, "custom_patterns": [...]}``).

        Returns:
            The saved configuration dict.

        Raises:
            ValidationError: If the config structure is invalid.
        """
        return self._client._post(
            "/api/bot-config/save/",
            {"website_id": website_id, "config": config},
        )
