# services/org_activity.py — org activity feed + D10 attribution helpers
# Shared by org-grant-mediated write paths (items 2 + 5 of ORG-SKELETON-SPEC).
# Additive-only: activity goes to the NEW org_activity collection and
# attribution is an additive field on records. Actors without org_grant
# (owners, legacy flag-off, party actors) hit no-op paths, so with
# TOGGLE_INSTITUTION off nothing is written.
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from database import db

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def trustee_display_name(trust: dict) -> str:
    """Trustee display name from the ACTUAL fields present in `trusts`.

    Live-schema check (dogfood 2026-09-28): trust docs carry trustee_full_name
    (populated, e.g. 'Benjamin Thomas Barlow') while trustee_names is usually
    empty and trustees holds the raw composite string. Resolution order:
    trustee_full_name -> first parsed trustees entry -> trustee_names ->
    grantor_name -> ''.
    """
    name = (trust.get("trustee_full_name") or "").strip()
    if name:
        return name
    raw = trust.get("trustees")
    if isinstance(raw, (list, tuple)):
        raw = ", ".join(str(x) for x in raw if x)
    if raw and str(raw).strip():
        try:
            from trustee_utils import parse_trustees

            parsed = parse_trustees(str(raw))
            if parsed:
                first = parsed[0]
                if isinstance(first, dict):
                    first = first.get("name") or ""
                if str(first).strip():
                    return str(first).strip()
        except Exception:
            pass
    name = (trust.get("trustee_names") or "").strip()
    if name:
        return name
    return (trust.get("grantor_name") or "").strip()


async def org_display_name(org_id: str) -> str:
    """Org name from orgs (TrustGrant docs carry no org_name)."""
    if not org_id:
        return ""
    try:
        org = await db.orgs.find_one({"org_id": org_id}, {"_id": 0, "name": 1})
    except Exception:
        return ""
    return (org or {}).get("name", "") or ""


async def build_org_attribution(trust_id: Optional[str], actor: Optional[dict]) -> Tuple[Optional[str], str]:
    """D10 attribution line for an org-grant-mediated write, mirroring the
    minutes.py pattern: 'Prepared by {member_name}, {org_name} — on behalf of
    {trustee_name}'. The 'on behalf of' tail is omitted when no trustee name
    can be resolved (falls back through grantor_name).

    Returns (attribution | None, org_id). None when the actor carries no
    org_grant (owner short-circuit, legacy flag off, party actor) — callers
    then skip record stamping and activity logging entirely.
    """
    actor = actor or {}
    grant = actor.get("org_grant")
    if not grant:
        return None, ""
    org_id = grant.get("org_id") or ""
    org_name = await org_display_name(org_id)
    member_name = ((actor.get("name") or actor.get("email") or "").strip())
    trustee_name = ""
    if trust_id:
        try:
            trust = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0})
        except Exception:
            trust = None
        trustee_name = trustee_display_name(trust or {})
    prepared = f"Prepared by {member_name}, {org_name}".replace(", ", ", ").strip()
    if trustee_name:
        return f"Prepared by {member_name}, {org_name} — on behalf of {trustee_name}", org_id
    return prepared, org_id


async def log_org_activity(
    trust_id: str,
    actor: Optional[dict],
    action: str,
    attribution: Optional[str] = None,
    org_id: Optional[str] = None,
) -> None:
    """Record one org-grant-mediated write in the org_activity feed (item 5).

    Best-effort: never raises, never blocks the surrounding write. No-op when
    the actor has no org_grant (also covers flag-off behavior).
    """
    actor = actor or {}
    grant = actor.get("org_grant")
    if not grant:
        return
    resolved_org_id = org_id or grant.get("org_id") or ""
    try:
        await db.org_activity.insert_one({
            "event_id": f"act_{uuid.uuid4().hex[:12]}",
            "org_id": resolved_org_id,
            "trust_id": trust_id or "",
            "member_name": (actor.get("name") or actor.get("email") or "").strip(),
            "org_name": await org_display_name(resolved_org_id),
            "action": action,
            "attribution": attribution,
            "created_at": _now(),
        })
    except Exception as e:  # feed must never break the parent write
        logger.warning(f"org_activity log failed for action={action}: {e}")