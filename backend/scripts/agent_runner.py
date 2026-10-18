#!/usr/bin/env python3
"""
TrustOffice Internal Proactive Agent Runner (Phase 1 MVP)

Iterates customers with agent_enabled=True and produces:
- Daily deadline checks: 7/14/30 days out + overdue (from db.deadlines)
- Weekly governance health-score check: alert on 5+ point drops
- Monthly digest: summary of deadlines + health score highlights

DRAFTS-ONLY RULE: every communication is produced as a draft with status=draft.
The runner only sends email when the customer record has agent_consent=True.
Missing or false consent fails closed.

Every action and every produced communication is logged to agent_activity.

Usage:
    cd backend
    .venv/bin/python scripts/agent_runner.py --run-id agent_2026-10-18_daily --mode daily
    .venv/bin/python scripts/agent_runner.py --run-id agent_2026-10-18_weekly --mode weekly
    .venv/bin/python scripts/agent_runner.py --run-id agent_2026-10-18_monthly --mode monthly
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Make imports work when run from repo root or backend/scripts
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database import db
from agent_mailer import AgentMailer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEADLINE_WINDOWS = [7, 14, 30]
HEALTH_SCORE_DROP_THRESHOLD = 5
MONTHLY_DIGEST_DAY = 1  # first of the month


# ---------------------------------------------------------------------------
# Time helpers (mockable for tests)
# ---------------------------------------------------------------------------

class Clock:
    """Simple injectable clock so deadline logic can be unit-tested."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def today(self) -> date:
        return self.now().date()


_CLOCK = Clock()


def _set_clock(clock: Clock):
    global _CLOCK
    _CLOCK = clock


def _now_iso() -> str:
    return _CLOCK.now().isoformat()


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            return None


def _days_until(due: Optional[Any]) -> Optional[int]:
    due_date = _parse_date(due)
    if due_date is None:
        return None
    return (due_date - _CLOCK.today()).days


def _format_date(value: Any) -> str:
    d = _parse_date(value)
    return d.strftime("%B %d, %Y") if d else str(value)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

