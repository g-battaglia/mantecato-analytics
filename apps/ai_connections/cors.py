"""One CORS policy for normal MCP responses and pre-transport overloads.

Imported only when remote MCP is configured. In particular, an outer ASGI
admission rejection must not bypass this policy or expose arbitrary origins.
"""

from django.conf import settings
from starlette.middleware.cors import CORSMiddleware


def mcp_allowed_origins(origin):
    return [
        origin,
        "https://claude.ai",
        "https://chatgpt.com",
        "https://gemini.google.com",
        "https://grok.com",
        *getattr(settings, "AI_MCP_ALLOWED_ORIGINS", []),
    ]


def mcp_cors(app, origin):
    return CORSMiddleware(
        app,
        allow_origins=mcp_allowed_origins(origin),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Mcp-Protocol-Version", "Mcp-Session-Id"],
        expose_headers=["WWW-Authenticate", "Mcp-Session-Id", "Retry-After"],
        allow_credentials=False,
    )
