# TrustOffice Admin API Documentation

## Overview

The Admin API provides programmatic access for AI agents and automation tools to manage TrustOffice users and retrieve statistics.

**Base URL:** `https://app.trustoffice.app/api/admin-api`

**Authentication:** API Key via `X-Admin-API-Key` header

**Rate Limit:** 100 requests per minute

---

## Authentication

All requests must include the API key in the header:

```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/stats/summary" \
  -H "X-Admin-API-Key: YOUR_API_KEY"
```

---

## Endpoints

### 1. Get Summary Statistics

**GET** `/stats/summary`

Returns overall statistics for the platform.

**Response:**
```json
{
  "users": {
    "total": 54,
    "new_last_7_days": 3,
    "new_last_30_days": 12
  },
  "subscriptions": {
    "active": 15,
    "trialing": 23,
    "expired": 8,
    "canceled": 2,
    "forever_free": 3
  },
  "plans": {
    "monthly_active": 10,
    "annual_active": 5
  },
  "revenue": {
    "total_cents": 125000,
    "total_formatted": "$1,250.00",
    "transaction_count": 18
  },
  "generated_at": "2026-04-18T12:00:00+00:00"
}
```

---

### 2. Get Daily Statistics

**GET** `/stats/daily`

Returns statistics for a specific date.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `date` | string | Date in YYYY-MM-DD format. Defaults to today. |

**Example:**
```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/stats/daily?date=2026-04-17" \
  -H "X-Admin-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "date": "2026-04-17",
  "stats": {
    "new_users": 5,
    "new_trials": 4,
    "new_purchases": 2,
    "purchase_transactions": 2
  },
  "generated_at": "2026-04-18T12:00:00+00:00"
}
```

---

### 3. List Users

**GET** `/users`

Returns a paginated list of users with optional filters.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by subscription status: `trialing`, `active`, `expired`, `canceled`, `forever_free` |
| `created_after` | string | Filter users created after this date (YYYY-MM-DD) |
| `created_before` | string | Filter users created before this date (YYYY-MM-DD) |
| `search` | string | Search by email or name |
| `limit` | int | Number of results (1-100, default: 50) |
| `skip` | int | Number of results to skip (default: 0) |

**Example:**
```bash
# Get all users currently in trial
curl -X GET "https://app.trustoffice.app/api/admin-api/users?status=trialing&limit=10" \
  -H "X-Admin-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "users": [
    {
      "user_id": "user_abc123",
      "email": "john@example.com",
      "name": "John Smith",
      "created_at": "2026-04-15T10:30:00+00:00",
      "is_admin": false,
      "subscription": {
        "status": "trialing",
        "plan": null,
        "trial_end": "2026-04-29T10:30:00+00:00"
      },
      "trust_count": 2
    }
  ],
  "total": 23,
  "limit": 10,
  "skip": 0
}
```

---

### 4. Get User Details

**GET** `/users/{user_id}`

Returns detailed information about a specific user.

**Example:**
```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/users/user_abc123" \
  -H "X-Admin-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "user": {
    "user_id": "user_abc123",
    "email": "john@example.com",
    "name": "John Smith",
    "created_at": "2026-04-15T10:30:00+00:00",
    "is_admin": false
  },
  "subscription": {
    "subscription_id": "sub_xyz789",
    "status": "trialing",
    "plan": null,
    "trial_start": "2026-04-15T10:30:00+00:00",
    "trial_end": "2026-04-29T10:30:00+00:00"
  },
  "stats": {
    "trust_count": 2,
    "minutes_count": 5,
    "distributions_count": 3
  }
}
```

---

### 5. Extend Trial Period

**POST** `/users/{user_id}/extend-trial`

Extends a user's trial period by a specified number of days.

**Request Body:**
```json
{
  "days": 14
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `days` | int | No | Days to extend (1-365, default: 14) |

**Example:**
```bash
curl -X POST "https://app.trustoffice.app/api/admin-api/users/user_abc123/extend-trial" \
  -H "X-Admin-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'
```

**Response:**
```json
{
  "success": true,
  "message": "Trial extended by 30 days",
  "user_id": "user_abc123",
  "email": "john@example.com",
  "new_trial_end": "2026-05-29T10:30:00+00:00"
}
```

---

### 6. Gift Subscription

**POST** `/users/{user_id}/gift-subscription`

Gifts a subscription to a user (monthly, annual, or forever free).

**Request Body:**
```json
{
  "plan_type": "monthly",
  "reason": "Customer appreciation"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plan_type` | string | Yes | One of: `monthly`, `annual`, `forever_free` |
| `reason` | string | No | Reason for gifting (logged for audit) |

**Plan Details:**
- `monthly`: 30 days of active subscription
- `annual`: 365 days of active subscription
- `forever_free`: Permanent free access

**Example:**
```bash
curl -X POST "https://app.trustoffice.app/api/admin-api/users/user_abc123/gift-subscription" \
  -H "X-Admin-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan_type": "annual", "reason": "Lifetime customer"}'
```

**Response:**
```json
{
  "success": true,
  "message": "Gifted annual subscription",
  "user_id": "user_abc123",
  "email": "john@example.com",
  "subscription": {
    "status": "active",
    "plan": "annual",
    "current_period_end": "2027-04-18T12:00:00+00:00"
  }
}
```

---

### 7. Get Audit Log

**GET** `/audit-log`

Returns the Admin API audit log.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `action` | string | Filter by action type |
| `limit` | int | Number of results (1-100, default: 50) |
| `skip` | int | Number of results to skip |

**Example:**
```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/audit-log?limit=10" \
  -H "X-Admin-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "logs": [
    {
      "audit_id": "api_audit_abc123",
      "action": "gift_subscription",
      "details": {
        "target_user_id": "user_abc123",
        "plan_type": "annual"
      },
      "user_id": "user_abc123",
      "ip_address": "192.168.1.1",
      "timestamp": "2026-04-18T12:00:00+00:00"
    }
  ],
  "total": 25,
  "limit": 10,
  "skip": 0
}
```

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Invalid API key"
}
```

### 404 Not Found
```json
{
  "detail": "User not found"
}
```

### 429 Rate Limited
```json
{
  "detail": "Rate limit exceeded. Max 100 requests per minute."
}
```

---

## Rate Limiting

- **Limit:** 100 requests per minute
- **Window:** Rolling 60-second window
- **Scope:** Per IP address

---

## Audit Logging

All API actions are logged to the `admin_api_audit` collection with:
- Action type
- Target user (if applicable)
- Request details
- IP address
- Timestamp

---

## Your API Key

```
to_admin_3Iksf_YmMpApyapMpr0ffZLke9cwqPJx9sh8dhZqqO0
```

**Keep this key secure!** Anyone with this key has full admin access to your user data.

To rotate the key, update the `ADMIN_API_KEY` environment variable in your Emergent Secrets.