async def _log_activity(
    customer_id: str,
    action: str,
    trust_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> str:
    activity_id = f"agent_act_{uuid.uuid4().hex[:12]}"
    await db.agent_activity.insert_one({
        "activity_id": activity_id,
        "customer_id": customer_id,
        "trust_id": trust_id,
        "action": action,
        "payload": payload or {},
        "run_id": run_id,
        "ts": _now_iso(),
    })
    return activity_id


async def _log_communication(
    customer_id: str,
    communication_type: str,
    subject: str,
    status: str,
    trust_id: Optional[str] = None,
    send_result: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> str:
    comm_id = f"agent_comm_{uuid.uuid4().hex[:12]}"
    await db.agent_communications.insert_one({
        "communication_id": comm_id,
        "customer_id": customer_id,
        "trust_id": trust_id,
        "type": communication_type,
        "subject": subject,
        "status": status,
        "send_result": send_result or {},
        "run_id": run_id,
        "ts": _now_iso(),
    })
    await _log_activity(
        customer_id=customer_id,
        action="communication_" + status,
        trust_id=trust_id,
        payload={"communication_id": comm_id, "type": communication_type, "subject": subject, "send_result": send_result},
        run_id=run_id,
    )
    return comm_id


# ---------------------------------------------------------------------------
# Email content
# ---------------------------------------------------------------------------

def _html_wrapper(title: str, body_parts: List[str]) -> str:
    body = "\n".join(body_parts)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{title}</title></head>
<body style="font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1a1a2e;line-height:1.6;max-width:600px;margin:0 auto;padding:24px;">
{body}
<p style="margin:24px 0 0 0;font-size:13px;color:#64748b;">Your trust administrator,<br>TrustOffice Agent</p>
<p style="margin:8px 0 0 0;font-size:12px;color:#94a3b8;">This is an automated message from your TrustOffice account. You control it in Settings.</p>
</body>
</html>"""


def _text_wrapper(title: str, paragraphs: List[str]) -> str:
    lines = [title, ""] + paragraphs + ["", "Your trust administrator,", "TrustOffice Agent", "", "This is an automated message from your TrustOffice account. You control it in Settings."]
    return "\n\n".join(lines)


def _deadline_check_email(
    customer_name: str,
    trust_name: str,
    windows: List[int],
    overdue: List[Dict[str, Any]],
    upcoming: List[Tuple[int, List[Dict[str, Any]]]],
) -> Tuple[str, str, str]:
    subject = f"TrustOffice deadline check for {trust_name}"
    intro = f"Hi {customer_name or 'there'},"

    paragraphs: List[str] = [intro]
    html_parts: List[str] = [f"<p style='margin:0 0 14px 0;'>{intro}</p>"]

    paragraphs.append(f"Here is what your trust administrator noticed for {trust_name}.")
    html_parts.append(f"<p style='margin:0 0 14px 0;'>Here is what your trust administrator noticed for {trust_name}.</p>")

    if overdue:
        paragraphs.append("Overdue items — these need attention now:")
        html_parts.append("<p style='margin:0 0 6px 0;font-weight:600;'>Overdue items — these need attention now:</p><ul style='margin:0 0 14px 0;'>")
        for d in overdue:
            line = f"- {d.get('title', 'Deadline')}: due {_format_date(d.get('due_date'))}"
            paragraphs.append(line)
            html_parts.append(f"<li>{d.get('title', 'Deadline')}: due {_format_date(d.get('due_date'))}</li>")
        html_parts.append("</ul>")

    for window, items in upcoming:
        if not items:
            continue
        paragraphs.append(f"Coming up in {window} days:")
        html_parts.append(f"<p style='margin:0 0 6px 0;font-weight:600;'>Coming up in {window} days:</p><ul style='margin:0 0 14px 0;'>")
        for d in items:
            line = f"- {d.get('title', 'Deadline')}: due {_format_date(d.get('due_date'))}"
            paragraphs.append(line)
            html_parts.append(f"<li>{d.get('title', 'Deadline')}: due {_format_date(d.get('due_date'))}</li>")
        html_parts.append("</ul>")

    if not overdue and not any(items for _, items in upcoming):
        paragraphs.append("No deadlines need attention right now. Your trust administrator will check again tomorrow.")
        html_parts.append("<p style='margin:0 0 14px 0;'>No deadlines need attention right now. Your trust administrator will check again tomorrow.</p>")

    html = _html_wrapper(subject, html_parts)
    text = _text_wrapper(subject, paragraphs)
    return subject, html, text


def _health_score_alert_email(
    customer_name: str,
    trust_name: str,
    previous_score: int,
    current_score: int,
    drop: int,
    findings: List[Dict[str, Any]],
) -> Tuple[str, str, str]:
    subject = f"TrustOffice health-score alert for {trust_name}"
    intro = f"Hi {customer_name or 'there'},"
    paragraphs = [intro]
    html_parts = [f"<p style='margin:0 0 14px 0;'>{intro}</p>"]

    paragraphs.append(f"Your trust administrator noticed your governance health score for {trust_name} dropped from {previous_score} to {current_score} (down {drop} points).")
    html_parts.append(f"<p style='margin:0 0 14px 0;'>Your trust administrator noticed your governance health score for {trust_name} dropped from {previous_score} to {current_score} (down {drop} points).</p>")

    if findings:
        paragraphs.append("The main items pulling it down:")
        html_parts.append("<p style='margin:0 0 6px 0;font-weight:600;'>The main items pulling it down:</p><ul style='margin:0 0 14px 0;'>")
        for f in findings[:5]:
            title = f.get("title") or f.get("criterion_name") or f.get("description") or "Risk finding"
            paragraphs.append(f"- {title}")
            html_parts.append(f"<li>{title}</li>")
        html_parts.append("</ul>")

    paragraphs.append("Log into TrustOffice to review the governance dashboard and see the next step for each item.")
    html_parts.append("<p style='margin:0 0 14px 0;'>Log into TrustOffice to review the governance dashboard and see the next step for each item.</p>")

    html = _html_wrapper(subject, html_parts)
    text = _text_wrapper(subject, paragraphs)
    return subject, html, text


def _monthly_digest_email(
    customer_name: str,
    trust_name: str,
    health_score: Optional[int],
    health_color: Optional[str],
    deadlines_total: int,
    overdue_count: int,
    due_soon_count: int,
    completed_count: int,
    top_deadlines: List[Dict[str, Any]],
) -> Tuple[str, str, str]:
    month_label = _CLOCK.today().strftime("%B %Y")
    subject = f"Your {month_label} trust digest for {trust_name}"
    intro = f"Hi {customer_name or 'there'},"
    paragraphs = [intro]
    html_parts = [f"<p style='margin:0 0 14px 0;'>{intro}</p>"]

    paragraphs.append(f"Here is your monthly trust summary from your trust administrator for {trust_name}.")
    html_parts.append(f"<p style='margin:0 0 14px 0;'>Here is your monthly trust summary from your trust administrator for {trust_name}.</p>")

    score_text = "not yet calculated" if health_score is None else str(health_score)
    score_html = f"<strong>Governance health score:</strong> {score_text}{f' ({health_color})' if health_color else ''}"
    paragraphs.append(f"Governance health score: {score_text}{f' ({health_color})' if health_color else ''}")
    html_parts.append(f"<p style='margin:0 0 6px 0;'>{score_html}</p>")

    counts = f"Deadlines this month: {deadlines_total} total — {overdue_count} overdue, {due_soon_count} due soon, {completed_count} completed."
    paragraphs.append(counts)
    html_parts.append(f"<p style='margin:0 0 6px 0;'>{counts}</p>")

    if top_deadlines:
        paragraphs.append("Up next:")
        html_parts.append("<p style='margin:0 0 6px 0;font-weight:600;'>Up next:</p><ul style='margin:0 0 14px 0;'>")
        for d in top_deadlines[:5]:
            line = f"- {d.get('title', 'Deadline')}: due {_format_date(d.get('due_date'))}"
            paragraphs.append(line)
            html_parts.append(f"<li>{d.get('title', 'Deadline')}: due {_format_date(d.get('due_date'))}</li>")
        html_parts.append("</ul>")

    paragraphs.append("Reply to this email if anything looks off, or update details directly in TrustOffice.")
    html_parts.append("<p style='margin:0 0 14px 0;'>Reply to this email if anything looks off, or update details directly in TrustOffice.</p>")

    html = _html_wrapper(subject, html_parts)
    text = _text_wrapper(subject, paragraphs)
    return subject, html, text


# ---------------------------------------------------------------------------
# Core runners
# ---------------------------------------------------------------------------

async def _load_enabled_customers(run_id: str) -> List[Dict[str, Any]]:
    """Return all customers with agent_enabled=True."""
    cursor = db.users.find(
        {"agent_enabled": True},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "agent_consent": 1},
    )
    return await cursor.to_list(length=10000)


async def _load_trusts(customer_id: str) -> List[Dict[str, Any]]:
    return await db.trusts.find(
        {"user_id": customer_id},
        {"_id": 0, "trust_id": 1, "name": 1},
    ).to_list(length=1000)


async def _get_deadlines(trust_id: str) -> List[Dict[str, Any]]:
    """Return non-terminal deadlines for a trust, earliest first."""
    docs = await db.deadlines.find(
        {"trust_id": trust_id, "status": {"$nin": ["completed", "waived"]}},
        {"_id": 0},
    ).sort("due_date", 1).to_list(length=1000)
    for d in docs:
        d["days_remaining"] = _days_until(d.get("due_date"))
    return docs


async def _get_latest_health_snapshot(trust_id: str) -> Optional[Dict[str, Any]]:
    return await db.health_score_snapshots.find_one(
        {"trust_id": trust_id},
        {"_id": 0, "score_value": 1, "color": 1, "calculated_at": 1, "risk_findings": 1, "criteria_breakdown": 1},
        sort=[("calculated_at", -1)],
    )


async def _get_previous_health_snapshot(trust_id: str, before: str) -> Optional[Dict[str, Any]]:
    return await db.health_score_snapshots.find_one(
        {"trust_id": trust_id, "calculated_at": {"$lt": before}},
        {"_id": 0, "score_value": 1, "calculated_at": 1},
        sort=[("calculated_at", -1)],
    )


def _deadline_buckets(deadlines: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Tuple[int, List[Dict[str, Any]]]]]:
    """Split deadlines into overdue and their closest window bucket."""
    overdue: List[Dict[str, Any]] = []
    windows: Dict[int, List[Dict[str, Any]]] = {w: [] for w in DEADLINE_WINDOWS}
    for d in deadlines:
        days = d.get("days_remaining")
        if days is None:
            continue
        if days < 0:
            overdue.append(d)
            continue
        for window in DEADLINE_WINDOWS:
            if 0 <= days <= window:
                windows[window].append(d)
                break
    upcoming = [(w, windows[w]) for w in DEADLINE_WINDOWS]
    return overdue, upcoming


async def _send_or_draft(
    mailer: AgentMailer,
    customer: Dict[str, Any],
    comm_type: str,
    subject: str,
    html: str,
    text: str,
    trust_id: Optional[str],
    run_id: str,
) -> Dict[str, Any]:
    """Draft or send a communication based on agent_consent. Returns send_result."""
    consent = bool(customer.get("agent_consent", False))
    send = consent

    result = await mailer.send_or_draft(
        to_email=customer["email"],
        to_name=customer.get("name"),
        subject=subject,
        html_body=html,
        text_body=text,
        tag=f"agent:{comm_type}",
        send=send,
    )

    status = result.get("status", "draft")
    if status not in ("sent", "failed"):
        status = "draft"

    await _log_communication(
        customer_id=customer["user_id"],
        communication_type=comm_type,
        subject=subject,
        status=status,
        trust_id=trust_id,
        send_result=result,
        run_id=run_id,
    )
    return result


async def run_daily(run_id: str, mailer: Optional[AgentMailer] = None) -> Dict[str, Any]:
    """Run daily deadline checks for all agent-enabled customers."""
    mailer = mailer or AgentMailer()
    customers = await _load_enabled_customers(run_id)
    summary = {"customers": len(customers), "drafts": 0, "sent": 0, "failed": 0, "errors": 0}

    for customer in customers:
        try:
            trusts = await _load_trusts(customer["user_id"])
            for trust in trusts:
                deadlines = await _get_deadlines(trust["trust_id"])
                overdue, upcoming = _deadline_buckets(deadlines)
                if not overdue and not any(items for _, items in upcoming):
                    await _log_activity(
                        customer_id=customer["user_id"],
                        action="deadline_check_no_action",
                        trust_id=trust["trust_id"],
                        run_id=run_id,
                    )
                    continue

                subject, html, text = _deadline_check_email(
                    customer_name=customer.get("name"),
                    trust_name=trust.get("name") or trust["trust_id"],
                    windows=DEADLINE_WINDOWS,
                    overdue=overdue,
                    upcoming=upcoming,
                )
                result = await _send_or_draft(
                    mailer, customer, "deadline_check", subject, html, text,
                    trust["trust_id"], run_id,
                )
                summary["drafts"] += 1 if result.get("status") == "draft" else 0
                summary["sent"] += 1 if result.get("status") == "sent" else 0
                summary["failed"] += 1 if result.get("status") == "failed" else 0
                await _log_activity(
                    customer_id=customer["user_id"],
                    action="deadline_check",
                    trust_id=trust["trust_id"],
                    payload={"overdue": len(overdue), "upcoming_by_window": {str(w): len(items) for w, items in upcoming}, "send_status": result.get("status")},
                    run_id=run_id,
                )
        except Exception as e:
            logger.exception(f"Daily run failed for customer {customer.get('user_id')}: {e}")
            summary["errors"] += 1
            await _log_activity(
                customer_id=customer.get("user_id", "unknown"),
                action="daily_run_error",
                payload={"error": str(e)},
                run_id=run_id,
            )

    return summary


async def run_weekly(run_id: str, mailer: Optional[AgentMailer] = None) -> Dict[str, Any]:
    """Run weekly governance health-score checks for agent-enabled customers."""
    mailer = mailer or AgentMailer()
    customers = await _load_enabled_customers(run_id)
    summary = {"customers": len(customers), "drafts": 0, "sent": 0, "failed": 0, "errors": 0, "alerts": 0}

    for customer in customers:
        try:
            trusts = await _load_trusts(customer["user_id"])
            for trust in trusts:
                snapshot = await _get_latest_health_snapshot(trust["trust_id"])
                if not snapshot or snapshot.get("score_value") is None:
                    continue
                current_score = int(snapshot["score_value"])
                previous = await _get_previous_health_snapshot(
                    trust["trust_id"], snapshot["calculated_at"]
                )
                if not previous or previous.get("score_value") is None:
                    continue
                previous_score = int(previous["score_value"])
                drop = previous_score - current_score
                if drop < HEALTH_SCORE_DROP_THRESHOLD:
                    continue

                findings: List[Dict[str, Any]] = []
                for c in snapshot.get("criteria_breakdown") or []:
                    if not c.get("achieved") and not c.get("no_data"):
                        findings.append({"title": c.get("name", "Governance item"), "criterion_name": c.get("name")})

                subject, html, text = _health_score_alert_email(
                    customer_name=customer.get("name"),
                    trust_name=trust.get("name") or trust["trust_id"],
                    previous_score=previous_score,
                    current_score=current_score,
                    drop=drop,
                    findings=findings,
                )
                result = await _send_or_draft(
                    mailer, customer, "health_score_alert", subject, html, text,
                    trust["trust_id"], run_id,
                )
                summary["drafts"] += 1 if result.get("status") == "draft" else 0
                summary["sent"] += 1 if result.get("status") == "sent" else 0
                summary["failed"] += 1 if result.get("status") == "failed" else 0
                summary["alerts"] += 1
                await _log_activity(
                    customer_id=customer["user_id"],
                    action="health_score_alert",
                    trust_id=trust["trust_id"],
                    payload={"previous_score": previous_score, "current_score": current_score, "drop": drop, "send_status": result.get("status")},
                    run_id=run_id,
                )
        except Exception as e:
            logger.exception(f"Weekly run failed for customer {customer.get('user_id')}: {e}")
            summary["errors"] += 1
            await _log_activity(
                customer_id=customer.get("user_id", "unknown"),
                action="weekly_run_error",
                payload={"error": str(e)},
                run_id=run_id,
            )

    return summary


async def run_monthly(run_id: str, mailer: Optional[AgentMailer] = None) -> Dict[str, Any]:
    """Run monthly digest for agent-enabled customers."""
    mailer = mailer or AgentMailer()
    customers = await _load_enabled_customers(run_id)
    summary = {"customers": len(customers), "drafts": 0, "sent": 0, "failed": 0, "errors": 0, "digests": 0}

    for customer in customers:
        try:
            trusts = await _load_trusts(customer["user_id"])
            for trust in trusts:
                deadlines = await _get_deadlines(trust["trust_id"])
                overdue = [d for d in deadlines if (d.get("days_remaining") or 0) < 0]
                due_soon = [d for d in deadlines if 0 <= (d.get("days_remaining") or 0) <= 7]
                completed = await db.deadlines.count_documents({"trust_id": trust["trust_id"], "status": "completed"})
                snapshot = await _get_latest_health_snapshot(trust["trust_id"])

                subject, html, text = _monthly_digest_email(
                    customer_name=customer.get("name"),
                    trust_name=trust.get("name") or trust["trust_id"],
                    health_score=snapshot.get("score_value") if snapshot else None,
                    health_color=snapshot.get("color") if snapshot else None,
                    deadlines_total=len(deadlines),
                    overdue_count=len(overdue),
                    due_soon_count=len(due_soon),
                    completed_count=completed,
                    top_deadlines=deadlines[:5],
                )
                result = await _send_or_draft(
                    mailer, customer, "monthly_digest", subject, html, text,
                    trust["trust_id"], run_id,
                )
                summary["drafts"] += 1 if result.get("status") == "draft" else 0
                summary["sent"] += 1 if result.get("status") == "sent" else 0
                summary["failed"] += 1 if result.get("status") == "failed" else 0
                summary["digests"] += 1
                await _log_activity(
                    customer_id=customer["user_id"],
                    action="monthly_digest",
                    trust_id=trust["trust_id"],
                    payload={"deadlines_total": len(deadlines), "send_status": result.get("status")},
                    run_id=run_id,
                )
        except Exception as e:
            logger.exception(f"Monthly run failed for customer {customer.get('user_id')}: {e}")
            summary["errors"] += 1
            await _log_activity(
                customer_id=customer.get("user_id", "unknown"),
                action="monthly_run_error",
                payload={"error": str(e)},
                run_id=run_id,
            )

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main():
    _configure_logging()
    parser = argparse.ArgumentParser(description="TrustOffice internal proactive agent runner")
    parser.add_argument("--run-id", required=False, help="Unique run identifier")
    parser.add_argument("--mode", choices=["daily", "weekly", "monthly"], required=True)
    args = parser.parse_args()

    run_id = args.run_id or f"agent_{_CLOCK.now().strftime('%Y%m%d_%H%M%S')}"

    mailer = AgentMailer()
    if args.mode == "daily":
        result = await run_daily(run_id, mailer)
    elif args.mode == "weekly":
        result = await run_weekly(run_id, mailer)
    else:
        result = await run_monthly(run_id, mailer)

    logger.info(f"Agent run {run_id} ({args.mode}) finished: {result}")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
