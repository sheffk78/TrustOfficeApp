""""
Daily guard for the TrustOffice Facebook Leadgen page subscription.

WHY THIS EXISTS (root-cause fix):
On 2026-09-03 the page's app subscription for leadgen events was found
GONE (GET /{page}/subscribed_apps returned an empty data array). Meta had
silently dropped all page-leadgen events after ~Aug 9. The repair re-POSTed
subscribed_fields=leadgen, but NO recurring guard was ever put in place, so a
repeat drop would go undetected again (exactly what happened: an Aug 20 -> Sep 4
2026 gap of 14.8 days with zero Facebook leads before the repair re-established flow).

WHAT IT DOES:
GET https://graph.facebook.com/v25.0/{FB_PAGE_ID}/subscribed_apps
Assert the AgenticTrust app id (FB_APP_ID) is present with subscribed_fields
containing 'leadgen'. If the array is empty OR the app/field is missing -> the
page subscription has dropped again -> POST a RED alert to DISCORD_LEADS_WEBHOOK_URL.

CONTRACT (per AGENTS.md Cron Alternative Framework):
- Script-only infra monitor (no_agent=True). Silent on success (empty stdout).
- Posts to ops/leads channel ONLY on failure.
- Designed to run daily (or every 30m) via a script-only cron, NOT an LLM cron.

Run inside the Railway backend container where env vars are present, OR locally
with a .env that exports FB_PAGE_ACCESS_TOKEN / FB_APP_ID / DISCORD_LEADS_WEBHOOK_URL.
"""
import os
import sys
from pathlib import Path

import httpx

# Accept a local .env for ad-hoc runs (Railway provides these as real env vars).
_ENV_FILE = Path.home() / ".hermes" / ".env"
if _ENV_FILE.exists():
    try:
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

FB_PAGE_ID = os.environ.get("FB_PAGE_ID") or "1000708909801900"  # TrustOffice page
FB_APP_ID = os.environ.get("FB_APP_ID", "928944609755747")        # AgenticTrust app
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
DISCORD_LEADS_WEBHOOK_URL = os.environ.get("DISCORD_LEADS_WEBHOOK_URL", "")

GRAPH = "https://graph.facebook.com/v25.0"


def _alert(message: str) -> None:
    """Post a RED alert to the Discord leads webhook. No-op if URL missing."""
    if not DISCORD_LEADS_WEBHOOK_URL:
        print(f"[ALERT-NO-WEBHOOK] {message}")
        return
    try:
        httpx.post(
            DISCORD_LEADS_WEBHOOK_URL,
            json={"content": f"**[RED] FB Leadgen subscription DOWN** (TrustOffice)\n{message}"},
            timeout=10.0,
        )
    except Exception as e:  # never crash the monitor on alert delivery failure
        print(f"[ALERT-POST-FAILED] {e}: {message}")


def check_subscription() -> bool:
    """Return True when the page is correctly subscribed; False otherwise."""
    if not FB_PAGE_ACCESS_TOKEN:
        _alert("FB_PAGE_ACCESS_TOKEN is not set in the backend environment.")
        return False

    try:
        resp = httpx.get(
            f"{GRAPH}/{FB_PAGE_ID}/subscribed_apps",
            params={"access_token": FB_PAGE_ACCESS_TOKEN},
            timeout=15.0,
        )
        payload = resp.json()
    except Exception as e:
        _alert(f"Failed to query /subscribed_apps: {e}")
        return False

    if "error" in payload:
        # Auth failure, expired token, etc. — report the real error, not a
        # misleading "empty array" (empty data means the subscription dropped).
        err = payload["error"]
        _alert(
            f"Graph API error from /subscribed_apps: {err.get('message', payload)} "
            f"(code={err.get('code')}, type={err.get('type')}). "
            "Check FB_PAGE_ACCESS_TOKEN validity/expiry."
        )
        return False

    data = payload.get("data", [])

    if not data:
        _alert(
            "GET /{page}/subscribed_apps returned an EMPTY data array. "
            "Meta is dropping all page-leadgen events. Re-POST "
            "subscribed_fields=leadgen with FB_PAGE_ACCESS_TOKEN to repair."
        )
        return False

    for entry in data:
        if str(entry.get("id")) == str(FB_APP_ID):
            fields = entry.get("subscribed_fields") or []
            if "leadgen" in fields:
                return True
            _alert(
                f"App {FB_APP_ID} is subscribed but leadgen field is MISSING "
                f"(fields={fields}). Re-POST subscribed_fields=leadgen."
            )
            return False

    _alert(
        f"App {FB_APP_ID} NOT found in subscribed_apps (entries={data}). "
        "Page subscription to the leadgen app has dropped."
    )
    return False


def main() -> int:
    ok = check_subscription()
    if ok:
        # Silent on success (empty stdout = no delivery per Cron Alternative Framework).
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
