"""User-facing errors with stable exit behavior."""

from __future__ import annotations


class CliError(RuntimeError):
    """Base CLI error that is safe to print after secret redaction."""

    exit_code = 1


class UsageError(CliError):
    """Invalid local input."""

    exit_code = 2


class ApiError(CliError):
    """An HTTP or API contract error."""

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
