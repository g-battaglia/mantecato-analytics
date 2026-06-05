"""URL routes for the core app: sign-in, sign-out, health-check.

Note:
    ``LoginView`` / ``LogoutView`` are class-based views; the historical names
    ``login`` / ``logout`` / ``health_check`` are preserved via
    :func:`~django.urls.path` ``name=`` kwargs so ``{% url 'login' %}`` and
    :func:`~django.urls.reverse` calls elsewhere keep working.
"""

from __future__ import annotations

from django.urls import path

from apps.core.views import LoginView, LogoutView, health_check

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("health/", health_check, name="health_check"),
]
