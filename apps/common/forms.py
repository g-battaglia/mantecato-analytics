"""Django forms for report-table CRUD input and tracker ingestion.

These forms replace the hand-rolled ``request.POST.get(...).strip()`` parsing
that previously lived inline in every view. They are shared between:

- the HTML CRUD views (``apps.dashboards.views``, ``apps.settings_app.views``),
- the JSON API endpoints (``apps.api.views``),
- the tracker ingestion endpoint (``apps.tracker.views``).

Design choice:
    The dashboard form is a :class:`~django.forms.ModelForm` over the proxy
    model in :mod:`apps.core.models`. Its :meth:`save` override sets the
    ``type`` discriminator explicitly because ``ModelForm.save`` calls
    ``instance.save()`` directly (bypassing :class:`apps.core.models.ReportProxyManager`'s
    ``create``).

    The API-key and bot-config forms remain plain :class:`~django.forms.Form`
    instances: their persistence has side effects (key generation + hashing,
    defaults merging) better handled by the service layer.

    :class:`TrackerEventForm` validates the JSON body for ``POST /api/send``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from django import forms

from apps.common.constants import COUNTRY_CHOICES_SORTED
from apps.common.constants import DASHBOARD_DEFAULT_CONFIG as _DASHBOARD_DEFAULT_CONFIG
from apps.core.models import (
    BOT_CONFIG_DEFAULTS,
    Dashboard,
    ReportType,
    Website,
)

# Minimum password length enforced across all user-management forms.
MIN_PASSWORD_LENGTH = 8

ROLE_CHOICES = [("user", "User"), ("admin", "Admin")]


def first_error(form: forms.BaseForm) -> str:
    """Return a human-readable summary of a bound form's first error.

    Args:
        form: A bound form whose :attr:`errors` mapping has been computed.

    Returns:
        A ``"Field: message"`` string suitable for ``messages.error``.
        Returns ``"Invalid input."`` when the form has no field errors.
    """
    for field, errors in form.errors.items():
        label = field.replace("_", " ").strip().capitalize()
        return f"{label}: {errors[0]}"
    return "Invalid input."


# ---------------------------------------------------------------------------
# Dashboard ModelForm
# ---------------------------------------------------------------------------


class _ReportModelForm(forms.ModelForm):
    """Common machinery for proxy-model forms (currently Dashboard).

    Sub-responsibilities:

    - Coerces blank description to ``""`` (the column is nullable but the JSON
      contract historically uses empty strings, never ``null``).
    - Disables ``website_id`` editing once the row exists (immutable post-create).
    - Stamps the discriminator string in :meth:`save` because Django's
      ``ModelForm.save`` invokes ``instance.save()`` directly, bypassing the
      manager's ``create`` override.

    Subclasses set:

    Attributes:
        report_type (ReportType): the discriminator value to stamp.
    """

    report_type: ReportType

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialise the form and disable ``website_id`` on existing rows.

        Args:
            *args: Positional arguments forwarded to ``ModelForm.__init__``.
            **kwargs: Keyword arguments forwarded to ``ModelForm.__init__``.
        """
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Website is immutable after creation -- disabling the field
            # prevents both rendering an editable widget and accepting a
            # changed value in submitted data.
            self.fields["website_id"].required = False
            self.fields["website_id"].disabled = True

    def clean_description(self) -> str:
        """Coerce blank or ``None`` descriptions to the empty string.

        Returns:
            The cleaned description string, never ``None``.
        """
        return self.cleaned_data.get("description") or ""

    def save(self, commit: bool = True) -> Any:
        """Persist the instance, stamping the ``type`` discriminator first.

        This override is necessary because ``ModelForm.save()`` calls
        ``instance.save()`` directly -- bypassing
        :meth:`ReportProxyManager.create` which would normally set the
        discriminator. Without this stamp the row would inherit whatever
        ``type`` value happens to be on the instance (often empty).

        Args:
            commit: If ``True`` (default), save to the database immediately.

        Returns:
            The saved model instance.
        """
        # ModelForm.save() bypasses Manager.create() so the discriminator must
        # be stamped explicitly to preserve the proxy invariant.
        self.instance.type = self.report_type.value
        return super().save(commit=commit)


