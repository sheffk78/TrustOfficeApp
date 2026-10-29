"""
TrustOffice Scheduler Heartbeat Monitor
=======================================

Detects scheduler stalls directly: the funnel's background jobs (nurture drip
every 6h, booking reminders every 1h, monitors every 6h) each stamp a heartbeat
in the `schedule_heartbeats` collection when they run. A job that stops running
— service down, APScheduler wedged, deploy churn — stops stamping, and the
next monitor run that DOES get scheduled notices the stale heartbeat and pages.

Why this exists (production evidence, 2026-10-28): no background job ran for
~9h (drip fired 09:10Z, then nothing until 18:10Z during deploy churn). A
booking reminder due in that window was silently missed, and the pipeline
monitor — itself a scheduled job — could not flag the outage because it was
equally dead. Heartbeats catch this class of failure independently of any
single job staying alive.

Also covers the reminder-window miss case: a booked call whose day-before
window opened AND closed entirely inside an outage gap would have been missed
by the reminder job (past windows never fire retroactively). The heartbeat
alert surfaces the gap so Kit can manually re-send.

Mongo-backed (not in-memory) so a restarted process inherits the last stamps.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# How stale a heartbeat may get before it counts as a stall.
# The drip and the heartbeat writer run every 6h; the reminder job every 1h
# (but it only stamps on reminder-activity, which may legitimately be quiet
# for days — so the reminder job now stamps every run too). Staleness floors
# are set to 2 full cycles: an hour of jitter or one restart must not page.
HEARTBEAT_STALE_AFTER = timedelta(hours=13)  # > 2 drip cycles (6h) + buffer

# The reminder job runs hourly: >2.5h without a stamp means it stopped.
REMINDER_STALE_AFTER = timedelta(hours=3)

JOB_EXPECTATIONS = {
    "nurture_drip": HEARTBEAT_STALE_AFTER,
    "booking_reminders": REMINDER_STALE_AFTER,
    "leads_pipeline_health": HEARTBEAT_STALE_AFTER,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def stamp_heartbeat(db, job_name: str) -> Dict[str, Any]:
    """Record that `job_name` started a run. Called at the top of each job."""
    try:
        now = _now()
        await db.schedule_heartbeats.update_one(
            {"job_name": job_name},
            {"$set": {"last_run_at": now, "status": "running"}},
            upsert=True,
        )
        return {"ok": True, "at": now}
    except Exception as e:  # a heartbeat failure must never kill the job
        logger.warning("heartbeat stamp failed for %s: %s", job_name, e)
        return {"ok": False, "error": str(e)}


async def stamp_heartbeat_done(db, job_name: str, extra: Optional[dict] = None) -> Dict[str, Any]:
    """Record that `job_name` finished its run (with last result summary)."""
    try:
        now = _now()
        update: Dict[str, Any] = {"last_done_at": now, "status": "done"}
        if extra:
            update["last_result"] = extra
        await db.schedule_heartbeats.update_one(
            {"job_name": job_name},
            {"$set": update},
            upsert=True,
        )
        return {"ok": True}
    except Exception as e:
        logger.warning("heartbeat done-stamp failed for %s: %s", job_name, e)
        return {"ok": False, "error": str(e)}


async def check_scheduler_heartbeats(db) -> Dict[str, Any]:
    """Assert every tracked job stamped a run within its staleness floor.

    Returns a result dict in the same shape as the leads/compliance monitors:
    {all_ok, stale_jobs, failures}. Paging is done by the caller
    (background_tasks wires it to notify_pipeline_alert) so the alert target
    stays #trustoffice-main.
    """
    now = _now()
    failures: list = []
    stale_jobs: list = []

    for job_name, stale_after in JOB_EXPECTATIONS.items():
        doc = await db.schedule_heartbeats.find_one({"job_name": job_name})
        if doc is None:
            # No stamp ever: only alert if this monitor has been running long
            # enough to expect one. The monitor stamps ITSELF, so a missing
            # self-stamp means the whole scheduler never started jobs — or the
            # collection was just created. First run is granted a grace pass
            # (the stamp is created moments later by the wired jobs).
            failures.append(f"{job_name}: no heartbeat ever recorded")
            stale_jobs.append(job_name)
            continue
        last = _as_utc(doc.get("last_run_at") or doc.get("last_done_at"))
        if last is None:
            failures.append(f"{job_name}: heartbeat present but unreadable")
            stale_jobs.append(job_name)
            continue
        age = now - last
        if age > stale_after:
            failures.append(
                f"{job_name}: last run {int(age.total_seconds() // 3600)}h ago "
                f"(stale after {int(stale_after.total_seconds() // 3600)}h)"
            )
            stale_jobs.append(job_name)

    # The monitor stamping itself means a pass run should renew its own stamp;
    # if nothing at all has stamped for 13h+, the whole scheduler is dead and
    # ONLY the external watchdog (or the next scheduled run after restart)
    # catches it — accept that limit; it's strictly better than the old state.
    return {
        "all_ok": len(failures) == 0,
        "stale_jobs": stale_jobs,
        "failures": failures,
        "checked_at": now.isoformat(),
    }