"""Mantecato Python SDK -- programmatic access to the Mantecato analytics API.

Quick start::

    from mantecato_client import MantecatoClient

    with MantecatoClient("https://analytics.example.com", api_key="mtk_xxx") as client:
        sites = client.sites.list()
        overview = client.analytics.overview(sites["sites"][0]["id"], date_range="30d")
        print(overview["stats"]["visitors"]["value"])
"""

from mantecato_client._client import MantecatoClient
from mantecato_client.exceptions import (
    AuthError,
    MantecatoError,
    NotFoundError,
    ValidationError,
)

__version__ = "0.1.0"
__all__ = [
    "MantecatoClient",
    "MantecatoError",
    "AuthError",
    "NotFoundError",
    "ValidationError",
]
