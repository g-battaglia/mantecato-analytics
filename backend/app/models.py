"""
Pydantic models for request/response validation.
Kept lightweight — most routes return dicts directly from the query layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# -- Auth ---------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: dict[str, Any]


# -- Annotations --------------------------------------------------------------


class AnnotationCreate(BaseModel):
    title: str
    description: str = ""
    date: str
    color: str = "blue"


# -- Saved Views --------------------------------------------------------------


class SavedViewCreate(BaseModel):
    name: str
    description: str = ""
    config: dict[str, Any]


class SavedViewUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None


# -- Dashboards ---------------------------------------------------------------


class DashboardCreate(BaseModel):
    name: str
    description: str = ""
    websiteId: str
    config: dict | None = None


class DashboardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None


# -- Scheduled Exports --------------------------------------------------------


class ScheduledExportCreate(BaseModel):
    name: str
    description: str = ""
    config: dict[str, Any]


class ScheduledExportUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None


# -- API Keys -----------------------------------------------------------------


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = ["read", "write"]