class DashboardModelForm(_ReportModelForm):
    """ModelForm for :class:`apps.core.models.Dashboard`.

    Fields:
        - ``name`` (CharField, ≤200, required)
        - ``description`` (CharField, ≤500, optional)
        - ``website_id`` (UUIDField; required on create, disabled on update)
        - ``config`` (JSONField, optional; default layout applied when blank
          on create, preserved on edit)

    The ``config`` field is the camelCase JSON name historically used by both
    the HTML form and the JSON API; it maps to the underlying
    :attr:`Report.parameters` column inside :meth:`save`.

    Cross-refs:
        - :class:`apps.dashboards.views.DashboardCreateView` (web)
        - :class:`apps.api.views.DashboardJSONCreateView` (JSON API)
    """

    report_type = ReportType.DASHBOARD
    config = forms.JSONField(required=False)

    class Meta:
        model = Dashboard
        fields = ("name", "description", "website_id")

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialise the form, pre-populating ``config`` as JSON text on edit.

        On existing instances the ``parameters`` dict is serialised to
        indented JSON so the ``<textarea>`` widget receives a human-readable
        string rather than Python's ``repr(dict)`` form.

        Args:
            *args: Positional arguments forwarded to the parent.
            **kwargs: Keyword arguments forwarded to the parent.
        """
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Serialize as JSON text so the textarea widget receives a clean
            # JSON string rather than Python's ``repr(dict)`` form.
            self.initial["config"] = json.dumps(
                self.instance.parameters or {}, indent=2, ensure_ascii=False
            )

    def save(self, commit: bool = True) -> Dashboard:
        """Persist the dashboard, applying the default layout on create.

        On create (no PK yet) the default 2-column / empty-widgets layout
        from :data:`_DASHBOARD_DEFAULT_CONFIG` is applied when no ``config``
        was submitted. On edit, the existing config is preserved if the
        field was not provided.

        Args:
            commit: If ``True`` (default), save to the database immediately.

        Returns:
            The saved :class:`Dashboard` instance.
        """
        cfg = self.cleaned_data.get("config")
        if self.instance.pk:
            # Preserve existing config if the edit form did not submit one.
            self.instance.parameters = cfg if cfg is not None else (self.instance.parameters or {})
        else:
            # Apply the default layout scaffold for new dashboards.
            self.instance.parameters = cfg if cfg is not None else dict(_DASHBOARD_DEFAULT_CONFIG)
        return super().save(commit=commit)


# ---------------------------------------------------------------------------
# API-key & bot-config forms (plain Form: side effects, not pure CRUD)
# ---------------------------------------------------------------------------


class ApiKeyForm(forms.Form):
    """Validate the API-key creation request.

    The key value itself is generated by
    :func:`apps.settings_app.services.generate_new_api_key`, which also hashes
    it and stamps the ``parameters`` JSON. The form only validates the
    user-supplied label and the optional comma-separated scope list.

    Fields:
        - ``name`` (CharField, ≤200, required)
        - ``scopes`` (CharField, optional; comma-separated list, e.g.
          ``"read,write"``)
    """

    name = forms.CharField(max_length=200)
    scopes = forms.CharField(required=False)

    def scope_list(self) -> list[str]:
        """Parse the comma-separated ``scopes`` field.

        Returns:
            The parsed scope list, or ``["read", "write"]`` when the field is
            empty (legacy default for keys created via the web UI).
        """
        raw = self.cleaned_data.get("scopes", "") or ""
        scopes = [s.strip() for s in raw.split(",") if s.strip()]
        return scopes or ["read", "write"]


# Field name groupings derived from :data:`BOT_CONFIG_DEFAULTS`. We split by
# type so the form can coerce them appropriately.
_BOT_BOOL_FIELDS: tuple[str, ...] = tuple(
    key for key, default in BOT_CONFIG_DEFAULTS.items() if isinstance(default, bool)
)
_BOT_INT_FIELDS: tuple[str, ...] = tuple(
    key
    for key, default in BOT_CONFIG_DEFAULTS.items()
    if isinstance(default, int) and not isinstance(default, bool)
)


class BotConfigForm(forms.Form):
    """Validate the bot-detection config form.

    Twelve typed fields mirroring :data:`apps.core.models.BOT_CONFIG_DEFAULTS`,
    plus :attr:`excludedCountries` (comma-separated country codes). The
    :meth:`to_config` helper produces a dict ready for
    :func:`apps.settings_app.services.save_bot_config`.
    """

    enabled = forms.BooleanField(required=False)
    knownBots = forms.BooleanField(required=False)
    emptyUa = forms.BooleanField(required=False)
    clusterDetection = forms.BooleanField(required=False)
    zeroEngagement = forms.BooleanField(required=False)
    missingScreen = forms.BooleanField(required=False)
    missingLanguage = forms.BooleanField(required=False)
    clusterBounceThreshold = forms.IntegerField(required=False)
    clusterMinSize = forms.IntegerField(required=False)
    minDuration = forms.IntegerField(required=False)
    highVelocityThreshold = forms.IntegerField(required=False)
    excludedCountries = forms.MultipleChoiceField(
        required=False,
        choices=COUNTRY_CHOICES_SORTED,
    )

    def to_config(self) -> dict[str, Any]:
        """Return the cleaned config dict for ``save_bot_config``.

        Booleans default to ``False``; integers default to ``0``; the country
        list is the cleaned multi-select value already validated against
        :data:`apps.common.constants.COUNTRY_CHOICES_SORTED`.
        """
        data = self.cleaned_data
        config: dict[str, Any] = {field: bool(data.get(field)) for field in _BOT_BOOL_FIELDS}
        for field in _BOT_INT_FIELDS:
            config[field] = data.get(field) or 0
        config["excludedCountries"] = list(data.get("excludedCountries") or [])
        return config


class UmamiImportForm(forms.Form):
    """Validate the UI-triggered, data-only single-site Umami import request.

    Mirrors the validation in the ``importumamidata`` management command: both
    website ids are required (single-site remap), the DSN must be a PostgreSQL
    connection string, and ``since`` (when given) uses the same ``YYYY-MM-DD``
    format. The DSN is **not** persisted — the view hands it straight to the
    background thread (see :func:`apps.settings_app.services.start_umami_import_job`).

    Fields:
        - ``target_website`` (UUIDField): existing Mantecato site to remap onto.
        - ``source_website`` (UUIDField): Umami ``website_id`` to import.
        - ``source_dsn`` (CharField, ≤500): source Umami PostgreSQL DSN.
        - ``since`` (optional): ``YYYY-MM-DD`` cutoff, cleaned to a ``datetime``.
        - ``replace`` (optional bool): delete the target site's rows first.
    """

    target_website = forms.UUIDField()
    source_website = forms.UUIDField()
    source_dsn = forms.CharField(max_length=500)
    since = forms.CharField(required=False)
    replace = forms.BooleanField(required=False)

    def clean_source_dsn(self) -> str:
        """Require a PostgreSQL DSN. The value is validated, never stored."""
        dsn = (self.cleaned_data.get("source_dsn") or "").strip()
        if not (dsn.startswith("postgres://") or dsn.startswith("postgresql://")):
            raise forms.ValidationError("DSN must be a postgres:// connection string.")
        return dsn

    def clean_since(self) -> datetime | None:
        """Parse the optional ``since`` date with the CLI's ``YYYY-MM-DD`` format."""
        raw = (self.cleaned_data.get("since") or "").strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d")  # noqa: DTZ007 — date-only cutoff
        except ValueError as exc:
            raise forms.ValidationError("Invalid date format. Use YYYY-MM-DD.") from exc


