# TrustOffice API Routers
# 
# MIGRATION STATUS (Dec 30, 2025):
# Successfully migrated 13 routers from monolithic server.py
# server.py reduced from 7538 to ~2300 lines (69% reduction)
#
# COMPLETED ROUTERS:
# - auth.py: Authentication, profile management
# - trusts.py: Trust CRUD with governance score
# - entities.py: Entity management and relationships
# - tasks.py: Governance tasks
# - trust_units.py: Trust certificate units with PDF generation
# - minutes.py: Minutes records and templates with PDF
# - schedule_a.py: Schedule A asset management with PDF
# - distributions.py: Distribution records
# - benevolence.py: Benevolence records with summary and PDF
# - compensation.py: Compensation plans and payments
# - governance.py: Health score, history, insights, dashboard
# - subscriptions.py: Stripe integration and webhooks
# - exports.py: CSV export endpoints (premium feature)
#
# REMAINING IN SERVER.PY:
# - Notification preferences endpoints
# - User preferences endpoints
# - Email admin endpoints
# - Background jobs endpoints
# - Demo data seeding
# - Categories endpoint
#
# All routers import from: database.py, models.py, dependencies.py

from .auth import router as auth_router
from .trusts import router as trusts_router
from .entities import router as entities_router
from .tasks import router as tasks_router
from .trust_units import router as trust_units_router
from .minutes import router as minutes_router
from .schedule_a import router as schedule_a_router
from .distributions import router as distributions_router
from .benevolence import router as benevolence_router
from .compensation import router as compensation_router
from .governance import router as governance_router
from .subscriptions import router as subscriptions_router
from .exports import router as exports_router

__all__ = [
    "auth_router",
    "trusts_router",
    "entities_router",
    "tasks_router",
    "trust_units_router",
    "minutes_router",
    "schedule_a_router",
    "distributions_router",
    "benevolence_router",
    "compensation_router",
    "governance_router",
    "subscriptions_router",
    "exports_router",
]
