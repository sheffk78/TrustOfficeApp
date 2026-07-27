"""
Meeting service — agenda generation, minutes CRUD, and approval workflow.

Phase 1 (Core Governance) of the TrustOffice council plan.

Approval workflow state machine:
    draft → pending_review → under_review → changes_requested → approved → finalized
    Any review state → rejected (terminal)

Every transition writes an ApprovalActionLog entry embedded in the
minutes_approval_status document.
"""
from datetime import datetime, timezone, date
from typing import List, Optional, Tuple
import uuid

from database import db
from models import (
    MeetingAgendaCreate, MeetingAgendaUpdate,
    MeetingAgendaItemCreate,
    MeetingCreate,
    MinutesApprovalStatusCreate, MinutesApprovalStatusUpdate,
    ApprovalStatus, ApprovalRole, AgendaItemType,
    MinutesType,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ==================== TRUST LOOKUP / OWNERSHIP ====================

async def get_owned_trust(trust_id: str, user_id: str) -> Optional[dict]:
    """Fetch a trust only if owned by this user (mirrors minutes.py pattern)."""
    return await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )


# ==================== AGENDA GENERATION ====================

# Smart-default agenda templates by meeting type. Each entry:
# (item_type, title, description, duration_minutes, priority)
_BASE_AGENDA: List[Tuple[AgendaItemType, str, str, int, str]] = [
    (
        AgendaItemType.review_financials,
        "Review Financial Statements",
        "Review trust bank balances, income, and expenses since last meeting.",
        15,
        "high",
    ),
    (
        AgendaItemType.compliance_check,
        "Compliance Check",
        "Confirm quarterly/annual compliance obligations are on track.",
        10,
        "high",
    ),
]

_MEETING_TYPE_AGENDA = {
    MinutesType.quarterly: [
        (
            AgendaItemType.review_distributions,
            "Review Distributions",
            "Review distributions made during the quarter and confirm documentation.",
            10,
            "normal",
        ),
        (
            AgendaItemType.review_compensation,
            "Trustee Compensation Review",
            "Confirm trustee compensation is within the approved plan.",
            10,
            "normal",
        ),
    ],
    MinutesType.annual: [
        (
            AgendaItemType.review_distributions,
            "Annual Distribution Review",
            "Review all distributions for the year and confirm documentation.",
            15,
            "high",
        ),
        (
            AgendaItemType.review_compensation,
            "Annual Trustee Compensation Review",
            "Review total annual trustee compensation against the approved plan.",
            15,
            "high",
        ),
        (
            AgendaItemType.tax_planning,
            "Tax Planning & Filings",
            "Review Form 1041 / K-1 preparation status and estimated tax payments.",
            20,
            "high",
        ),
        (
            AgendaItemType.asset_review,
            "Annual Asset Review",
            "Review trust assets, valuations, and insurance coverage.",
            15,
            "normal",
        ),
        (
            AgendaItemType.review_beneficiaries,
            "Beneficiary Review",
            "Confirm beneficiary information and contact details are current.",
            10,
            "normal",
        ),
    ],
    MinutesType.general: [],
    MinutesType.compensation: [
        (
            AgendaItemType.review_compensation,
            "Trustee Compensation Decision",
            "Review and document trustee compensation decision.",
            20,
            "high",
        ),
    ],
    MinutesType.distribution: [
        (
            AgendaItemType.review_distributions,
            "Distribution Decision",
            "Review and document proposed distribution(s).",
            20,
            "high",
        ),
    ],
    MinutesType.solvency: [
        (
            AgendaItemType.review_financials,
            "Solvency Review",
            "Confirm trust solvency and document findings.",
            20,
            "high",
        ),
    ],
}


