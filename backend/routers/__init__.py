# TrustOffice API Routers
# 
# MIGRATION STATUS:
# The main application currently runs from server.py (7600+ lines).
# This routers/ directory contains the modular structure for gradual migration.
#
# COMPLETED ROUTERS (ready for use):
# - auth.py: Authentication, profile, notifications
# - trusts.py: Trust CRUD operations
# - entities.py: Entity management and relationships
# - tasks.py: Governance tasks
# - units.py: Trust certificate units with PDF generation
#
# PLACEHOLDER ROUTERS (for future migration):
# - minutes.py: Minutes records and templates
# - schedule_a.py: Schedule A asset management
# - distributions.py: Distributions and benevolence
# - benevolence.py: Benevolence records (deprecated - use distributions)
# - compensation.py: Compensation plans and payments
# - governance.py: Health score and insights
# - dashboard.py: Unified dashboard endpoint
# - subscriptions.py: Stripe integration
# - exports.py: CSV export endpoints
# - email_admin.py: Email admin endpoints
# - background_jobs.py: Background task management
# - demo.py: Demo data seeding
#
# MIGRATION STRATEGY:
# 1. Routers import shared code from database.py, models.py, dependencies.py
# 2. Migrate endpoints one domain at a time
# 3. Test thoroughly after each migration
# 4. Eventually remove migrated code from server.py
#
# To use a completed router in server.py, add:
#   from routers.auth import router as auth_router
#   app.include_router(auth_router, prefix="/api")

from .auth import router as auth_router, notifications_router, user_prefs_router
from .trusts import router as trusts_router
from .entities import router as entities_router
from .units import router as units_router
from .tasks import router as tasks_router

# Placeholder imports for when migration is complete
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
    # Ready for use
    "auth_router",
    "notifications_router",
    "user_prefs_router",
    "trusts_router",
    "entities_router",
    "units_router",
    "tasks_router",
    # Placeholders
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
