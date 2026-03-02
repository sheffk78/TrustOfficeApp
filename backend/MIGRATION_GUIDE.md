# Backend Migration Guide

## Current State (Mar 2, 2026)

The TrustOffice backend is currently a monolithic FastAPI application in `server.py` (~7600 lines).
A modular router structure has been created in `/app/backend/routers/` for gradual migration.

## Architecture

```
/app/backend/
├── server.py           # Main monolithic app (will shrink as routers migrate)
├── database.py         # MongoDB connection singleton (SHARED)
├── models.py           # All Pydantic models (~750 lines, SHARED)
├── dependencies.py     # Auth, middleware, helpers (SHARED)
├── email_service.py    # Postmark email integration
├── email_templates.py  # Email template content
├── background_tasks.py # APScheduler background jobs
└── routers/            # Domain-specific router modules
    ├── __init__.py     # Router exports and status
    ├── auth.py         # ✅ READY (350 lines)
    ├── trusts.py       # ✅ READY (70 lines)
    ├── entities.py     # ✅ READY (120 lines)
    ├── tasks.py        # ✅ READY (80 lines)
    ├── units.py        # ✅ READY (660 lines)
    └── [others]        # ⏳ Placeholder stubs
```

## Shared Modules

### database.py
```python
from database import db
# Use db.collection_name for all MongoDB operations
```

### models.py
All Pydantic models are centralized here:
- User models (UserCreate, UserLogin, UserResponse, etc.)
- Trust models (TrustCreate, TrustUpdate, TrustResponse, etc.)
- Distribution models
- Minutes models
- Subscription models
- etc.

### dependencies.py
Shared dependencies and helpers:
- `get_current_user(request)`: Auth dependency
- `require_write_access(user)`: Blocks writes for expired subscriptions
- `get_subscription_state(user_id)`: Returns SubscriptionState object
- `should_show_watermark(user_id)`: PDF watermark check
- `auto_update_onboarding(user_id, trust_id)`: Onboarding state updates
- `create_initial_governance_tasks(trust_id, user_id)`: Task seeding

## Migration Process

### Step 1: Identify Endpoints
Use grep to find all endpoints for a domain:
```bash
grep -n "@api_router.*distribution\|/distribution" server.py
```

### Step 2: Create Router File
```python
# routers/distributions.py
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, require_write_access, auto_update_onboarding
from models import DistributionCreate, DistributionUpdate, DistributionResponse
from email_service import email_service

router = APIRouter(prefix="/distributions", tags=["distributions"])

@router.post("", response_model=DistributionResponse)
async def create_distribution(
    dist: DistributionCreate, 
    background_tasks: BackgroundTasks, 
    user: dict = Depends(require_write_access)  # Note: require_write_access for writes
):
    # ... endpoint code
```

### Step 3: Include Router in App
In server.py, add:
```python
from routers.distributions import router as distributions_router
app.include_router(distributions_router, prefix="/api")
```

### Step 4: Remove from server.py
After testing, remove the migrated endpoints from server.py.

### Step 5: Test Thoroughly
```bash
# Test read operations
curl -s "$API_URL/api/distributions?trust_id=..." -H "Authorization: Bearer $TOKEN"

# Test write operations
curl -s -X POST "$API_URL/api/distributions" ...
```

## Migration Priority

1. **High Priority** (frequent use, complex logic):
   - distributions.py (includes benevolence)
   - minutes.py (includes templates)
   - governance.py (health score)

2. **Medium Priority** (moderate use):
   - schedule_a.py
   - compensation.py
   - dashboard.py

3. **Low Priority** (infrequent use):
   - exports.py
   - subscriptions.py (Stripe integration)
   - background_jobs.py

## Key Considerations

### Write Access
All write endpoints (POST, PUT, PATCH, DELETE) should use `require_write_access`:
```python
@router.post("", response_model=Response)
async def create_item(
    item: ItemCreate, 
    user: dict = Depends(require_write_access)  # Blocks if subscription expired
):
```

### Read Access
Read endpoints use `get_current_user`:
```python
@router.get("", response_model=List[Response])
async def list_items(user: dict = Depends(get_current_user)):  # Always allowed
```

### Email Service
Import email_service for notification emails:
```python
from email_service import email_service
# In endpoint:
background_tasks.add_task(email_service.send_notification, ...)
```

### MongoDB ObjectId
Always exclude `_id` in projections:
```python
await db.collection.find(query, {"_id": 0}).to_list(1000)
```

## Testing

After migration, run:
1. Backend API tests (curl commands)
2. Frontend integration tests (screenshot tool)
3. Full testing agent suite

```bash
# Quick backend test
API_URL="https://..." && TOKEN="..." && \
curl -s "$API_URL/api/[endpoint]" -H "Authorization: Bearer $TOKEN"
```