# ---------------------------------------------------------------------------
# User management forms (admin CRUD + self-service password change)
# ---------------------------------------------------------------------------


class UserCreateForm(forms.Form):
    """Validate the admin user-creation form.

    Fields:
        - ``username`` (CharField, ≤255, required) — unique login identifier.
        - ``role`` (ChoiceField) — ``"user"`` or ``"admin"``.
        - ``password`` (CharField, min_length=8) — raw password.
        - ``password2`` (CharField) — confirmation.
    """

    username = forms.CharField(max_length=255)
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    password = forms.CharField(min_length=MIN_PASSWORD_LENGTH, widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self) -> str:
        """Strip and reject blank usernames."""
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("Username cannot be empty.")
        return username

    def clean(self) -> dict[str, Any]:
        """Ensure passwords match."""
        cleaned = super().clean()
        pw1 = cleaned.get("password", "")
        pw2 = cleaned.get("password2", "")
        if pw1 and pw2 and pw1 != pw2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned


class UserEditForm(forms.Form):
    """Validate the admin user-edit form (role + optional password reset).

    Fields:
        - ``role`` (ChoiceField) — ``"user"`` or ``"admin"``.
        - ``new_password`` (CharField, optional) — new password (≥ 8 chars).
        - ``new_password2`` (CharField, optional) — confirmation.
    """

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    new_password = forms.CharField(required=False, min_length=MIN_PASSWORD_LENGTH, widget=forms.PasswordInput)
    new_password2 = forms.CharField(required=False, widget=forms.PasswordInput)

    def clean(self) -> dict[str, Any]:
        """Validate optional password fields when provided."""
        cleaned = super().clean()
        pw1 = cleaned.get("new_password", "")
        pw2 = cleaned.get("new_password2", "")
        if pw1 or pw2:
            if pw1 != pw2:
                self.add_error("new_password2", "Passwords do not match.")
        return cleaned


