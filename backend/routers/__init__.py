# TrustOffice API Routers
# Each router handles a specific domain of the application

from .auth import router as auth_router
from .trusts import router as trusts_router
from .entities import router as entities_router
from .units import router as units_router
from .tasks import router as tasks_router
from .minutes import router as minutes_router
from .schedule_a import router as schedule_a_router
from .distributions import router as distributions_router
from .benevolence import router as benevolence_router
from .compensation import router as compensation_router
from .governance import router as governance_router
from .dashboard import router as dashboard_router
from .subscriptions import router as subscriptions_router
from .exports import router as exports_router
from .email_admin import router as email_admin_router
from .background_jobs import router as background_jobs_router
from .demo import router as demo_router

__all__ = [
    "auth_router",
    "trusts_router",
    "entities_router",
    "units_router",
    "tasks_router",
    "minutes_router",
    "schedule_a_router",
    "distributions_router",
    "benevolence_router",
    "compensation_router",
    "governance_router",
    "dashboard_router",
    "subscriptions_router",
    "exports_router",
    "email_admin_router",
    "background_jobs_router",
    "demo_router",
]
