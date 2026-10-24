"""
TrustOffice Lead Pipeline Monitor
===============================

Anti-silent-failure assertions for the lead funnel:

  capture -> book-invite -> MailerCloud Leads list -> 90-day nurture drip
  (+ booking reminders + post-drip re-engagement)

Asserts (run on a schedule by background_tasks.check_leads_pipeline_health):
  1. Nurture throughput: the number of nurture sends in the last 24h must be
     at least the number of sends that were DUE in that window (demand-based
     floor, derived from the drip schedule), and no due send may be overdue
     past the grace window. On failure, posts a RED alert to
     #trustoffice-main (1479343804527153262).
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

# 2026-10-23 fix: the throughput floor was measured as a flat 10% of the
# eligible cohort. That is NOT what the drip is supposed to do. The drip is
# a scheduled 12-email sequence: a lead gets its next email only when its
# own schedule day arrives (step N fires on day D_N after the step-1 anchor).
# So the number of sends that SHOULD happen in a 24h window is the number of
# cohort leads whose next step falls due in that window - NOT 10% of the
# whole cohort.
#
# Why the old floor was wrong (production evidence, 2026-10-23):
#   - cohort 128 leads -> floor 12 sends/24h
#   - actual demand: 0 sends were due in the trailing 24h window; the
#     largest single run in 14 days sent 42 against a cap of 80
#   - steady-state demand across the cohort is ~17 sends/day, and the
#     drip's day-to-day demand swings from 0 to 55 depending on where the
#     cohort's anchors fall.
# So a flat 10% floor produced a permanent false RED (7 sends vs floor 13)
# on a perfectly healthy drip, and it was ALSO blind to a real stall: a
# genuinely stuck drip (0 sends) was indistinguishable from a quiet day.
#
# The fix measures the thing that actually matters: are the sends that were
# DUE actually going out? The floor is now derived from demand:
#   floor = due_in_window (what the schedule says should have gone out)
# and the assert is "sends >= floor" AND "no due send is overdue".
# A genuinely broken drip (0 sends while N are due) still goes RED, and a
# quiet day (0 due) does not.
THROUGHPUT_FLOOR_RATIO = 0.10  # retained for back-compat; not used as the floor

# Nurture schedule: step -> days after the step-1 anchor.
# Mirrors background_tasks.send_nurture_drip_emails NURTURE_SCHEDULE.
NURTURE_SCHEDULE = {
    2: 3,   # Day 3
    3: 8,   # Day 8
    4: 12,  # Day 12
    5: 18,  # Day 18
    6: 25,  # Day 25
    7: 35,  # Day 35
    8: 42,  # Day 42
    9: 50,  # Day 50
    10: 60, # Day 60
    11: 70, # Day 70
    12: 80, # Day 80
}

# Grace window: a due step is not "late" until the drip has had this long
# to pick it up. The drip runs every 6 hours, so 12h = two full runs.
DUE_GRACE = timedelta(hours=12)

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
        {
            "_id": 0,
            "lead_id": 1,
            "nurture_step_sent": 1,
            "booked_call": 1,
            "nurture_step1_sent_at": 1,
            "nurture_step1_backfill_at": 1,
            "created_at": 1,
        },
    ).to_list(2000)
    eligible = 0
    cohort_anchors = []  # (lead_id, anchor_dt, current_step) for demand math
    for lead in cohort_leads:
        step = lead.get("nurture_step_sent")
        if not isinstance(step, int):
            continue
        if step < NURTURE_MIN_STEP or step > NURTURE_MAX_STEP:
            continue
        if lead.get("booked_call") is True:
            continue
        eligible += 1
        anchor = _as_dt(
            lead.get("nurture_step1_backfill_at")
            or lead.get("nurture_step1_sent_at")
            or lead.get("created_at")
        )
        if anchor is not None:
            cohort_anchors.append((lead.get("lead_id"), anchor, step))

    # ---- Demand: how many cohort leads have their NEXT step due in the
    # trailing 24h window? This is what the drip is actually supposed to
    # send, and it is what the floor is measured against.
    due_in_window = 0
    overdue_due = 0
    for _lead_id, anchor, step in cohort_anchors:
        next_step = step + 1
        if next_step not in NURTURE_SCHEDULE:
            continue
        due_at = anchor + timedelta(days=NURTURE_SCHEDULE[next_step])
        if day_ago <= due_at <= now:
            due_in_window += 1
        elif due_at < now - DUE_GRACE:
            # 2026-10-24: lateness must be measured against when the drip could
            # actually have run, not against raw wall-clock. The drip fires
            # every 6 hours, so a step that became due in the LAST 6h has not
            # been missed by anything yet — flagging it here raced the
            # scheduler (e.g. 27 sends due at 04:26 AM, drip last ran 04:03,
            # next run 10:03 -> 6 spurious "overdue" REDs). A send is only
            # overdue when the previous drip run finished AFTER it came due:
            # that is at least one full drip cycle of real negligence.
            if due_at >= now - timedelta(hours=6):
                due_in_window += 1
                continue
            # Due and still not sent, past the grace window.
            overdue_due += 1

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
    # Only a real stall trips this: a cohort with no due sends in the window
    # is a quiet day, not a broken drip.
    if eligible > 0 and due_in_window > 0 and sends_last_24h < 1:
        failures.append(
            f"Nurture throughput: {eligible} eligible leads, {due_in_window} sends due "
            f"in last 24h, but 0 nurture sends went out"
        )

    # ---- Assert 2: sends >= the number of sends that were DUE ----
    # The floor is demand, not a flat fraction of the cohort. A due send that
    # never went out is the real failure this monitor exists to catch.
    floor = due_in_window
    if eligible > 0 and sends_last_24h < floor:
        failures.append(
            f"Nurture throughput: {sends_last_24h} sends/24h < floor {floor} "
            f"({due_in_window} sends were due in the window, "
            f"{overdue_due} overdue past the {int(DUE_GRACE.total_seconds() // 3600)}h grace)"
        )

    # ---- Assert 3: nothing overdue ----
    if overdue_due > 0:
        failures.append(
            f"Nurture throughput: {overdue_due} due nurture send(s) still not sent "
            f"more than {int(DUE_GRACE.total_seconds() // 3600)}h past their schedule day"
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
            # Call is long past — reminders (if any) already fired; not our concern.
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
            f"within 36h window —" + "; ".join(booking_violations[:5])
            + ("…" if len(booking_violations) > 5 else "")
        )

    all_ok = len(failures) == 0

    if not all_ok:
        detail = {
            "eligible_cohort": eligible,
            "sends_last_24h": sends_last_24h,
            "throughput_floor": floor,
            "sends_due_in_window": due_in_window,
            "sends_overdue": overdue_due,
            "booking_violations": len(booking_violations),
        }
        # A failed assertion that fails to page anyone is worse than no
        # assertion at all: it converts a live RED into a silent one. Log at
        # ERROR, and treat a notifier that did not report success as a
        # monitor failure in its own right.
        logger.error(
            "LEAD PIPELINE HEALTH CHECK FAILED (RED) - "
            f"eligible={eligible}, sends_last_24h={sends_last_24h}, "
            f"floor={floor}, booking_violations={len(booking_violations)}: "
            + "; ".join(failures)
        )
        try:
            notify_result = await notify(
                title="Lead pipeline health check FAILED (RED)",
                message="; ".join(failures),
                details=detail,
                alert_level="red",
            )
            if isinstance(notify_result, dict) and not notify_result.get("success", True):
                logger.error(
                    "PIPELINE RED ALERT WAS NOT DELIVERED: "
                    f"{notify_result.get('error') or notify_result} - "
                    "the failure above is live but unannounced. Check the "
                    "Discord webhook env vars (DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL "
                    "/ DISCORD_ALERTS_WEBHOOK_URL)."
                )
        except Exception as e:
            logger.error(
                f"PIPELINE RED ALERT RAISED AN EXCEPTION AND WAS NOT DELIVERED: {e}",
                exc_info=True,
            )
    else:
        logger.info(
            f"[pipeline-monitor] OK - eligible={eligible}, sends_24h={sends_last_24h}, "
            f"due_in_window={due_in_window}, overdue={overdue_due}, "
            f"booking_violations={len(booking_violations)}"
        )

    return {
        "all_ok": all_ok,
        "eligible_cohort": eligible,
        "sends_last_24h": sends_last_24h,
        "throughput_floor": floor,
        "sends_due_in_window": due_in_window,
        "sends_overdue": overdue_due,
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