async def _deadline_driven_items(trust_id: str) -> List[MeetingAgendaItemCreate]:
    """Generate agenda items from open compliance deadlines for this trust."""
    items: List[MeetingAgendaItemCreate] = []
    today = date.today().isoformat()
    open_deadlines = await db.deadlines.find(
        {
            "trust_id": trust_id,
            "status": {"$in": ["upcoming", "due_soon", "overdue"]},
        },
        {"_id": 0},
    ).sort("due_date", 1).to_list(20)

    for d in open_deadlines:
        overdue = d.get("due_date", "") < today
        items.append(
            MeetingAgendaItemCreate(
                item_type=AgendaItemType.compliance_check,
                title=f"Deadline: {d.get('title', 'Compliance deadline')}",
                description=(
                    f"{'OVERDUE — ' if overdue else ''}Due {d.get('due_date')}. "
                    f"{d.get('description') or ''}".strip()
                ),
                duration_minutes=10,
                priority="high" if overdue or d.get("priority") in ("critical", "high") else "normal",
            )
        )
    return items


async def _carryover_items(trust_id: str) -> List[MeetingAgendaItemCreate]:
    """Pull incomplete agenda items from the most recent prior agenda."""
    last_agenda = await db.meeting_agendas.find_one(
        {"trust_id": trust_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not last_agenda:
        return []
    items: List[MeetingAgendaItemCreate] = []
    for it in last_agenda.get("agenda_items", []):
        if not it.get("completed", False):
            items.append(
                MeetingAgendaItemCreate(
                    item_type=AgendaItemType(it.get("item_type", "other")),
                    title=f"Follow-up: {it.get('title')}",
                    description=it.get("description"),
                    duration_minutes=it.get("duration_minutes") or 10,
                    priority=it.get("priority", "normal"),
                )
            )
    return items


async def generate_agenda(trust_id: str, payload: MeetingAgendaCreate, user: dict) -> dict:
    """Create a meeting agenda. If no agenda_items supplied, generate smart defaults
    from meeting type, open deadlines, and incomplete prior agenda items."""
    now = _now()

    if payload.agenda_items:
        items = payload.agenda_items
    else:
        items = [
            MeetingAgendaItemCreate(
                item_type=t, title=ti, description=d, duration_minutes=dur, priority=p
            )
            for (t, ti, d, dur, p) in _BASE_AGENDA
        ]
        items += [
            MeetingAgendaItemCreate(
                item_type=t, title=ti, description=d, duration_minutes=dur, priority=p
            )
            for (t, ti, d, dur, p) in _MEETING_TYPE_AGENDA.get(payload.meeting_type, [])
        ]
        items += await _deadline_driven_items(trust_id)
        items += await _carryover_items(trust_id)

    agenda_id = _new_id("agenda")
    agenda_items_docs = [
        {
            "agenda_item_id": _new_id("agitem"),
            "item_type": it.item_type.value,
            "title": it.title,
            "description": it.description,
            "duration_minutes": it.duration_minutes,
            "priority": it.priority,
            "completed": False,
            "created_at": now,
        }
        for it in items
    ]

    agenda_doc = {
        "agenda_id": agenda_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "meeting_type": payload.meeting_type.value,
        "scheduled_date": payload.scheduled_date,
        "estimated_duration_minutes": payload.estimated_duration_minutes,
        "agenda_items": agenda_items_docs,
        "notes": payload.notes,
        "location": payload.location,
        "virtual_meeting_link": payload.virtual_meeting_link,
        "status": "scheduled",
        "created_at": now,
        "updated_at": None,
    }
    await db.meeting_agendas.insert_one(agenda_doc)
    agenda_doc.pop("_id", None)
    return agenda_doc


async def get_agenda(agenda_id: str, user_id: str) -> Optional[dict]:
    return await db.meeting_agendas.find_one(
        {"agenda_id": agenda_id, "user_id": user_id}, {"_id": 0}
    )


async def update_agenda(agenda_id: str, payload: MeetingAgendaUpdate, user_id: str) -> Optional[dict]:
    existing = await db.meeting_agendas.find_one({"agenda_id": agenda_id, "user_id": user_id})
    if not existing:
        return None

    updates: dict = {"updated_at": _now()}
    if payload.scheduled_date is not None:
        updates["scheduled_date"] = payload.scheduled_date
    if payload.estimated_duration_minutes is not None:
        updates["estimated_duration_minutes"] = payload.estimated_duration_minutes
    if payload.notes is not None:
        updates["notes"] = payload.notes
    if payload.location is not None:
        updates["location"] = payload.location
    if payload.virtual_meeting_link is not None:
        updates["virtual_meeting_link"] = payload.virtual_meeting_link
    if payload.status is not None:
        if payload.status not in ("scheduled", "completed", "cancelled"):
            raise ValueError("status must be one of: scheduled, completed, cancelled")
        updates["status"] = payload.status
    if payload.agenda_items is not None:
        now = _now()
        # Preserve completion state for items that already exist (matched by title+type)
        old_items = {
            (i.get("item_type"), i.get("title")): i
            for i in existing.get("agenda_items", [])
        }
        new_items = []
        for it in payload.agenda_items:
            key = (it.item_type.value, it.title)
            prior = old_items.get(key)
            new_items.append({
                "agenda_item_id": prior["agenda_item_id"] if prior else _new_id("agitem"),
                "item_type": it.item_type.value,
                "title": it.title,
                "description": it.description,
                "duration_minutes": it.duration_minutes,
                "priority": it.priority,
                "completed": prior.get("completed", False) if prior else False,
                "created_at": prior.get("created_at", now) if prior else now,
            })
        updates["agenda_items"] = new_items

    await db.meeting_agendas.update_one(
        {"agenda_id": agenda_id, "user_id": user_id}, {"$set": updates}
    )
    return await db.meeting_agendas.find_one(
        {"agenda_id": agenda_id, "user_id": user_id}, {"_id": 0}
    )


# ==================== MEETINGS (link agenda ↔ minutes) ====================

async def create_meeting(trust_id: str, payload: MeetingCreate, user: dict) -> dict:
    now = _now()
    meeting_id = _new_id("meeting")
    meeting_doc = {
        "meeting_id": meeting_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "agenda_id": payload.agenda_id,
        "meeting_type": payload.meeting_type.value,
        "actual_meeting_date": payload.actual_meeting_date,
        "attendees": payload.attendees,
        "other_attendees": payload.other_attendees,
        "location": payload.location,
        "virtual_meeting_link": payload.virtual_meeting_link,
        "notes": payload.notes,
        "status": "completed",
        "linked_minutes_id": None,
        "created_at": now,
        "updated_at": None,
    }
    await db.meetings.insert_one(meeting_doc)
    meeting_doc.pop("_id", None)
    return meeting_doc


# ==================== MINUTES + APPROVAL WORKFLOW ====================

# Valid transitions: current_status -> set of allowed next statuses
_TRANSITIONS = {
    ApprovalStatus.draft: {ApprovalStatus.pending_review, ApprovalStatus.rejected},
    ApprovalStatus.pending_review: {ApprovalStatus.under_review, ApprovalStatus.rejected},
    ApprovalStatus.under_review: {
        ApprovalStatus.approved,
        ApprovalStatus.changes_requested,
        ApprovalStatus.rejected,
    },
    ApprovalStatus.changes_requested: {ApprovalStatus.pending_review, ApprovalStatus.rejected},
    ApprovalStatus.approved: {ApprovalStatus.finalized},
    ApprovalStatus.rejected: set(),  # terminal
    ApprovalStatus.finalized: set(),  # terminal
}

# Map transition target -> (action label, role performing it)
_ACTION_MAP = {
    ApprovalStatus.pending_review: ("submitted", ApprovalRole.drafter),
    ApprovalStatus.under_review: ("reviewed", ApprovalRole.reviewer),
    ApprovalStatus.changes_requested: ("changes_requested", ApprovalRole.reviewer),
    ApprovalStatus.approved: ("approved", ApprovalRole.approver),
    ApprovalStatus.rejected: ("rejected", ApprovalRole.approver),
    ApprovalStatus.finalized: ("finalized", ApprovalRole.approver),
}


async def create_minutes_record(trust_id: str, payload: dict, user: dict) -> dict:
    """Create a minutes record in the new workflow and open its approval status."""
    now = _now()
    minutes_id = _new_id("minutes")

    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "meeting_id": payload.get("meeting_id"),
        "agenda_id": payload.get("agenda_id"),
        "minutes_type": payload.get("minutes_type", MinutesType.quarterly.value),
        "meeting_date": payload.get("meeting_date"),
        "participants_text": payload.get("participants_text", ""),
        "decisions_text": payload.get("decisions_text", ""),
        "sections": payload.get("sections", []),
        "template_data": payload.get("template_data", {}),
        "notes": payload.get("notes"),
        "status": "draft",
        "created_at": now,
        "updated_at": None,
    }
    await db.meeting_minutes.insert_one(minutes_doc)

    # If linked to a meeting record, back-link it
    if payload.get("meeting_id"):
        await db.meetings.update_one(
            {"meeting_id": payload["meeting_id"], "user_id": user["user_id"]},
            {"$set": {"linked_minutes_id": minutes_id, "updated_at": now}},
        )

    # Open approval workflow
    approval_doc = await _create_approval_status(
        MinutesApprovalStatusCreate(
            minutes_id=minutes_id,
            trust_id=trust_id,
            drafter_user_id=user["user_id"],
            due_date=payload.get("approval_due_date"),
        ),
        user,
    )

    minutes_doc.pop("_id", None)
    minutes_doc["approval_id"] = approval_doc["approval_id"]
    minutes_doc["approval_status"] = approval_doc["current_status"]
    return minutes_doc


async def _create_approval_status(payload: MinutesApprovalStatusCreate, user: dict) -> dict:
    now = _now()
    approval_id = _new_id("approval")
    user_name = user.get("name") or user.get("email", "")
    doc = {
        "approval_id": approval_id,
        "minutes_id": payload.minutes_id,
        "trust_id": payload.trust_id,
        "user_id": user["user_id"],
        "current_status": payload.current_status.value,
        "drafter_user_id": payload.drafter_user_id,
        "drafter_name": user_name,
        "reviewer_user_id": payload.reviewer_user_id,
        "reviewer_name": None,
        "approver_user_id": payload.approver_user_id,
        "approver_name": None,
        "due_date": payload.due_date,
        "priority": payload.priority,
        "action_log": [
            {
                "action": "created",
                "performed_by_user_id": user["user_id"],
                "performed_by_name": user_name,
                "performed_by_role": ApprovalRole.drafter.value,
                "timestamp": now,
                "note": None,
            }
        ],
        "changes_requested_note": None,
        "rejection_reason": None,
        "created_at": now,
        "updated_at": None,
    }
    await db.minutes_approval_status.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_minutes_record(minutes_id: str, user_id: str) -> Optional[dict]:
    doc = await db.meeting_minutes.find_one(
        {"minutes_id": minutes_id, "user_id": user_id}, {"_id": 0}
    )
    if not doc:
        return None
    approval = await db.minutes_approval_status.find_one(
        {"minutes_id": minutes_id, "user_id": user_id}, {"_id": 0}
    )
    if approval:
        doc["approval_id"] = approval["approval_id"]
        doc["approval_status"] = approval["current_status"]
    return doc


async def update_minutes_record(minutes_id: str, payload: dict, user_id: str) -> Optional[dict]:
    existing = await db.meeting_minutes.find_one(
        {"minutes_id": minutes_id, "user_id": user_id}
    )
    if not existing:
        return None

    # Guard: finalized minutes are immutable
    approval = await db.minutes_approval_status.find_one(
        {"minutes_id": minutes_id, "user_id": user_id}
    )
    if approval and approval.get("current_status") in (
        ApprovalStatus.finalized.value,
        ApprovalStatus.rejected.value,
    ):
        raise ValueError(f"Minutes are {approval['current_status']} and cannot be edited.")

    allowed = {
        "meeting_date", "participants_text", "decisions_text", "sections",
        "template_data", "notes", "meeting_id", "agenda_id", "minutes_type",
    }
    updates = {k: v for k, v in payload.items() if k in allowed and v is not None}
    if not updates:
        return await db.meeting_minutes.find_one(
            {"minutes_id": minutes_id, "user_id": user_id}, {"_id": 0}
        )
    updates["updated_at"] = _now()
    await db.meeting_minutes.update_one(
        {"minutes_id": minutes_id, "user_id": user_id}, {"$set": updates}
    )
    return await get_minutes_record(minutes_id, user_id)


async def get_approval_status(minutes_id: str, user_id: str) -> Optional[dict]:
    return await db.minutes_approval_status.find_one(
        {"minutes_id": minutes_id, "user_id": user_id}, {"_id": 0}
    )


async def transition_minutes(
    minutes_id: str,
    target: ApprovalStatus,
    user: dict,
    note: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """Advance the approval state machine.

    Returns (updated_doc, error). error is set if the minutes/approval
    don't exist or the transition is invalid.
    """
    approval = await db.minutes_approval_status.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]}
    )
    if not approval:
        return None, "Minutes approval record not found."

    current = ApprovalStatus(approval["current_status"])
    if target not in _TRANSITIONS.get(current, set()):
        return None, f"Invalid transition: {current.value} → {target.value}."

    action, role = _ACTION_MAP[target]
    now = _now()
    user_name = user.get("name") or user.get("email", "")

    log_entry = {
        "action": action,
        "performed_by_user_id": user["user_id"],
        "performed_by_name": user_name,
        "performed_by_role": role.value,
        "timestamp": now,
        "note": note,
    }

    set_fields: dict = {"current_status": target.value, "updated_at": now}
    if target == ApprovalStatus.changes_requested:
        set_fields["changes_requested_note"] = note
    if target == ApprovalStatus.rejected:
        set_fields["rejection_reason"] = note
    # Track who performed reviewer/approver actions
    if role == ApprovalRole.reviewer and not approval.get("reviewer_user_id"):
        set_fields["reviewer_user_id"] = user["user_id"]
        set_fields["reviewer_name"] = user_name
    if role == ApprovalRole.approver and not approval.get("approver_user_id"):
        set_fields["approver_user_id"] = user["user_id"]
        set_fields["approver_name"] = user_name

    await db.minutes_approval_status.update_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"$set": set_fields, "$push": {"action_log": log_entry}},
    )

    # Mirror the high-level status onto the minutes document
    await db.meeting_minutes.update_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"$set": {"status": target.value, "updated_at": now}},
    )

    updated = await db.minutes_approval_status.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    return updated, None


