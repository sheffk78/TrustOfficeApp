# Placeholder routers - these will be gradually migrated from server.py
from fastapi import APIRouter

router = APIRouter(prefix="/compensation", tags=["compensation"])
# Note: Endpoints are currently served from server.py
