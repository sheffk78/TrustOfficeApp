# error-relay worker (Cloudflare Worker)

Serves `/capture.js` (browser error capture snippet) and forwards browser error
reports from `/report` to the configured Discord webhook.

## Deployed at
- https://error-relay.jeff-43f.workers.dev (workers.dev trigger)

## Embedded by (classic `<script src>` with `data-brand`)
- app.trustoffice.app (all app pages, incl. /dashboard)
- truejoybirthing.com
- wingpointtrust.com

## 2026-09-18 fix (err_201b0c3bde48)
`serveCaptureJs()` served an ES-module snippet containing `export function
initErrorCapture(...)` — but every embedding page loads it as a CLASSIC script,
so browsers threw `SyntaxError: Unexpected token 'export'` on page load
(logged as uncaught_exception at /dashboard, severity major, first seen
2026-09-18T10:55:54Z; same failure would fire on TJB + WingPoint pages).

Fix: removed the `export` keyword from the served snippet; capture behavior is
unchanged (the snippet already self-inits from `document.currentScript`).
Also dropped Cache-Control max-age 3600 → 300 so fixes propagate quickly.

Deployed via `wrangler deploy` (version a6ff671b-571b-40b1-a02d-6c9de1e43971)
with the existing `DISCORD_WEBHOOK_URL` secret binding preserved. Verified:
live capture.js contains no `export` token, parses as a classic script, and a
test report POST returned `{"ok":true}`.

This file is the source of record for the deployed worker.