# ==================== WORKFLOW STATUS + HISTORY ====================

async def get_workflow_summary(trust_id: str, user_id: str) -> dict:
    now = _now()
    today = date.today().isoformat()

    approvals = await db.minutes_approval_status.find(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    ).to_list(200)

    pending = [
        a for a in approvals
        if a.get("current_status") in (
            ApprovalStatus.pending_review.value,
            ApprovalStatus.under_review.value,
            ApprovalStatus.changes_requested.value,
        )
    ]
    overdue = [
        a for a in pending
        if a.get("due_date") and a["due_date"] < today
    ]
    recently_completed = sorted(
        [
            a for a in approvals
            if a.get("current_status") in (
                ApprovalStatus.approved.value, ApprovalStatus.finalized.value
            )
        ],
        key=lambda a: a.get("updated_at") or a.get("created_at", ""),
        reverse=True,
    )[:5]

    return {
        "trust_id": trust_id,
        "pending_approvals_count": len(pending),
        "overdue_approvals_count": len(overdue),
        "recently_completed_approvals": [
            {
                "approval_id": a["approval_id"],
                "minutes_id": a["minutes_id"],
                "current_status": a["current_status"],
                "updated_at": a.get("updated_at"),
            }
            for a in recently_completed
        ],
        "calculated_at": now,
    }


async def get_meeting_history(trust_id: str, user_id: str) -> dict:
    agendas = await db.meeting_agendas.find(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    ).sort("scheduled_date", -1).to_list(100)

    meetings = await db.meetings.find(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    ).sort("actual_meeting_date", -1).to_list(100)

    minutes = await db.meeting_minutes.find(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    approvals = {
        a["minutes_id"]: a
        for a in await db.minutes_approval_status.find(
            {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
        ).to_list(200)
    }
    for m in minutes:
        a = approvals.get(m["minutes_id"])
        if a:
            m["approval_id"] = a["approval_id"]
            m["approval_status"] = a["current_status"]

    return {
        "trust_id": trust_id,
        "agendas": agendas,
        "meetings": meetings,
        "minutes": minutes,
    }
