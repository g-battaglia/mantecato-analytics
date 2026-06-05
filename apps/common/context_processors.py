"""Template context processors for the Mantecato UI."""

from __future__ import annotations

import logging

_logged_default_password: set[str] = set()


def default_password_warning(request: object) -> dict[str, bool]:
    """Add ``show_default_password_banner`` to the template context.

    When the current user is an admin whose ``password_is_default`` flag is set,
    a one-time WARNING is emitted to the ``mantecato.security`` logger. The flag
    is tracked in a module-level set keyed by user id so the warning fires at
    most once per process lifetime (similar to the ``ALLOWED_HOSTS`` startup
    warning pattern).
    """
    try:
        user = request.user  # type: ignore[union-attr]
    except AttributeError:
        return {}

    if not getattr(user, "is_authenticated", False):
        return {}

    if getattr(user, "password_is_default", False):
        uid = str(user.id)
        if uid not in _logged_default_password:
            _logged_default_password.add(uid)
            logging.getLogger("mantecato.security").warning(
                "Admin user '%s' is still using the default password. "
                "Change it via Settings → Account or the 'update_user_account' service.",
                user.username,
            )

    return {}
