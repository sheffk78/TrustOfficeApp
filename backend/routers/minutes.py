# Placeholder routers - these will be gradually migrated from server.py
# For now, these are stub files that can be used as the codebase evolves

from fastapi import APIRouter

# Minutes router placeholder - actual implementation in server.py
router = APIRouter(prefix="/minutes", tags=["minutes"])
# Note: Endpoints are currently served from server.py
