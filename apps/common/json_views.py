"""JSON CBV base classes — Django-native, DRF-free.

These class-based views replace the manual request-body parsing, manual
validation, and manual error responses that previously littered every
endpoint in :mod:`apps.api.views`. They are intentionally minimal so they
remain easy to audit (no metaclass magic, no implicit serializer registry).

The four building blocks cover every CRUD shape currently used by the JSON
API:

- :class:`JSONListView` — ``GET`` returning an array (optionally paginated).
- :class:`JSONDetailView` — ``GET`` returning a single object by URL kwarg.
- :class:`JSONFormView` — ``POST`` validated by a Django ``Form`` /
  ``ModelForm``, executed inside ``transaction.atomic``.
- :class:`JSONDeleteView` — ``POST`` that deletes a row by URL kwarg.

All four extend :class:`JSONView`, which disables CSRF on ``dispatch``
because JSON endpoints authenticate via Bearer API keys instead of session
cookies (see :class:`mantecato.middleware.ApiKeyMiddleware`).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.api.serializers import sanitize_for_json
from apps.common.http import safe_int

if TYPE_CHECKING:
    from django import forms
    from django.db.models import QuerySet
    from django.http import HttpRequest


def json_response(data: object, status: int = 200) -> JsonResponse:
    """Build a :class:`~django.http.JsonResponse` after sanitizing values.

    Args:
        data: The payload (dict / list / scalar). Non-JSON types (datetime,
            Decimal, UUID, bytes) are normalised via
            :func:`apps.api.serializers.sanitize_for_json`.
        status: HTTP status code (default ``200``).

    Returns:
        A ready-to-return ``JsonResponse``. ``safe=False`` so lists are
        allowed at the top level.
    """
    return JsonResponse(sanitize_for_json(data), safe=False, status=status)


@method_decorator(csrf_exempt, name="dispatch")
class JSONView(View):
    """Base class for JSON endpoints.

    CSRF protection is disabled because all JSON endpoints authenticate via
    the ``Authorization: Bearer mtk_...`` header, validated by
    :class:`mantecato.middleware.ApiKeyMiddleware`. Session-cookie CSRF is
    therefore irrelevant.

    Subclasses typically combine this with
    :class:`apps.common.mixins.ApiAuthMixin` (read) or
    :class:`apps.common.mixins.ApiWriteMixin` (write).
    """


class JSONListView(JSONView):
    """``GET`` endpoint returning ``{response_key: [...]}``.

    Subclasses define:

    Attributes:
        response_key (str): top-level key for the array (e.g. ``"dashboards"``).
        get_queryset: returns the iterable / queryset of items.
        serialize(obj) (optional): per-item serialization. Defaults to
            ``obj.to_dict()`` when available, otherwise returns the object as-is.

    Optional pagination:

    Attributes:
        paginate (bool): set ``True`` to honour ``?page=`` / ``?page_size=``.
            When enabled the response also includes ``page``, ``pageSize``,
            ``total``, and ``totalPages`` metadata.
        default_page_size (int): default 50.
        max_page_size (int): default 500 (cap to protect the database).

    Example:
        .. code-block:: python

            class DashboardJSONListView(ApiAuthMixin, JSONListView):
                response_key = "dashboards"
                def get_queryset(self):
                    return Dashboard.objects.filter(
                        user_id=self.request.api_user_id
                    ).order_by("-updated_at")
    """

    response_key: str = "items"
    paginate: bool = False
    default_page_size: int = 50
    max_page_size: int = 500

    def get_queryset(self) -> QuerySet | list:
        raise NotImplementedError("JSONListView subclasses must define get_queryset().")

    def serialize(self, obj: object) -> object:
        """Return a JSON-safe representation of *obj* (default: ``obj.to_dict()``)."""
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return obj

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Handle GET: serialize the queryset, optionally paginating.

        When :attr:`paginate` is ``False`` the full list is returned.
        When ``True``, ``?page=`` and ``?page_size=`` control the window;
        ``page_size`` is clamped to :attr:`max_page_size` to prevent
        unbounded queries.

        Returns:
            A :func:`json_response` containing the serialized items and,
            when paginating, ``page``, ``pageSize``, ``total``, and
            ``totalPages`` metadata keys.
        """
        qs = self.get_queryset()
        if not self.paginate:
            return json_response({self.response_key: [self.serialize(o) for o in qs]})

        page = max(1, safe_int(request.GET.get("page"), default=1))
        page_size = max(
            1,
            min(
                safe_int(request.GET.get("page_size"), default=self.default_page_size),
                self.max_page_size,
            ),
        )
        total = qs.count() if hasattr(qs, "count") else len(qs)
        offset = (page - 1) * page_size
        items = list(qs[offset : offset + page_size])
        return json_response(
            {
                self.response_key: [self.serialize(o) for o in items],
                "page": page,
                "pageSize": page_size,
                "total": total,
                "totalPages": (total + page_size - 1) // page_size if page_size else 1,
            }
        )


