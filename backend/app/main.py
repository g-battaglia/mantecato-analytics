from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from mantecato_core.database import create_pool, close_pool
from .routers import (
    auth_router,
    sites_router,
    stats_router,
    pages_router,
    sources_router,
    events_router,
    sessions_router,
    devices_router,
    geo_router,
    realtime_router,
    compare_router,
    retention_router,
    funnels_router,
    journeys_router,
    revenue_router,
    engagement_router,
    filter_values_router,
    annotations_router,
    saved_views_router,
    dashboards_router,
    scheduled_exports_router,
    api_keys_router,
    script_router,
    share_router,
    cron_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool(dsn=settings.DATABASE_URL)
    yield
    await close_pool()


app = FastAPI(
    title="Mantecato Analytics API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(sites_router)
app.include_router(stats_router)
app.include_router(pages_router)
app.include_router(sources_router)
app.include_router(events_router)
app.include_router(sessions_router)
app.include_router(devices_router)
app.include_router(geo_router)
app.include_router(realtime_router)
app.include_router(compare_router)
app.include_router(retention_router)
app.include_router(funnels_router)
app.include_router(journeys_router)
app.include_router(revenue_router)
app.include_router(engagement_router)
app.include_router(filter_values_router)
app.include_router(annotations_router)
app.include_router(saved_views_router)
app.include_router(dashboards_router)
app.include_router(scheduled_exports_router)
app.include_router(api_keys_router)
app.include_router(script_router)
app.include_router(share_router)
app.include_router(cron_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
