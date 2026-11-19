# Bland Dispatch Controller Ã¢ÂÂ Handoff ÃÂ§10 (Kit-Owned Dispatch Architecture)

Date: 2026-11-19 (dormant, by design)

## 10. Kit-owned dispatch architecture (env knobs, dormant state, activation)

The Kit owns orchestration for Bland AI calls. **NO dependence on Bland-side
polling/worker.** The dispatcher is OUR code: it decides who gets called, when,
at what rate. Bland executes the conversation and reports the outcome via the
call-completed webhook.

## Component map (this build)

- `backend/routers/bland_dispatcher.py` Ã¢ÂÂ the dispatch controller:
  - Scheduler: FastAPI startup-launched asyncio background loop, env-gated.
  - FRESH poll every `BLAND_FRESH_POLL_MINUTES` (default 5) Ã¢ÂÂ GET `tier=fresh` from
    the local queue logic directly (`get_calling_queue` in `routers/leads_service`,
    called as a function Ã¢ÂÂ no HTTP self-call).
  - AGED poll once per calendar day after `BLAND_AGED_DISPATCH_HOUR_MT` (default
    09:00, America/Denver, via `zoneinfo.America/Denver`).
  - Per lead: claim via existing claim logic (`claim_lead_for_call` /
    `ClaimRequest`, direct call Ã¢ÂÂ no endpoint HTTP), then POST
    `https://api.bland.ai/v1/calls` (Bland Send Call docs:
    `https://docs.bland.ai/api-v1/post/calls-agent`):
    - `agent_id` = `BLAND_AGENT_ID` (default `fe709e36-fc79-4eab-a199-d984fbe36e52`)
    - `phone_number` = lead phone (already normalized E.164)
    - `request_data` = `{lead_id, name, email, timezone: "America/Denver"}`
    - `metadata` = `{lead_id, tier}`
    - `external_id` = lead_id (idempotency echo)
    - `webhook` = `https://api.trustoffice.app/api/service/bland/webhook?secret=<BLAND_WEBHOOK_SECRET>`
  - Guardrails: call window `BLAND_CALL_WINDOW_MT` (default `09:00-19:30`
    America/Denver Ã¢ÂÂ outside window: defer, no error); fresh batch max
    `BLAND_FRESH_BATCH_MAX` (default 2 per poll cycle, no burst); kill switches.
  - Audit: every dispatch decision writes to collection `bland_call_log`
    `{lead_id, tier, claim_id, ts, ok, error_code, http}`; Bland 4xx Ã¢ÂÂ log +
    skip that lead this cycle, never crash the loop.

## Env knobs table

| Var | Default | Meaning | Enable |
| --- | --- | --- | --- |
| `BLAND_DISPATCH_ENABLED` | unset (false) | Master switch. Unset/false Ã¢ÂÂ fully idle (one startup log line). | yes |
| `BLAND_API_KEY` | unset in Railway | Bearer key for `api.bland.ai` Send Call. Absent Ã¢ÂÂ dispatcher stays idle even if enabled (log once at startup). | yes |
| `BLAND_AGENT_ID` | `fe709e36-fc79-4eab-a199-d984fbe36e52` | Bland agent to dial. | Ã¢ÂÂ |
| `BLAND_WEBHOOK_SECRET` | env | Secret for webhook auth (header `X-Webhook-Secret` OR `?secret=` query param; constant-time compare). | Ã¢ÂÂ |
| `BLAND_FRESH_POLL_MINUTES` | `5` | Fresh-tier poll cadence. | Ã¢ÂÂ |
| `BLAND_FRESH_BATCH_MAX` | `2` | Fresh calls max per poll cycle. | Ã¢ÂÂ |
| `BLAND_FRESH_ENABLED` | `false` | Fresh tier enabled. Off until go-live. | yes |
| `BLAND_AGED_ENABLED` | `false` | Aged tier enabled. **Default OFF Ã¢ÂÂ aged calls stay OFF until Jeff flips.** | yes |
| `BLAND_AGED_DISPATCH_HOUR_MT` | `9` | Hour (America/Denver local) after which the once-per-day aged poll may run. | Ã¢ÂÂ |
| `BLAND_CALL_WINDOW_MT` | `09:00-19:30` | Call window (America/Denver). Outside Ã¢ÂÂ defer, no error. | Ã¢ÂÂ |

## Dormant state (shipped)

- `BLAND_API_KEY` is **NOT** set in Railway yet. The dispatcher ships dormant by
  design; activation = setting `BLAND_API_KEY` in Railway + flipping
  `BLAND_FRESH_ENABLED` / `BLAND_AGED_ENABLED` (as desired). **No new env vars
  were set beyond the code defaults** in this deploy.
- Dispatcher idle (BLAND_DISPATCH_ENABLED unset) Ã¢ÂÂ no calls placed, no CRM writes.

## Activation sequence

1. Provision `BLAND_API_KEY` in Railway.
2. Flip `BLAND_FRESH_ENABLED=true` (go-live) and/or `BLAND_AGED_ENABLED=true`.
3. Watch `bland_call_log` audit trail.

## Bland is callee only

Worker/polling instructions to Bland are **REMOVED** from this architecture.
Bland executes the conversation and reports via the webhook; the dispatcher owns
scheduling, claiming, rate-limiting, windows.

## Interplay with the concurrent tier lane

The dispatcher probes the queue function's signature for tier support; once the
concurrent tier lane (`deleg_2f77f2ab` Ã¢ÂÂ tier params + `bland_aged_budget` daily
cap ledger) lands, the dispatcher opts into `tier=fresh` / `tier=aged` selection
via that lane's queue logic (aged inherits the server-side daily cap from
`bland_aged_budget`). This build adds **no** duplicate tier logic or cap ledger.
Before that lane merges, the aged poll logs and skips (aged dispatches stay at
zero).
