"""Unit tests for :mod:`apps.common.json_views`.

The four base classes (``JSONListView``, ``JSONDetailView``, ``JSONFormView``,
``JSONDeleteView``) are exercised via :class:`~django.test.RequestFactory`
and lightweight in-test subclasses that stub ``get_queryset`` / ``perform``.

No database hits — the tests target the request/response contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from django import forms
from django.test import RequestFactory

from apps.common.json_views import (
    JSONDeleteView,
    JSONDetailView,
    JSONFormView,
    JSONListView,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_atomic() -> object:
    """Replace ``transaction.atomic`` with a no-op context manager.

    The base classes wrap mutating endpoints in ``transaction.atomic``; in
    unit tests we never want to hit the database, so we stub the helper to
    keep the request/response contract exercise hermetic.
    """
    with patch("apps.common.json_views.transaction.atomic") as mock_atomic:
        mock_atomic.return_value.__enter__ = lambda *_: None
        mock_atomic.return_value.__exit__ = lambda *_: None
        yield mock_atomic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeQuerySet(list):
    """A list with a Django-style ``count()`` for paginated tests."""

    def count(self) -> int:
        return len(self)


class _Obj:
    """Simple object exposing ``to_dict`` like the proxy models do."""

    def __init__(self, oid: int, name: str) -> None:
        self.id = oid
        self.name = name

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


@pytest.fixture
def request_factory() -> RequestFactory:
    return RequestFactory()


# ---------------------------------------------------------------------------
# JSONListView
# ---------------------------------------------------------------------------


class _SimpleList(JSONListView):
    response_key = "things"

    def get_queryset(self) -> list:
        return [_Obj(1, "a"), _Obj(2, "b")]


class _PaginatedList(JSONListView):
    response_key = "things"
    paginate = True
    default_page_size = 2

    def get_queryset(self) -> _FakeQuerySet:
        return _FakeQuerySet([_Obj(i, f"obj{i}") for i in range(5)])


class TestJSONListView:
    def test_returns_keyed_array(self, request_factory: RequestFactory) -> None:
        response = _SimpleList.as_view()(request_factory.get("/x/"))
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body == {"things": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]}

    def test_paginated_response_includes_meta(
        self, request_factory: RequestFactory
    ) -> None:
        response = _PaginatedList.as_view()(request_factory.get("/x/?page=1"))
        body = json.loads(response.content)
        assert body["page"] == 1
        assert body["pageSize"] == 2
        assert body["total"] == 5
        assert body["totalPages"] == 3
        assert len(body["things"]) == 2

    def test_pagination_second_page(self, request_factory: RequestFactory) -> None:
        response = _PaginatedList.as_view()(request_factory.get("/x/?page=2"))
        body = json.loads(response.content)
        assert body["page"] == 2
        assert len(body["things"]) == 2

    def test_pagination_clamps_excessive_page_size(
        self, request_factory: RequestFactory
    ) -> None:
        response = _PaginatedList.as_view()(
            request_factory.get("/x/?page=1&page_size=99999")
        )
        body = json.loads(response.content)
        assert body["pageSize"] == _PaginatedList.max_page_size


# ---------------------------------------------------------------------------
# JSONDetailView
# ---------------------------------------------------------------------------


class _SimpleDetail(JSONDetailView):
    lookup_url_kwarg = "thing_id"
    not_found_message = "Thing not found."

    def get_queryset(self) -> object:
        qs = MagicMock()

        def _filter(**kwargs: object) -> MagicMock:
            inner = MagicMock()
            inner.first.return_value = _Obj(1, "a") if kwargs.get("id") == 1 else None
            return inner

        qs.filter.side_effect = _filter
        return qs


class TestJSONDetailView:
    def test_found_returns_serialized_object(
        self, request_factory: RequestFactory
    ) -> None:
        response = _SimpleDetail.as_view()(request_factory.get("/x/"), thing_id=1)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body == {"id": 1, "name": "a"}

    def test_missing_returns_404(self, request_factory: RequestFactory) -> None:
        response = _SimpleDetail.as_view()(request_factory.get("/x/"), thing_id=999)
        body = json.loads(response.content)
        assert response.status_code == 404
        assert body == {"error": "Thing not found."}


# ---------------------------------------------------------------------------
# JSONFormView
# ---------------------------------------------------------------------------


class _SampleForm(forms.Form):
    name = forms.CharField(max_length=10)


class _CreateView(JSONFormView):
    form_class = _SampleForm
    success_status = 201

    def perform(self, form: forms.Form, request: HttpRequest) -> dict:
        return {"created": form.cleaned_data["name"]}


class TestJSONFormView:
    def _post(
        self, rf: RequestFactory, body: str, content_type: str = "application/json"
    ) -> object:
        request = rf.post("/x/", data=body, content_type=content_type)
        return _CreateView.as_view()(request)

    def test_valid_body_runs_perform_and_returns_success_status(
        self, request_factory: RequestFactory
    ) -> None:
        response = self._post(request_factory, json.dumps({"name": "abc"}))
        body = json.loads(response.content)
        assert response.status_code == 201
        assert body == {"created": "abc"}

    def test_validation_error_returns_400_with_field_errors(
        self, request_factory: RequestFactory
    ) -> None:
        response = self._post(request_factory, json.dumps({"name": "x" * 20}))
        body = json.loads(response.content)
        assert response.status_code == 400
        assert "errors" in body
        assert "name" in body["errors"]

    def test_missing_field_returns_400(self, request_factory: RequestFactory) -> None:
        response = self._post(request_factory, "{}")
        body = json.loads(response.content)
        assert response.status_code == 400
        assert "errors" in body

    def test_invalid_json_returns_400(self, request_factory: RequestFactory) -> None:
        response = self._post(request_factory, "{not valid")
        body = json.loads(response.content)
        assert response.status_code == 400
        assert body == {"error": "Invalid JSON body."}

    def test_perform_wrapped_in_atomic(
        self, request_factory: RequestFactory, _stub_atomic: object
    ) -> None:
        """The ``transaction.atomic`` context manager must wrap ``perform``."""
        self._post(request_factory, json.dumps({"name": "abc"}))
        _stub_atomic.assert_called_once()


# ---------------------------------------------------------------------------
# JSONDeleteView
# ---------------------------------------------------------------------------


class _DeleteExisting(JSONDeleteView):
    lookup_url_kwarg = "thing_id"
    not_found_message = "Thing not found."

    def get_queryset(self) -> object:
        qs = MagicMock()
        qs.filter.return_value.delete.return_value = (1, {"app.Thing": 1})
        return qs


class _DeleteMissing(JSONDeleteView):
    lookup_url_kwarg = "thing_id"
    not_found_message = "Thing not found."

    def get_queryset(self) -> object:
        qs = MagicMock()
        qs.filter.return_value.delete.return_value = (0, {})
        return qs


class TestJSONDeleteView:
    def test_existing_row_returns_deleted_true(
        self, request_factory: RequestFactory
    ) -> None:
        response = _DeleteExisting.as_view()(request_factory.post("/x/"), thing_id=1)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body == {"deleted": True}

    def test_missing_row_returns_404(self, request_factory: RequestFactory) -> None:
        response = _DeleteMissing.as_view()(request_factory.post("/x/"), thing_id=99)
        body = json.loads(response.content)
        assert response.status_code == 404
        assert body == {"error": "Thing not found."}