class JSONDetailView(JSONView):
    """``GET`` endpoint returning a single serialized object.

    Subclasses define:

    Attributes:
        lookup_url_kwarg (str): URL kwarg carrying the lookup value (e.g.
            ``"report_id"``).
        lookup_field (str): model field used for the lookup (default ``"id"``).
        get_queryset: returns the queryset to filter against — typically
            scoped to the acting principal via ownership.
        serialize(obj) (optional): default ``obj.to_dict()``.
        not_found_message (str): error message returned with HTTP 404 when no
            row matches.

    Example:
        .. code-block:: python

            class DashboardJSONDetailView(ApiAuthMixin, JSONDetailView):
                lookup_url_kwarg = "report_id"
                not_found_message = "Dashboard not found."
                def get_queryset(self):
                    return Dashboard.objects.filter(
                        user_id=self.request.api_user_id
                    )
    """

    lookup_url_kwarg: str = "pk"
    lookup_field: str = "id"
    not_found_message: str = "Not found."

    def get_queryset(self) -> QuerySet:
        raise NotImplementedError("JSONDetailView subclasses must define get_queryset().")

    def serialize(self, obj: object) -> object:
        """Return a JSON-safe representation of *obj* (default: ``obj.to_dict()``)."""
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return obj

    def get_object(self) -> object | None:
        """Look up the object by URL kwarg against the ownership-scoped queryset.

        Returns:
            The matched model instance, or ``None`` if no row matches the
            lookup value for the acting principal.
        """
        qs = self.get_queryset()
        lookup_value = self.kwargs.get(self.lookup_url_kwarg)
        return qs.filter(**{self.lookup_field: lookup_value}).first()

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Handle GET: return the serialized object or a 404 error.

        Returns:
            200 with the serialized object, or 404 with
            ``{"error": not_found_message}``.
        """
        obj = self.get_object()
        if obj is None:
            return json_response({"error": self.not_found_message}, status=404)
        return json_response(self.serialize(obj))


class JSONFormView(JSONView):
    """``POST`` endpoint that validates the JSON body through a Django ``Form``.

    The flow on every request is:

    1. Parse the request body as JSON; ``400`` on malformed input.
    2. Instantiate ``self.form_class(data=parsed_body)``.
    3. If ``form.is_valid()`` is ``False`` → ``400`` with
       ``{"errors": form.errors.get_json_data()}``.
    4. Otherwise invoke ``self.perform(form, request)`` inside
       :func:`django.db.transaction.atomic` and return its dict as JSON with
       :attr:`success_status`.

    Subclasses define:

    Attributes:
        form_class (type[forms.Form]): the form / model form class.
        success_status (int): HTTP status on success (default ``200``; use
            ``201`` for create endpoints).
        perform(form, request) -> dict: business logic.

    Example:
        .. code-block:: python

            class DashboardJSONCreateView(ApiWriteMixin, JSONFormView):
                form_class = DashboardModelForm
                success_status = 201

                def perform(self, form, request):
                    form.instance.user_id = request.api_user_id
                    dashboard = form.save()
                    return {"dashboard": dashboard.to_dict()}
    """

    form_class: type[forms.Form] | None = None
    success_status: int = 200

    def perform(self, form: forms.Form, request: HttpRequest) -> object:
        raise NotImplementedError("JSONFormView subclasses must define perform().")

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Handle POST: parse JSON body, validate via the form, then perform.

        Processing steps:
            1. Parse ``request.body`` as JSON (400 on failure).
            2. Instantiate :attr:`form_class` with the parsed dict.
            3. Validate -- return 400 with ``{"errors": ...}`` on failure.
            4. Call :meth:`perform` inside ``transaction.atomic`` so the
               business logic is all-or-nothing.
            5. Return the result dict with :attr:`success_status`.

        Returns:
            :func:`json_response` wrapping the dict returned by :meth:`perform`.
        """
        if self.form_class is None:
            return json_response({"error": "Form not configured."}, status=500)
        try:
            data = json.loads(request.body) if request.body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return json_response({"error": "Invalid JSON body."}, status=400)

        form = self.form_class(data=data)
        if not form.is_valid():
            return json_response(
                {"errors": form.errors.get_json_data()},
                status=400,
            )
        with transaction.atomic():
            result = self.perform(form, request)
        return json_response(result, status=self.success_status)


class JSONDeleteView(JSONView):
    """``POST`` endpoint that deletes a row identified by URL kwarg.

    Subclasses define:

    Attributes:
        lookup_url_kwarg (str): URL kwarg holding the lookup value.
        lookup_field (str): model field (default ``"id"``).
        get_queryset: returns the ownership-scoped queryset to delete from.
        not_found_message (str): returned with HTTP 404 when nothing was
            deleted.

    The deletion runs in a :func:`~django.db.transaction.atomic` block so
    cascades (or signals that fan out) are all-or-nothing.

    Response on success::

        {"deleted": true}

    Example:
        .. code-block:: python

            class DashboardJSONDeleteView(ApiWriteMixin, JSONDeleteView):
                lookup_url_kwarg = "report_id"
                not_found_message = "Dashboard not found."
                def get_queryset(self):
                    return Dashboard.objects.filter(
                        user_id=self.request.api_user_id
                    )
    """

    lookup_url_kwarg: str = "pk"
    lookup_field: str = "id"
    not_found_message: str = "Not found."

    def get_queryset(self) -> QuerySet:
        raise NotImplementedError("JSONDeleteView subclasses must define get_queryset().")

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Handle POST: delete the row identified by the URL kwarg.

        The deletion runs inside ``transaction.atomic`` so any cascaded
        deletes or signal side-effects are all-or-nothing.

        Returns:
            200 with ``{"deleted": true}`` on success, or 404 with
            ``{"error": not_found_message}`` when no row matched.
        """
        qs = self.get_queryset()
        lookup_value = self.kwargs.get(self.lookup_url_kwarg)
        with transaction.atomic():
            deleted, _ = qs.filter(**{self.lookup_field: lookup_value}).delete()
        if deleted == 0:
            return json_response({"error": self.not_found_message}, status=404)
        return json_response({"deleted": True})
