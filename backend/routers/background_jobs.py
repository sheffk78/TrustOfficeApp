# Placeholder routers - these will be gradually migrated from server.py
from fastapi import APIRouter

router = APIRouter(prefix="/background-jobs", tags=["background-jobs"])
# Note: Endpoints are currently served from server.py
