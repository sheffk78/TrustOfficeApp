"""
TrustOffice State Compliance Reminder Monitor
=============================================

Anti-silent-failure assertion for the state-compliance deadline reminder job
(item 4 of the State Compliance Phase A work):

  send_compliance_deadline_reminders (background_tasks) scans
  trust_state_compliance for upcoming/overdue beneficiary-notice and annual-
  accounting deadlines and emails the trustee. If email is configured yet a
  trust has a compliance deadline within the next 14 days (or already overdue)
  AND zero compliance reminders have been sent in the last 24h, the monitor
  posts a RED alert to #trustoffice-main so a silent scanner failure surfaces.

This module is import-safe and unit-testable: pass a mongomock `db` and an
optional `notify` callable (defaults to discord_service.notify_pipeline_alert)
and an optional `email_configured` flag (defaults to email_service.is_configured)
so tests inject a spy + a boolean without touching Discord or the real email
service.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)

# A compliance due date within the next 14 days (or already overdue) is "in
# scope" for the stall check.
STALL_LOOKAHEAD_DAYS = 14
SEND_WINDOW_HOURS = 24
REMINDER_SENT_ACTION = "compliance_reminder_sent"


def _as_dt(value) -> Optional[datetime]:
    """Normalize a stored timestamp (BSON Date OR ISO string) to tz-aware UTC."""
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


async def check_compliance_reminder_health(
    db,
    notify: Optional[Callable] = None,
    email_configured: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run the compliance-reminder health assertion. Returns a result dict.

    `notify` is an async callable(title, message, details, alert_level) used to
    raise RED alerts; defaults to discord_service.notify_pipeline_alert. Pass a
    stub in tests to capture alerts without touching Discord.

    `email_configured` lets tests force the email-configured branch without
    configuring the real email service; defaults to email_service.is_configured.
    """
    if notify is None:
        from discord_service import notify_pipeline_alert as notify  # late import
    if email_configured is None:
        from email_service import email_service
        email_configured = bool(email_service.is_configured)

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=SEND_WINDOW_HOURS)

    failures: list = []

    # If email is not configured there is nothing to alert about â a "stall" is
    # expected, not a defect. (The scanner itself also no-ops when unconfigured.)
    if not email_configured:
        logger.info("[compliance-monitor] email not configured â skipping stall check")
        return {
            "all_ok": True,
            "email_configured": False,
            "at_risk_count": 0,
            "sends_last_24h": 0,
            "failures": [],
        }

    # ---- Trusts with a compliance due date inside the lookahead window ----
    at_risk = 0
    async for rec in db.trust_state_compliance.find(
        {},
        {
            "_id": 0,
            "trust_id": 1,
            "state_code": 1,
            "notice_next_due": 1,
            "accounting_next_due": 1,
        },
    ):
        hit = False
        for due_raw in (rec.get("notice_next_due"), rec.get("accounting_next_due")):
            if due_raw in (None, "null", "", "None"):
                continue
            try:
                due = datetime.fromisoformat(str(due_raw)[:10]).date()
            except (ValueError, TypeError):
                continue
            days_remaining = (due - now.date()).days
            if days_remaining <= STALL_LOOKAHEAD_DAYS:  # includes overdue (< 0)
                hit = True
                break
        if hit:
            at_risk += 1

    # ---- Compliance reminder sends in the last 24h (audit trail) ----
    sends_last_24h = 0
    async for log in db.audit_logs.find(
        {"action": REMINDER_SENT_ACTION}, {"_id": 0, "timestamp": 1}
    ):
        ts = _as_dt(log.get("timestamp"))
        if ts is None or ts < day_ago:
            continue
        sends_last_24h += 1

    # ---- Assert: at-risk trusts require a recent send ----
    if at_risk > 0 and sends_last_24h == 0:
        failures.append(
            f"State compliance reminders stalled: {at_risk} trust(s) have a "
            f"compliance deadline within {STALL_LOOKAHEAD_DAYS} days (or overdue), "
            f"but zero compliance reminders were sent in the last {SEND_WINDOW_HOURS}h"
        )

    all_ok = len(failures) == 0

    if not all_ok:
        detail = {
            "at_risk_count": at_risk,
            "sends_last_24h": sends_last_24h,
            "lookahead_days": STALL_LOOKAHEAD_DAYS,
        }
        try:
            await notify(
                title="State compliance reminders stalled",
                message="; ".join(failures),
                details=detail,
                alert_level="red",
            )
        except Exception as e:
            logger.error(f"[compliance-monitor] failed to send RED alert: {e}")
    else:
        logger.info(
            f"[compliance-monitor] OK â at_risk={at_risk}, sends_24h={sends_last_24h}"
        )

    return {
        "all_ok": all_ok,
        "email_configured": True,
        "at_risk_count": at_risk,
        "sends_last_24h": sends_last_24h,
        "failures": failures,
    }
