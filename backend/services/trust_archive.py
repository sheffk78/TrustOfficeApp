"""Trust archive service — Records Repository v1 (F1, 2026-09-12).

Status model + backfill + one-time wiring of the dependency-level guard.

- Trust.status: "active" | "dissolved_archived" (default active)
- Trust.dissolved_on: optional ISO date string, set by POST /trusts/{id}/dissolve
- Backfill is EXPLICIT (update_many stamping status="active" on legacy docs);
  no collection-scan defaults at read time.
- apply_archive_guard() wires the 409 trust_dissolved guard onto every
  already-declared mutating trust-scoped route across all routers, by path
  shape — one enforcement point, no per-route conditionals.

Run from server.py startup_event():
    from services.trust_archive import backfill_trust_status, apply_archive_guard
    await backfill_trust_status()
    apply_archive_guard(app)
"""
import logging

logger = logging.getLogger(__name__)

TRUST_STATUS_ACTIVE = "active"
TRUST_STATUS_DISSOLVED = "dissolved_archived"

# FastAPI route path-param verbs that mutate trust-scoped state. Paths are
# declared WITHOUT the /api prefix (routers are mounted with prefix="/api").
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def backfill_trust_status() -> int:
    """Explicit backfill: stamp status="active" on every trust missing the field.

    Idempotent. Returns the number of documents updated this run. Deliberately
    an update_many (one collection pass) — NOT a per-read default.
    """
    from database import db

    result = await db.trusts.update_many(
        {"status": {"$exists": False}},
        {"$set": {
            "status": TRUST_STATUS_ACTIVE,
            # dissolved_on stays absent for active trusts (optional field).
        }},
    )
    if result.modified_count:
        logger.info(
            "trust_archive backfill: stamped status=active on %d legacy trust(s)",
            result.modified_count,
        )
    return result.modified_count


def apply_archive_guard(app) -> int:
    """Wire guard_trust_archive onto every mutating trust-scoped route.

    A route is trust-scoped when its path contains "/trusts/{...}" (path-param
    form) or "/trusts" (collection form, e.g. POST /api/trusts — creation is
    unaffected by dissolve). The guard dependency resolves the shared
    {trust_id} path param via FastAPI's dependency cache and raises
    409 trust_dissolved when the trust is dissolved_archived.

    Exemptions (called BY the dissolve flow, must stay reachable):
      - POST /api/trusts (creation)
      - POST /api/trusts/{trust_id}/dissolve
      - POST /api/trusts/{trust_id}/un-dissolve (admin-only reversal)
    Returns the number of routes wired (for the startup log / tests).
    """
    from dependencies import guard_trust_archive

    _EXEMPT_SUFFIXES = ("/dissolve", "/un-dissolve")
    from fastapi import Depends

    wired = 0
    for route in app.router.routes:
        path = getattr(route, "path", "") or ""
        methods = {m.upper() for m in (getattr(route, "methods", None) or set())}
        if not (methods & _MUTATING_METHODS):
            continue
        if "/trusts" not in path:
            continue
        if path == "/api/trusts":  # trust creation
            continue
        if any(path.endswith(suffix) for suffix in _EXEMPT_SUFFIXES):
            continue
        if "{trust_id}" not in path:
            continue  # non-trust-scoped path under /trusts (none known today)
        # Dependency cache makes {trust_id} resolve to the path param on every
        # route that has it — including body-trust_id routes that ALSO carry
        # {trust_id} in the path. Routes scoped purely by body set
        # X-Trust-Scoped: body (header) and use the body-reading guard.
        scope = (getattr(route, "dependant", None) is not None and
                 "trust_id" not in path)
        if scope:
            continue  # pragma: no cover — defensive; all current paths carry {trust_id}
        # Appending to route.dependencies AFTER the APIRoute was constructed has
        # no effect — FastAPI already compiled route.dependant. Insert the
        # compiled parameter-less sub-dependant at the FRONT of the route's
        # dependant so the guard runs before the endpoint's own dependencies
        # (FastAPI evaluates route.dependant.dependencies in order).
        from fastapi.dependencies.utils import get_parameterless_sub_dependant
        guard_sub = get_parameterless_sub_dependant(
            depends=Depends(guard_trust_archive), path=path,
        )
        route.dependant.dependencies.insert(0, guard_sub)
        wired += 1
    if wired:
        logger.info("trust_archive guard: wired 409 guard onto %d mutating route(s)", wired)
    return wired


def body_scoped_mutating_route(path: str) -> bool:
    """True when a mutating route scopes the trust from the body (no path param).

    Used by the guard application test to document which route shapes need
    guard_trust_archive_body. Current codebase: every trust-scoped mutating
    route carries {trust_id} in the path, so the body form is a defensive
    affordance for future routes (wired manually via Depends).
    """
    return "{trust_id}" not in path and path.startswith("/api/")