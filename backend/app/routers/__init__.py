from .auth import router as auth_router
from .sites import router as sites_router
from .stats import router as stats_router
from .pages import router as pages_router
from .sources import router as sources_router
from .events import router as events_router
from .sessions import router as sessions_router
from .devices import router as devices_router
from .geo import router as geo_router
from .realtime import router as realtime_router
from .compare import router as compare_router
from .retention import router as retention_router
from .funnels import router as funnels_router
from .journeys import router as journeys_router
from .revenue import router as revenue_router
from .engagement import router as engagement_router
from .filter_values import router as filter_values_router
from .annotations import router as annotations_router
from .saved_views import router as saved_views_router
from .dashboards import router as dashboards_router
from .scheduled_exports import router as scheduled_exports_router
from .api_keys import router as api_keys_router
from .script import router as script_router
from .share import router as share_router
from .cron import router as cron_router
from .bot_config import router as bot_config_router

__all__ = [
    "auth_router",
    "sites_router",
    "stats_router",
    "pages_router",
    "sources_router",
    "events_router",
    "sessions_router",
    "devices_router",
    "geo_router",
    "realtime_router",
    "compare_router",
    "retention_router",
    "funnels_router",
    "journeys_router",
    "revenue_router",
    "engagement_router",
    "filter_values_router",
    "annotations_router",
    "saved_views_router",
    "dashboards_router",
    "scheduled_exports_router",
    "api_keys_router",
    "script_router",
    "share_router",
    "cron_router",
    "bot_config_router",
]
