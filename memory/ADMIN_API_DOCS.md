# TrustOffice Admin API Documentation

_Created: 2026-04-18_
_Base URL: `https://app.trustoffice.app/api/admin-api`_
_Auth: `X-Admin-API-Key` header_

---

## Authentication

All requests require the `X-Admin-API-Key` header with the admin API key.

Key is stored in: `~/.openclaw/workspace/secrets/trustoffice-admin-api.key`

For Emergent deployment, set environment variable `ADMIN_API_KEY`.

---

## Endpoints

### GET `/stats/summary`

Overall stats (users, trials, purchases, revenue).

```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/stats/summary" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

### GET `/stats/daily`

Daily stats for a specific date.

```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/stats/daily?date=2026-04-18" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

### GET `/users`

List users with filters. Supports query parameters like `?status=trialing`.

```bash
# List all trial users
curl -X GET "https://app.trustoffice.app/api/admin-api/users?status=trialing" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

### GET `/users/{user_id}`

Get specific user details.

```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/users/USER_ID" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

### POST `/users/{user_id}/extend-trial`

Extend a user's trial by X days.

```bash
curl -X POST "https://app.trustoffice.app/api/admin-api/users/USER_ID/extend-trial" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"days": 14}'
```

### POST `/users/{user_id}/gift-subscription`

Gift a subscription to a user. Plan types: `monthly`, `annual`, `forever_free`.

```bash
curl -X POST "https://app.trustoffice.app/api/admin-api/users/USER_ID/gift-subscription" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan_type": "annual", "reason": "VIP customer"}'
```

### GET `/audit-log`

View all admin API actions (audit trail).

```bash
curl -X GET "https://app.trustoffice.app/api/admin-api/audit-log" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

---

## Audit Logging

All Admin API actions are logged to the `admin_api_audit` collection with:
- Action type
- Target user
- Request details
- IP address
- Timestamp

---

## Kit Integration Notes

- **Morning brief:** Use `/stats/summary` for real-time user/revenue numbers
- **User management:** Use `/users?status=trialing` to monitor trial conversions
- **VIP handling:** Use `extend-trial` and `gift-subscription` for special cases (with Jeff approval per autonomy rules)
- **Audit trail:** Check `/audit-log` periodically for accountability