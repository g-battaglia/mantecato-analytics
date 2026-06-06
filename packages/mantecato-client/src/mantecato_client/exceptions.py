"""Exception hierarchy for the Mantecato Python SDK.

All API errors are subclasses of :class:`MantecatoError`, which carries the
HTTP status code and raw response body.  This allows callers to catch broad
(``MantecatoError``) or narrow (``AuthError``, ``NotFoundError``, etc.)
exceptions as needed.

Exception mapping (handled by :meth:`MantecatoClient._request`):

- HTTP 400 -> :class:`ValidationError`
- HTTP 401, 403 -> :class:`AuthError`
- HTTP 404 -> :class:`NotFoundError`
- HTTP 5xx / other -> :class:`MantecatoError`

Example::

    from mantecato_client import MantecatoClient, AuthError, NotFoundError

    try:
        data = client.analytics.overview("bad-uuid", date_range="30d")
    except AuthError:
        print("Invalid API key")
    except NotFoundError:
        print("Website not found")
"""

from __future__ import annotations


class MantecatoError(Exception):
    """Base exception for all Mantecato API errors.

    Attributes:
        status_code: HTTP status code from the API response (0 if not
            from an HTTP response).
        response_body: Parsed JSON body from the error response, or
            an empty dict if parsing failed.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        response_body: dict | None = None,
    ) -> None:
        """Initialize with error details.

        Args:
            message: Human-readable error message (typically from the API's
                ``"error"`` field, or a fallback like ``"HTTP 500"``).
            status_code: HTTP status code from the response.
            response_body: Parsed JSON body from the error response.
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}


class AuthError(MantecatoError):
    """Raised on HTTP 401 (Unauthorized) or 403 (Forbidden).

    Indicates the API key is missing, invalid, expired, or lacks the
    required scopes for the requested operation.
    """


class NotFoundError(MantecatoError):
    """Raised on HTTP 404 (Not Found).

    Indicates the requested resource (website, dashboard, or API key)
    does not exist or has been deleted.
    """


class ValidationError(MantecatoError):
    """Raised on HTTP 400 (Bad Request).

    Indicates invalid request parameters or body.  Check
    ``response_body`` for field-level error details.
    """
