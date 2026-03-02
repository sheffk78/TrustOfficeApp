# Placeholder routers - these will be gradually migrated from server.py
from fastapi import APIRouter

router = APIRouter(prefix="/governance", tags=["governance"])
# Note: Endpoints are currently served from server.py
