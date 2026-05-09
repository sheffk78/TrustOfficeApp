# Product State — AgenticTrust Portfolio

**Last updated:** 2026-05-08 20:04 UTC (14:04 MT)

---

## Product Health Snapshot

| Product | Frontend | API Health | Auth Chain | Known Issues | Filmability |
|---------|----------|-----------|------------|--------------|-------------|
| AAV (agentauthority.dev) | ✅ 200 · 515ms · title=OK | ✅ 200 · JSON · 521ms | ✅ signup 422 · login 401 (endpoints exist) | Railway FAILED (informational — live checks pass) | 🟢 A — Demo-ready |
| Safe-Spend (safe-spend.dev) | ✅ 200 · 627ms · title=OK | ✅ 200 · JSON · 649ms | ✅ signup 400 · login 401 (endpoints exist) | Railway FAILED (informational); v1/health now returns 200 (gap resolved) | 🟢 A — Demo-ready |
| ARL (reputationledger.dev) | ✅ 200 · 524ms · DOM populated · 4643 bytes | ✅ 200 · JSON · 570ms | ✅ signup 422 · login 401 (endpoints exist) | Railway FAILED (informational — live checks pass) | 🟢 A — Demo-ready |
| Portfolio (agentictrust.app) | ✅ 200 · 649ms · title=OK | N/A | N/A | None | N/A |

---

## Auth Chain Details

| Product | Signup Endpoint | Signup Status | Login Endpoint | Login Status | Auth Type | Pass? |
|---------|----------------|---------------|----------------|-------------|-----------|-------|
| AAV | POST /api/auth/register | 422 (endpoint exists) | POST /api/auth/login | 401 (endpoint exists) | Cookie (session_token) | ✅ |
| Safe-Spend | POST /api/v1/auth/signup | 400 (endpoint exists) | POST /api/v1/auth/login | 401 (endpoint exists) | Bearer JWT (ss_token) | ✅ |
| ARL | POST /api/auth/signup | 422 (endpoint exists) | POST /api/auth/login | 401 (endpoint exists) | Bearer JWT (access_token) | ✅ |

---

## API Health Endpoint Details

| Product | Endpoint | Status | Content-Type | Response Time | Notes |
|---------|----------|--------|-------------|---------------|-------|
| AAV | /api/v1/health (root) | 200 | application/json | 521ms | Previously returned HTML (SPA catch-all) — now returning JSON ✅ |
| AAV | /api/v1/health (api sub) | 200 | application/json | 567ms | Same fix applied |
| Safe-Spend | /api/health | 200 | application/json; charset=utf-8 | 649ms | Includes DB + Stripe checks |
| Safe-Spend | /api/v1/health | 200 | application/json; charset=utf-8 | 403ms | Previously 404 — now returns full health check ✅ |
| ARL | /api/health | 200 | application/json | 570ms | Returns `{"status":"healthy"}` |

---

## Railway Deploy Status (Informational)

| Service | Service ID | Last Deploy Status | Deploy Date | Notes |
|---------|-----------|-------------------|-------------|-------|
| AAV | 324e4849-4ad0-4dae-8a4a-0f7f7d3a0e7c | FAILED | 2026-04-23 | Live checks pass — zombie build serving |
| Safe-Spend | 03001f77-9cda-4cfb-8fad-eb1e360a947a | FAILED | 2026-04-23 | Live checks pass — zombie build serving |
| ARL | c49a7d6c-07d6-407f-96e3-a79807bdf698 | FAILED | 2026-04-23 | Live checks pass — zombie build serving |

> ⚠️ All three Railway services show FAILED deploy status. Per deploy-status decoupling policy, this is **informational only** — live HTTP/API/auth checks all pass. No tickets generated for Railway FAILED status alone.

---

## Previously Resolved Issues

| Date | Product | Issue | Resolution |
|------|---------|-------|------------|
| 2026-05-08 | Safe-Spend | Spend endpoint 500 error | Fixed: Date type mismatch, raw SQL timestamp, invalid Prisma fields |
| 2026-05-02 | ARL | Blank frontend (empty #root) | Resolved — DOM now populated with content |
| 2026-05-08 | AAV | SPA catch-all intercepting /api/v1/health | Resolved — now returns JSON correctly |
| 2026-05-08 | Safe-Spend | /api/v1/health returning 404 | Resolved — now returns 200 with full health check |
| 2026-05-08 | Discord | 503 Server Error on message send | Delivery failed — Discord platform outage, retry on next run |