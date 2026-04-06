from __future__ import annotations

import os
from typing import Any

import httpx


class RemoteClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("MANTECATO_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        client = await self._get_client()
        response = await client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def post(self, path: str, json_data: dict[str, Any] | None = None) -> Any:
        client = await self._get_client()
        response = await client.post(path, json=json_data)
        response.raise_for_status()
        return response.json()

    async def delete(self, path: str) -> Any:
        client = await self._get_client()
        response = await client.delete(path)
        response.raise_for_status()
        return response.json()

    def _resolve_site(self, site: str) -> str:
        return site

    def _build_params(
        self,
        site: str | None = None,
        period: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filter: list[str] | None = None,
        granularity: str | None = None,
        limit: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if period:
            params["range"] = period
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if filter:
            params["f"] = filter
        if granularity:
            params["granularity"] = granularity
        if limit:
            params["limit"] = limit
        params.update(extra)
        return params

    async def list_sites(self) -> list[dict]:
        return await self.get("/api/sites")

    async def get_stats(self, site: str, **kwargs) -> dict:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/stats", params)

    async def get_timeseries(self, site: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        section_params = {**params, "section": "timeseries"}
        return await self.get(f"/api/sites/{site}/stats", section_params)

    async def get_pages(self, site: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/pages", params)

    async def get_sources(self, site: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/sources", params)

    async def get_events(self, site: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/events", params)

    async def get_sessions(self, site: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/sessions", params)

    async def get_devices(
        self, site: str, device_type: str = "browser", **kwargs
    ) -> list:
        params = self._build_params(**kwargs)
        params["type"] = device_type
        return await self.get(f"/api/sites/{site}/devices", params)

    async def get_geo(self, site: str, geo_type: str = "country", **kwargs) -> list:
        params = self._build_params(**kwargs)
        params["type"] = geo_type
        return await self.get(f"/api/sites/{site}/geo", params)

    async def get_realtime(self, site: str) -> dict:
        return await self.get(f"/api/sites/{site}/realtime")

    async def get_comparison(self, site: str, **kwargs) -> dict:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/compare", params)

    async def get_retention(self, site: str, **kwargs) -> dict:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/retention", params)

    async def get_funnels(self, site: str, **kwargs) -> dict:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/funnels", params)

    async def get_journeys(self, site: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/journeys", params)

    async def get_revenue(self, site: str, **kwargs) -> dict:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/revenue", params)

    async def get_engagement(self, site: str, **kwargs) -> dict:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/engagement", params)

    async def get_filter_values(self, site: str, column: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        params["column"] = column
        return await self.get(f"/api/sites/{site}/filter-values", params)

    async def list_annotations(self, site: str, **kwargs) -> list:
        params = self._build_params(**kwargs)
        return await self.get(f"/api/sites/{site}/annotations", params)

    async def create_annotation(self, site: str, data: dict) -> dict:
        return await self.post(f"/api/sites/{site}/annotations", data)

    async def delete_annotation(self, site: str, annotation_id: str) -> dict:
        return await self.delete(f"/api/sites/{site}/annotations/{annotation_id}")

    async def list_saved_views(self, site: str) -> list:
        return await self.get(f"/api/sites/{site}/saved-views")

    async def get_saved_view(self, site: str, view_id: str) -> dict:
        return await self.get(f"/api/sites/{site}/saved-views/{view_id}")

    async def create_saved_view(self, site: str, data: dict) -> dict:
        return await self.post(f"/api/sites/{site}/saved-views", data)

    async def delete_saved_view(self, site: str, view_id: str) -> dict:
        return await self.delete(f"/api/sites/{site}/saved-views/{view_id}")

    async def list_dashboards(self, site: str) -> list:
        return await self.get(f"/api/sites/{site}/dashboards")

    async def get_dashboard(self, site: str, dashboard_id: str) -> dict:
        return await self.get(f"/api/sites/{site}/dashboards/{dashboard_id}")

    async def delete_dashboard(self, site: str, dashboard_id: str) -> dict:
        return await self.delete(f"/api/sites/{site}/dashboards/{dashboard_id}")

    async def list_scheduled_exports(self, site: str) -> list:
        return await self.get(f"/api/sites/{site}/scheduled-exports")

    async def get_scheduled_export(self, site: str, export_id: str) -> dict:
        return await self.get(f"/api/sites/{site}/scheduled-exports/{export_id}")

    async def delete_scheduled_export(self, site: str, export_id: str) -> dict:
        return await self.delete(f"/api/sites/{site}/scheduled-exports/{export_id}")
