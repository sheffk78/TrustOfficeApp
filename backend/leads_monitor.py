"""
TrustOffice Lead Pipeline Monitor
===============================

Anti-silent-failure assertions for the lead funnel:

  capture -> book-invite -> MailerCloud Leads list -> 90-day nurture drip
  (+ booking reminders + post-drip re-engagement)

Asserts (run on a schedule by background_tasks.check_leads_pipeline_health):
  1. Nurture throughput: when eligible leads exist, >=1 nurture send in the
     last 24h AND sends_last_24h >= 10% of the eligible cohort. On failure,
     posts a RED alert to #trustoffice-main (1479343804527153262).
  2. Booking reminders: any booked call landing within 36h whose reminder
     window has already opened MUST have reminder activity logged
     (day-before and/or 1-hour). Missed reminders => RED alert.

`created_at` in lead_activities may be a STRING during the type migration
(item 5) or a BSON Date after it. `_as_dt` normalizes both so time-range
checks work across the transition.

This module is import-safe and unit-testable: pass a mongomock `db` and an
optional `notify` callable (defaults to discord_service.notify_pipeline_alert)
to capture alerts without hitting Discord.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)

# Cohort = leads actually in the nurture drip (1..11 steps sent, not yet
# converted/post_drip, and not a booked-call lead the call flow owns).
ELIGIBLE_STAGES = ["new", "engaged", "warm"]
NURTURE_MIN_STEP = 1
NURTURE_MAX_STEP = 11  # sequence has 12 emails (steps 1..12); step>=12 -> post_drip
THROUGHPUT_FLOOR_RATIO = 0.10  # sends_last_24h must be >= 10% of eligible cohort

# Booking-reminder windows (mirror background_tasks.send_booking_reminder_emails)
DAY_BEFORE_LOWER = timedelta(hours=23)
DAY_BEFORE_UPPER = timedelta(hours=25)
ONE_HOUR_LOWER = timedelta(minutes=55)
ONE_HOUR_UPPER = timedelta(minutes=65)
BOOKING_LOOKAHEAD = timedelta(hours=36)


def _as_dt(value) -> Optional[datetime]:
    """Normalize a stored created_at (BSON Date OR ISO string) to a tz-aware UTC datetime.

    Returns None when the value cannot be parsed (caller treats unparseable as
    'outside the window' rather than crashing the monitor).
    """
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


def _is_nurture_send(content: str) -> bool:
    c = (content or "").lower()
    return "nurture" in c or "mailercloud" in c or "drip" in c


async def check_leads_pipeline_health(
    db,
    notify: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Run the pipeline-health assertions. Returns a result dict.

    `notify` is an async callable(title, message, details) used to raise RED
    alerts; defaults to discord_service.notify_pipeline_alert. Pass a stub in
    tests to capture alerts without touching Discord.
    """
    if notify is None:
        from discord_service import notify_pipeline_alert as notify  # late import

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    failures: list = []

    # ---- Eligible cohort (Python-side filter for prod/transition robustness) ----
    cohort_leads = await db.leads.find(
        {"stage": {"$in": ELIGIBLE_STAGES}},
        {"_id": 0, "lead_id": 1, "nurture_step_sent": 1, "booked_call": 1},
    ).to_list(2000)
    eligible = 0
    for lead in cohort_leads:
        step = lead.get("nurture_step_sent")
        if not isinstance(step, int):
            continue
        if step < NURTURE_MIN_STEP or step > NURTURE_MAX_STEP:
            continue
        if lead.get("booked_call") is True:
            continue
        eligible += 1

    # ---- Nurture sends in the last 24h ----
    sends_last_24h = 0
    async for act in db.lead_activities.find(
        {"action_type": "email"}, {"_id": 0, "created_at": 1, "content": 1}
    ):
        dt = _as_dt(act.get("created_at"))
        if dt is None or dt < day_ago:
            continue
        if _is_nurture_send(act.get("content", "")):
            sends_last_24h += 1

    # ---- Assert 1: at least one nurture send when leads exist ----
    if eligible > 0 and sends_last_24h < 1:
        failures.append(
            f"Nurture throughput: {eligible} eligible leads but 0 nurture sends in last 24h"
        )

    # ---- Assert 2: sends >= 10% of eligible cohort ----
    floor = int(THROUGHPUT_FLOOR_RATIO * eligible)
    if eligible > 0 and sends_last_24h < floor:
        failures.append(
            f"Nurture throughput: {sends_last_24h} sends/24h < floor {floor} "
            f"(10% of {eligible} eligible leads)"
        )

    # ---- Booking-reminder assert ----
    booking_violations: list = []
    booked_leads = await db.leads.find(
        {"booked_call": True},
        {
            "_id": 0,
            "lead_id": 1,
            "email": 1,
            "name": 1,
            "booked_call_at": 1,
            "reminder_day_before_sent_at": 1,
            "reminder_1h_sent_at": 1,
        },
    ).to_list(2000)
    for lead in booked_leads:
        bca = _as_dt(lead.get("booked_call_at"))
        if bca is None:
            continue
        # Only calls within the next 36h (future or just-past) are in scope.
        if bca > now + BOOKING_LOOKAHEAD:
            continue
        if bca < now - ONE_HOUR_UPPER:
            # Call is long past â reminders (if any) already fired; not our concern.
            continue

        day_before_logged = bool(lead.get("reminder_day_before_sent_at")) or await _has_reminder_activity(
            db, lead.get("lead_id"), "booking_reminder_day_before"
        )
        one_h_logged = bool(lead.get("reminder_1h_sent_at")) or await _has_reminder_activity(
            db, lead.get("lead_id"), "booking_reminder_1h"
        )

        # Day-before window has opened (call is within 23h) -> day-before must be logged.
        if bca <= now + DAY_BEFORE_LOWER and not day_before_logged:
            booking_violations.append(
                f"{lead.get('email')}: day-before reminder missing for call at {bca.isoformat()}"
            )
        # 1-hour window has opened (call is within 55min) -> 1h must be logged.
        if bca <= now + ONE_HOUR_LOWER and not one_h_logged:
            booking_violations.append(
                f"{lead.get('email')}: 1-hour reminder missing for call at {bca.isoformat()}"
            )

    if booking_violations:
        failures.append(
            f"Booking reminders: {len(booking_violations)} call(s) missing reminder activity "
            f"within 36h window â " + "; ".join(booking_violations[:5])
            + (" â¦" if len(booking_violations) > 5 else "")
        )

    all_ok = len(failures) == 0

    if not all_ok:
        detail = {
            "eligible_cohort": eligible,
            "sends_last_24h": sends_last_24h,
            "throughput_floor": floor,
            "booking_violations": len(booking_violations),
        }
        try:
            await notify(
                title="Lead pipeline health check FAILED (RED)",
                message="; ".join(failures),
                details=detail,
                alert_level="red",
            )
        except Exception as e:
            logger.error(f"Pipeline monitor: failed to send RED alert: {e}")
    else:
        logger.info(
            f"[pipeline-monitor] OK â eligible={eligible}, sends_24h={sends_last_24h}, "
            f"booking_violations={len(booking_violations)}"
        )

    return {
        "all_ok": all_ok,
        "eligible_cohort": eligible,
        "sends_last_24h": sends_last_24h,
        "throughput_floor": floor,
        "booking_violations": len(booking_violations),
        "failures": failures,
    }


async def _has_reminder_activity(db, lead_id: str, action_type: str) -> bool:
    if not lead_id:
        return False
    doc = await db.lead_activities.find_one(
        {"lead_id": lead_id, "action_type": action_type}, {"_id": 1}
    )
    return doc is not None