class ChangePasswordForm(forms.Form):
    """Self-service password change form (all logged-in users).

    Fields:
        - ``current_password`` (CharField) — verified by the service layer.
        - ``new_password`` (CharField, min_length=8).
        - ``new_password2`` (CharField) — confirmation.
    """

    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(min_length=MIN_PASSWORD_LENGTH, widget=forms.PasswordInput)
    new_password2 = forms.CharField(widget=forms.PasswordInput)

    def clean(self) -> dict[str, Any]:
        """Ensure new passwords match."""
        cleaned = super().clean()
        pw1 = cleaned.get("new_password", "")
        pw2 = cleaned.get("new_password2", "")
        if pw1 and pw2 and pw1 != pw2:
            self.add_error("new_password2", "Passwords do not match.")
        return cleaned


# ---------------------------------------------------------------------------
# Tracker ingestion form
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Website ModelForm
# ---------------------------------------------------------------------------


class WebsiteModelForm(forms.ModelForm):
    """ModelForm for :class:`apps.core.models.Website`.

    Fields:
        - ``name`` (CharField, ≤100, required) — human-readable label.
        - ``domain`` (CharField, ≤500, optional) — the tracked hostname (e.g.
          ``"example.com"``); used by the tracker to associate events.

    The view that owns the form is responsible for stamping ``user_id`` /
    ``team_id`` before ``save()`` so the website is scoped to the creator.
    """

    class Meta:
        model = Website
        fields = ("name", "domain")

    def clean_name(self) -> str:
        """Strip whitespace and reject blank names.

        Returns:
            The trimmed name string.

        Raises:
            forms.ValidationError: If the name is empty after stripping.
        """
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Name cannot be empty.")
        return name

    def clean_domain(self) -> str:
        """Strip whitespace from the domain, defaulting to empty string.

        Returns:
            The trimmed domain string, or ``""`` when blank.
        """
        return (self.cleaned_data.get("domain") or "").strip() or ""


class TrackerEventForm(forms.Form):
    """Validate the JSON body of ``POST /api/send`` (Umami-compatible).

    Fields:
        - ``type`` (ChoiceField): ``"event"`` or ``"identify"``.
        - ``payload`` (JSONField): the event payload dict. ``website``
          (UUID-string) is required inside the payload — the cross-field
          check is performed in :meth:`clean`.

    The form is **only** the validation layer — actual ingestion is performed
    by :func:`apps.tracker.services.ingest_event` / :func:`ingest_identify`,
    which use raw SQL for performance.
    """

    _MESSAGE_TYPES = (("event", "Event"), ("identify", "Identify"))

    type = forms.ChoiceField(choices=_MESSAGE_TYPES)
    payload = forms.JSONField()

    def clean(self) -> dict[str, Any]:
        """Cross-field validation: ensure ``payload`` is a dict containing ``website``.

        The ``website`` key inside the payload carries the UUID of the tracked
        website that the event belongs to. Without it the ingestion layer
        cannot route the event.

        Returns:
            The cleaned data dict.
        """
        cleaned = super().clean()
        payload = cleaned.get("payload")
        if not isinstance(payload, dict):
            self.add_error("payload", "Payload must be a JSON object.")
            return cleaned
        if not payload.get("website"):
            self.add_error("payload", "Payload must include a 'website' UUID.")
        return cleaned
