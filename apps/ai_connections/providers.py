"""Public documented workflows; neither logos nor interoperability claims."""

from urllib.parse import urlencode, urlsplit

from django.utils.translation import gettext_lazy as _

PROVIDERS = [
    {
        "id": "claude",
        "name": "Claude",
        "symbol": "C",
        "guide": "https://claude.com/docs/connectors/building/directory-vs-custom",
        "description": _(
            "Use the prefilled form or add a custom connector manually. "
            "Review the URL before confirming."
        ),
        "steps": [
            _("Open Claude's connector settings and choose Add custom connector."),
            _("Enter Mantecato and the MCP address below, or use Open Claude setup."),
        ],
        "eligibility": _(
            "Custom connector availability is controlled by your account and organization. "
            "This server is not a directory-listed or endorsed connector."
        ),
    },
    {
        "id": "chatgpt",
        "name": "ChatGPT",
        "symbol": "O",
        "guide": "https://developers.openai.com/plugins/build/app-quickstart",
        "description": _("Use custom MCP setup in developer mode, not a model API key."),
        "steps": [
            _(
                "In ChatGPT, open Settings, then Security and login, "
                "and enable Developer mode if available."
            ),
            _(
                "Open ChatGPT Plugins, select the plus button, and enter the HTTPS MCP address. "
                "Choose OAuth authentication."
            ),
        ],
        "eligibility": _(
            "Your account or workspace may restrict developer mode and custom plugins. "
            "Menu names can change; use the official instructions if these options are missing."
        ),
    },
    {
        "id": "gemini",
        "name": "Gemini",
        "symbol": "G",
        "guide": "https://support.google.com/gemini/answer/17209137?hl=en",
        "description": _("Add a custom connected app in Gemini's web app using its MCP URL."),
        "steps": [
            _("Open Gemini on the web and follow its custom connected-app setup."),
            _("Enter the MCP address below and complete the authorization prompt."),
        ],
        "eligibility": _(
            "Current official requirements: age 18+, US, a personal Google Account, "
            "Keep Activity enabled, and English. Work or school accounts are not eligible. "
            "Recheck the guide as availability changes."
        ),
    },
    {
        "id": "grok",
        "name": "Grok",
        "symbol": "X",
        "guide": "https://docs.x.ai/grok/connectors",
        "description": _(
            "Add a custom MCP connector, separate from the built-in connector catalog."
        ),
        "steps": [
            _("Open grok.com/connectors, choose New Connector, then Custom."),
            _("Enter the public MCP address below and complete OAuth authorization."),
        ],
        "eligibility": _(
            "Business and Enterprise workspaces require an administrator to provision "
            "the connector. The MCP server must be publicly reachable."
        ),
    },
    {
        "id": "generic",
        "name": _("Other MCP client"),
        "symbol": "+",
        "guide": "https://modelcontextprotocol.io/specification/2025-11-25/basic/transports",
        "description": _(
            "Use remote Streamable HTTP with OAuth, or a protected Bearer token setting."
        ),
        "steps": [
            _("Add a remote Streamable HTTP server with the MCP address below."),
            _(
                "Use OAuth with S256 PKCE. If your client lacks OAuth, create a personal token "
                "below and save it only in protected client settings."
            ),
        ],
        "eligibility": _(
            "Cloud clients cannot reach localhost. Local stdio clients use the independent "
            "mantecato-mcp package and a separate legacy API key."
        ),
    },
]


def claude_url(endpoint):
    p = urlsplit(endpoint)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.hostname in ("localhost", "127.0.0.1", "::1")
        or "." not in p.hostname
        or p.hostname.endswith((".local", ".internal", ".localhost"))
        or p.username
        or p.password
        or p.query
        or p.fragment
    ):
        return ""
    return "https://claude.ai/customize/connectors?" + urlencode(
        {
            "modal": "add-custom-connector",
            "connectorName": "Mantecato",
            "connectorUrl": endpoint,
        }
    )


def agent_prompt(endpoint):
    return _(
        "Add Mantecato as a custom MCP connection.\n\n"
        "Server URL: %(endpoint)s\nTransport: remote Streamable HTTP.\n\n"
        "Discover OAuth metadata and use authorization code with S256 PKCE. Open the Mantecato "
        "sign-in and consent page so I choose the sites and approve read-only access myself. "
        "Never ask for passwords, authorization codes, or tokens in chat. Keep credentials only "
        "in protected connector settings. Verify with tools/list or get_connection_status, "
        "without reading statistics during setup. Read analytics only when I request them. "
        "If this client cannot add custom MCP connections, explain manual setup instead; "
        "do not claim success until verified."
    ) % {"endpoint": endpoint}
