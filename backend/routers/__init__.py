# TrustOffice API Routers
# 
# MIGRATION STATUS (Mar 2, 2026):
# Successfully migrated ALL routers from monolithic server.py
# server.py reduced from 7538 to ~350 lines (95% reduction)
#
# COMPLETED ROUTERS (19 total):
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
# - preferences.py: Notification and user preferences
# - email.py: Email status and test endpoints
# - background_jobs.py: Background job status and triggers
# - categories.py: Enum values for forms
# - beneficiaries.py: Beneficiary dashboard (premium)
# - demo.py: Demo data seeding
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
from .preferences import router as preferences_router
from .email import router as email_router
from .background_jobs import router as background_jobs_router
from .categories import router as categories_router
from .beneficiaries import router as beneficiaries_router
from .demo import router as demo_router
from .ai import router as ai_router

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
    "preferences_router",
    "email_router",
    "background_jobs_router",
    "categories_router",
    "beneficiaries_router",
    "demo_router",
    "ai_router",
]
