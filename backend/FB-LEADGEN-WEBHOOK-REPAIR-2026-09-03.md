# TrustOffice FB Leadgen Webhook — Diagnosis & Repair (2026-09-03)

## Root cause
The page's app subscription for leadgen events was gone: GET /1000708909801900/subscribed_apps
returned an empty `data` array. The app-level webhook subscription
(GET /928944609755747/subscriptions with app access token) was still healthy:
`object=page, callback_url=https://api.trustoffice.app/api/admin/leads/facebook-webhook,
active=true, fields=[leadgen@v25.0]`. So Meta was configured to send page-leadgen events,
but the page itself was no longer subscribed to the app → Meta dropped all leadgen events
for the page after Aug 9. Cause of the drop: not determinable from the API (no timestamp
exposed); possible triggers include a token/permission refresh, BM access change, or manual
removal in Page settings.

## Repair
POST /v25.0/1000708909801900/subscribed_apps with `subscribed_fields=leadgen` using the
existing page access token (FB_PAGE_ACCESS_TOKEN from Railway backend-v2) → `{"success": true}`.
Post-repair GET /subscribed_apps now returns:
`[{id: 928944609755747, name: AgenticTrust, subscribed_fields: [leadgen]}]`.

No permission gap blocked the repair: the page token DOES hold `pages_manage_metadata`
+ `leads_retrieval` (debug_token confirmed), which is sufficient for subscribed_apps writes.
It lacks `pages_manage_ads` (needed for /leadgen_forms listing) and `ads_read` (needed for
ad-account insights).

## Webhook endpoint verification (https://api.trustoffice.app)
Route found in code: `GET/POST /api/admin/leads/facebook-webhook`
(routers/leads.py, mounted via server.py with /api prefix; verify-token + X-Hub-Signature-256
HMAC checks present).
- GET verify handshake: hub.mode=subscribe + correct verify token → echoed hub.challenge (200). ✓
- GET with wrong token → 403. ✓
- POST signed test payload (valid HMAC sig) → 200 `{"success":true,"processed":1,...}`. ✓
- POST unsigned → 403. ✓
Endpoint is live and correctly wired. (First attempts got Cloudflare 1010 blocks; retried
with browser-like User-Agent and they passed — Meta's own crawler will not be blocked the
same way, and the app subscription + endpoint handshake both confirmed working.)

## Ads activity Aug 21–Sep 3
NOT VERIFIABLE with current tokens: page token has no `ads_read`; user token in
~/.hermes/.env (FACEBOOK_ACCESS_TOKEN) also lacks `ads_read`/`ads_management`. The
trustoffice.app BM (id 1289032089941524) is visible via /me/businesses but
/{BM}/owned_ad_accounts returns 403 "Ad account owner has NOT grant ads_management or
ads_read permission". client_ad_accounts returns empty. No ad account id is documented in
secrets or brand files.

## What Jeff must grant (in Business Manager)
1. Add `ads_read` (and optionally `pages_manage_ads`) to the AgenticTrust app's
   permissions and re-authorize — needed for /leadgen_forms listing and ad insights.
2. In Business Manager (trustoffice.app, id 1289032089941524): grant the app/system user
   `Ads Management` access to the ad account, or share the ad account ID so we can query
   it directly.
3. Ad account lead counts by day for Aug 10–Sep 3 remain UNKNOWN until this is granted.

## Monitoring recommendation
Set a daily script-only monitor: GET /1000708909801900/subscribed_apps must return the app
id 928944609755747 with subscribed_fields containing leadgen. Empty array = page down again.
(Per Cron Alternative Framework: webcheck script, not an LLM cron.)