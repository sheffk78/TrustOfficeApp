# Placeholder routers - these will be gradually migrated from server.py
from fastapi import APIRouter

router = APIRouter(prefix="/subscription", tags=["subscription"])
# Note: Endpoints are currently served from server.py
