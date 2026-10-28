"""
exec_hardening.py — shared hardening primitives for the Trust Assistant
action-execution path (council P0, 2026-10-23).

Two primitives live here, both used by routers/chat.py and the member-record
delete routes:

  1. READ-BACK VERIFICATION (verify_exec_write)
     After an action handler reports success, the record is READ BACK from
     Mongo by its primary key. A handler that claims success but wrote
     nothing is the exact failure mode that produced Jerel Kratt's
     "the draft does not exist" complaint (2026-10-23) and a stream of
     "phantom" success replies. If the read-back finds nothing:
       - execution_result flips to success=False, error="record not found
         after write"
       - notify_alert (discord_service) fires with action type, user_id,
         record id and timestamp — loud, at the moment it happens, zero cron.
     If the read-back finds the record: execution_result gains verified=True.

  2. DELETE PROVENANCE (audit_member_deletion)
     Every deletion of a MEMBER record writes an audit_logs row BEFORE the
     delete commits. The row carries:
       - actor_user_id       — whose record it was
       - performed_by        — "self" or "impersonated"
       - impersonated_by_admin_id — the admin's user_id when impersonating
       - record_type / record_id
       - deleted_at
       - snapshot_summary    — a small, non-sensitive summary of what went
                                away, so the trail is meaningful without
                                dumping the whole document
     A failed audit write FAILS LOUDLY (raises) — an unaudited delete is
     worse than a failed delete.

Design notes:
  - The read-back map is keyed by the chat endpoint_type (the same key
    ACTION_EXECUTION_MAP uses), because that is what every handler's
    result envelope reports back.
  - Deletion modes are explicit per collection: "hard" deletes the document,
    "soft" stamps deleted_at and keeps it. The caller decides; this module
    only owns the audit row and the ordering.
  - Impersonation attribution is derived from the JWT the caller presented.
    The backend mints a plain access token for the impersonated user, so
    the admin identity is NOT in the token — it is recovered from the
    admin_audit_log row written when the impersonation started. If that
    row cannot be found we fall back to "impersonated" with no admin id
    rather than silently claiming "self".
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. READ-BACK VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

# endpoint_type -> (mongo collection, primary key field, result key, scope field)
#
# Every entry here was verified against the actual insert site in the
# handler (see routers/chat.py _exec_* and actions_seed.py chat handlers).
# A collection or key that does not exist will surface as a read-back miss
# and page Discord — which is the intended behaviour for an unknown map
# entry, but every known endpoint_type is listed here.
#
#   collection  — the Mongo collection the write landed in
#   key_field   — the primary key field on the document
#   result_key  — the key in the handler's result envelope holding the id
#                 ("" means: use result["record_id"])
#   scope_field — an extra equality constraint on the lookup (usually
#                 "trust_id" or "user_id") so a read-back can never match
#                 another member's record. "" means no extra constraint.
#
# A value may also be a LIST of tuples for actions that create more than one
# record (contribute_asset creates a Schedule A item AND acceptance minutes).
READBACK_MAP: dict[str, Any] = {
    "minutes":                 ("minutes_records", "minutes_id", "", "user_id"),
    "contribute_asset":        [
        ("schedule_a_items", "item_id", "schedule_a_id", "user_id"),
        ("minutes_records", "minutes_id", "minutes_id", "user_id"),
    ],
    "distribution":            ("distribution_records", "distribution_id", "", "user_id"),
    "asset":                   ("schedule_a_items", "item_id", "", "user_id"),
    "asset_update":            ("schedule_a_items", "item_id", "", "user_id"),
    "beneficiary":             ("trust_unit_certificates", "certificate_id", "", "user_id"),
    "beneficiary_update":      ("trust_unit_certificates", "certificate_id", "", "user_id"),
    # beneficiary_removal is a SOFT delete (certificate flipped to
    # status=inactive), so the document still exists — the read-back finds it.
    "beneficiary_removal":     ("trust_unit_certificates", "certificate_id", "", "user_id"),
    "send_certificate":        ("trust_unit_certificates", "certificate_id", "", "user_id"),
    "document_upload":         ("vault_documents", "doc_id", "", "user_id"),
    "compensation_plan":       ("compensation_plans", "plan_id", "", "user_id"),
    "compensation_payment":    ("compensation_payments", "payment_id", "", "user_id"),
    "investment":              ("investments", "investment_id", "", "user_id"),
    "task":                    ("governance_tasks", "task_id", "", "user_id"),
    "transaction":             ("transactions", "transaction_id", "", "user_id"),
    "entity":                  ("entities", "entity_id", "", "user_id"),
    "class_beneficiary":       ("class_beneficiaries", "class_beneficiary_id", "", "user_id"),
    # settings_update writes to trusts (keyed by trust_id);
    # alert_dismiss upserts into dismissed_insights (keyed by criterion).
    "settings_update":         ("trusts", "trust_id", "", ""),
    "alert_dismiss":           ("dismissed_insights", "criterion_name", "criterion", "trust_id"),
}

# endpoint_type -> (mongo collection, primary key field, scope field)
#
# REMOVAL actions: nothing is created, so "read the created record back" does
# not apply. The meaningful check is the inverse — the record must be GONE
# (or, for soft deletes, no longer active). A removal that reports success
# while the record is still live is exactly the silent failure this bundle
# exists to eliminate, so it is checked in the opposite direction.
REMOVAL_MAP: dict[str, Any] = {
    # distribution_cancel hard-deletes the distribution record.
    "distribution_cancel":     ("distribution_records", "distribution_id", "user_id"),
    # class_beneficiary_removal hard-deletes the class + its members.
    "class_beneficiary_removal": ("class_beneficiaries", "class_beneficiary_id", "user_id"),
}

# The error string the council specified verbatim.
READBACK_MISS_ERROR = "record not found after write"


async def readback_targets(
    db,
    endpoint_type: str,
    result: dict,
    user_id: str = "",
) -> list[tuple[str, str, str, str]]:
    """
    Resolve the (collection, key_field, key_value, scope_field) tuples to
    read back.

    Returns an empty list when the action produced no verifiable record id
    (e.g. settings_update reports record_id=trust_id, but alert_dismiss
    reports only a criterion name) or when the endpoint_type is not in the
    map.
    """
    entry = READBACK_MAP.get(endpoint_type)
    if not entry:
        return []

    specs = entry if isinstance(entry, list) else [entry]
    targets: list[tuple[str, str, str, str]] = []
    for spec in specs:
        if len(spec) == 4:
            collection, key_field, result_key, scope_field = spec
        elif len(spec) == 3:
            collection, key_field, result_key = spec
            scope_field = ""
        else:
            collection, key_field = spec
            result_key = None
            scope_field = ""

        key_value = result.get(result_key) if result_key else None
        if key_value is None:
            key_value = result.get("record_id")
        if key_value is None and not result_key:
            key_value = result.get(f"{key_field}")
        if key_value is None:
            # Some handlers name their id differently (e.g. contribute_asset
            # returns minutes_id).
            for alt in ("minutes_id", "schedule_a_id", "distribution_id",
                        "certificate_id", "item_id", "payment_id", "plan_id",
                        "task_id", "transaction_id", "entity_id", "doc_id",
                        "investment_id", "class_beneficiary_id"):
                if result.get(alt):
                    key_value = result[alt]
                    break
        if not key_value:
            continue
        targets.append((collection, key_field, str(key_value), scope_field))
    return targets


# The status values that mean "this record is still live / actionable".
#
# A removal that leaves the record in one of these states is a silent
# failure: the member was told it was cancelled and it is not. Anything
# else (cancelled, superseded, replaced, inactive, deleted) counts as
# removed. The default for an absent status field is "active" — a record
# with no status is still live unless the collection says otherwise.
LIVE_STATUSES = frozenset({
    "active",
    "review",
    "pending",
    "approved",
    "executed",
    "open",
    "draft",
    "in_progress",
    "scheduled",
})


async def verify_removal(
    db,
    endpoint_type: str,
    result: dict,
    user_id: str,
    trust_id: str = "",
    action_type: str = "",
) -> dict:
    """
    Verify a REMOVAL action: the record it claims to have removed must
    actually be gone (or, for a soft delete, no longer active).

    A removal that reports success while the record is still live is a
    silent failure — the member was told it was cancelled and it is not.
    """
    entry = REMOVAL_MAP.get(endpoint_type)
    if not entry:
        result["verified"] = False
        result["verification_skipped"] = (
            f"no removal read-back mapping for endpoint_type '{endpoint_type}'"
        )
        return result

    collection, key_field, scope_field = entry
    key_value = result.get("record_id") or result.get(f"{key_field}")
    if not key_value:
        result["verified"] = False
        result["verification_skipped"] = "removal reported no record id"
        return result
    key_value = str(key_value)

    query: dict[str, Any] = {key_field: key_value}
    if scope_field and user_id:
        query[scope_field] = user_id

    try:
        still_there = await db[collection].find_one(query, {"_id": 0})
    except Exception as e:  # noqa: BLE001
        logger.error(
            "REMOVAL_READBACK_ERROR | endpoint_type=%s collection=%s key=%s error=%s",
            endpoint_type, collection, key_value, e,
        )
        result["verified"] = False
        result["verification_error"] = str(e)
        return result

    if still_there is None:
        result["verified"] = True
        result["verified_collection"] = collection
        result["verified_key"] = key_value
        logger.info(
            "REMOVAL_READBACK_OK | endpoint_type=%s collection=%s key=%s user=%s",
            endpoint_type, collection, key_value, user_id,
        )
        return result

    # The record is still there. Soft deletes flip a status field instead —
    # but ONLY a status that means "not live any more" counts as removed.
    # A record left in "review"/"pending"/"active" is still actionable and
    # the member was told otherwise, so it is a failure.
    status = still_there.get("status")
    if status is None:
        still_active = True
    else:
        still_active = str(status).strip().lower() in LIVE_STATUSES
    if not still_active:
        result["verified"] = True
        result["verified_collection"] = collection
        result["verified_key"] = key_value
        result["verified_soft_delete"] = True
        logger.info(
            "REMOVAL_READBACK_OK | endpoint_type=%s collection=%s key=%s "
            "(soft-deleted, status=%s) user=%s",
            endpoint_type, collection, key_value, status,
            user_id,
        )
        return result

    ts = datetime.now(timezone.utc).isoformat()
    result["success"] = False
    result["verified"] = False
    result["error"] = "record still present after removal"
    result["readback_still_present_collection"] = collection
    result["readback_still_present_key"] = key_value
    result["readback_still_present_at"] = ts

    logger.error(
        "REMOVAL_READBACK_STILL_PRESENT | endpoint_type=%s collection=%s key=%s "
        "action=%s user=%s trust=%s | removal reported success but record remains",
        endpoint_type, collection, key_value, action_type, user_id, trust_id,
    )
    try:
        from discord_service import notify_alert
        await notify_alert(
            title="Trust Assistant: removal read-back MISS",
            message=(
                f"A chat action reported a successful removal but the record "
                f"is still present.\n"
                f"action_type: {action_type or endpoint_type}\n"
                f"endpoint_type: {endpoint_type}\n"
                f"user_id: {user_id}\n"
                f"trust_id: {trust_id or '(none)'}\n"
                f"record id: {key_value}\n"
                f"collection: {collection}\n"
                f"timestamp: {ts}\n"
                f"result: the member was told the record was removed, but it "
                f"is still there. The action has been flipped to success=false."
            ),
            color=0xB44040,
            ping_kit=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(
            "REMOVAL_READBACK_ALERT_FAILED | endpoint_type=%s key=%s error=%s",
            endpoint_type, key_value, e,
        )
    return result


async def verify_exec_write(
    db,
    endpoint_type: str,
    result: dict,
    user_id: str,
    trust_id: str = "",
    action_type: str = "",
) -> dict:
    """
    Read the created record back from Mongo and annotate `result`.

    On success: result["verified"] = True
    On miss:    result["success"] = False
                result["error"]  = "record not found after write"
                result["verified"] = False
                and a Discord alert fires (loud, immediate, no cron).

    `result` is mutated in place AND returned, so callers can do either
    `result = await verify_exec_write(...)` or just call it for effect.
    """
    if not isinstance(result, dict):
        return result
    # Always stamp the endpoint_type so downstream reply builders (and the
    # stored action card) know which action produced this envelope.
    result.setdefault("endpoint_type", endpoint_type)
    if not result.get("success"):
        # A failed action needs no read-back.
        return result

    # Removal actions are verified in the opposite direction: the record
    # must be GONE (or deactivated), not present.
    if endpoint_type in REMOVAL_MAP:
        return await verify_removal(
            db,
            endpoint_type=endpoint_type,
            result=result,
            user_id=user_id,
            trust_id=trust_id,
            action_type=action_type,
        )

    targets = await readback_targets(db, endpoint_type, result, user_id=user_id)
    if not targets:
        # Nothing verifiable to check. Mark it honestly rather than
        # claiming a verification we did not perform.
        result["verified"] = False
        result["verification_skipped"] = (
            f"no read-back mapping for endpoint_type '{endpoint_type}'"
        )
        logger.warning(
            "EXEC_READBACK_SKIPPED | endpoint_type=%s action=%s user=%s | no mapping",
            endpoint_type, action_type, user_id,
        )
        return result

    # Read every target. ALL must be present for the action to count as
    # verified — a partial write (e.g. the minutes landed but the Schedule A
    # item did not) is still a broken action.
    missing: list[tuple[str, str]] = []
    verified_pairs: list[tuple[str, str]] = []
    read_error: Optional[str] = None

    for collection, key_field, key_value, scope_field in targets:
        query: dict[str, Any] = {key_field: key_value}
        if scope_field and user_id:
            query[scope_field] = user_id
        try:
            found = await db[collection].find_one(query, {"_id": 0})
        except Exception as e:  # noqa: BLE001 — a broken read must not mask the write
            read_error = f"{collection}.{key_field}={key_value}: {e}"
            logger.error(
                "EXEC_READBACK_ERROR | endpoint_type=%s collection=%s key=%s error=%s",
                endpoint_type, collection, key_value, e,
            )
            continue
        if found is not None:
            verified_pairs.append((collection, key_value))
        else:
            missing.append((collection, key_value))

    if read_error and not missing:
        # The read itself blew up — we cannot claim verification.
        result["verified"] = False
        result["verification_error"] = read_error
        return result

    if not missing:
        result["verified"] = True
        result["verified_collection"] = verified_pairs[0][0]
        result["verified_key"] = verified_pairs[0][1]
        if len(verified_pairs) > 1:
            result["verified_records"] = [
                {"collection": c, "key": k} for c, k in verified_pairs
            ]
        logger.info(
            "EXEC_READBACK_OK | endpoint_type=%s records=%s action=%s user=%s",
            endpoint_type, verified_pairs, action_type, user_id,
        )
        return result

    # ── MISS: the handler claimed success but the record is not there ──
    ts = datetime.now(timezone.utc).isoformat()
    missing_desc = ", ".join(f"{c}/{k}" for c, k in missing)
    result["success"] = False
    result["verified"] = False
    result["error"] = READBACK_MISS_ERROR
    result["readback_missing_collection"] = missing[0][0]
    result["readback_missing_key"] = missing[0][1]
    result["readback_missing_at"] = ts

    logger.error(
        "EXEC_READBACK_MISS | endpoint_type=%s missing=%s action=%s "
        "user=%s trust=%s | write reported success but record is absent",
        endpoint_type, missing_desc, action_type, user_id, trust_id,
    )

    # Fire the alert. Never let a Discord failure change the outcome.
    try:
        from discord_service import notify_alert
        await notify_alert(
            title="Trust Assistant: exec read-back MISS",
            message=(
                f"A chat action reported success but its record was not found "
                f"after the write.\n"
                f"action_type: {action_type or endpoint_type}\n"
                f"endpoint_type: {endpoint_type}\n"
                f"user_id: {user_id}\n"
                f"trust_id: {trust_id or '(none)'}\n"
                f"record id: {missing_desc}\n"
                f"timestamp: {ts}\n"
                f"result: the member was told the action succeeded, but no "
                f"record exists. The action has been flipped to success=false."
            ),
            color=0xB44040,  # RUST — RED severity
            ping_kit=True,
        )
    except Exception as e:  # noqa: BLE001 — the alert must never mask the failure
        logger.error(
            "EXEC_READBACK_ALERT_FAILED | endpoint_type=%s missing=%s error=%s",
            endpoint_type, missing_desc, e,
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. DELETE PROVENANCE
# ─────────────────────────────────────────────────────────────────────────────

# Snapshot fields per record type. Kept small on purpose: enough to make
# the trail meaningful, not a full document dump (which could carry PII).
SNAPSHOT_FIELDS: dict[str, list[str]] = {
    "minutes_records": ["minutes_id", "status", "minutes_type", "title",
                        "meeting_date", "trust_id"],
    "minutes_templates": ["minutes_id", "status", "template_type", "trust_id"],
    "chat_conversations": ["conversation_id", "title", "trust_id", "message_count"],
    "schedule_a_items": ["item_id", "status", "category", "description",
                         "approximate_value", "trust_id"],
    "governance_tasks": ["task_id", "task_type", "status", "description", "trust_id"],
    "transactions": ["transaction_id", "amount", "direction", "date", "trust_id"],
    "entities": ["entity_id", "name", "entity_type", "trust_id"],
    "class_beneficiaries": ["class_beneficiary_id", "class_type", "description",
                             "percentage", "trust_id"],
    "distribution_records": ["distribution_id", "status", "beneficiary_name",
                              "amount", "date", "trust_id"],
    "compensation_plans": ["plan_id", "trustee_name", "annual_amount", "trust_id"],
    "compensation_payments": ["payment_id", "amount", "payment_date", "trust_id"],
    "vault_documents": ["doc_id", "title", "category", "file_name", "trust_id"],
    "investments": ["investment_id", "asset_name", "asset_type", "current_value",
                    "trust_id"],
    "trust_unit_certificates": ["certificate_id", "holder_name", "units",
                                "status", "trust_id"],
}


def build_snapshot(record: Optional[dict], record_type: str) -> dict:
    """Build a small, non-sensitive summary of a record about to be deleted."""
    if not record:
        return {}
    fields = SNAPSHOT_FIELDS.get(record_type)
    if not fields:
        # Unknown type: keep only the identifying fields, never the body.
        return {k: record.get(k) for k in ("trust_id",) if k in record}
    out = {}
    for f in fields:
        if f in record:
            v = record[f]
            # Keep the summary JSON-safe and compact.
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[f] = v
            else:
                out[f] = str(v)
    return out


async def resolve_actor(
    db,
    actor_user_id: str,
    request: Any = None,
) -> dict:
    """
    Determine WHO actually performed the delete and WHETHER they were
    impersonating someone.

    The backend mints a plain access token for the impersonated user, so the
    admin identity is not in the JWT. It is recovered from the
    admin_audit_log row written when the impersonation started
    (routers/admin.py impersonate_user) — the most recent impersonate_user
    row whose target_user_id is the actor, with no matching exit row.

    Returns {"performed_by": "self"|"impersonated", "impersonated_by_admin_id": str|None}
    """
    performed_by = "self"
    admin_id = None

    try:
        # An explicit header set by the admin console wins if present.
        if request is not None:
            try:
                hdr_admin = request.headers.get("X-Admin-User-Id")
            except Exception:  # noqa: BLE001
                hdr_admin = None
            if hdr_admin:
                performed_by = "impersonated"
                admin_id = hdr_admin
        if admin_id is None:
            impersonation = await db.admin_audit_log.find_one(
                {
                    "action": "impersonate_user",
                    "target_user_id": actor_user_id,
                },
                {"_id": 0, "admin_user_id": 1, "timestamp": 1},
                sort=[("timestamp", -1)],
            )
            if impersonation and impersonation.get("admin_user_id"):
                performed_by = "impersonated"
                admin_id = impersonation["admin_user_id"]
    except Exception as e:  # noqa: BLE001 — attribution lookup is best-effort
        logger.warning(
            "DELETE_AUDIT_ATTRIBUTION_LOOKUP_FAILED | actor=%s error=%s",
            actor_user_id, e,
        )

    return {
        "performed_by": performed_by,
        "impersonated_by_admin_id": admin_id,
    }


async def audit_member_deletion(
    db,
    actor_user_id: str,
    record_type: str,
    record_id: str,
    record: Optional[dict] = None,
    trust_id: str = "",
    request: Any = None,
    action: str = "delete",
    extra: Optional[dict] = None,
) -> dict:
    """
    Write the audit_logs row for a member-record deletion.

    The caller MUST invoke this BEFORE the delete commits, so the trail
    exists even if the delete itself later fails. A failure to write the
    audit row RAISES — an unaudited delete must not proceed silently.

    Returns the audit document that was written.
    """
    attribution = await resolve_actor(db, actor_user_id, request=request)
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        # House-style id (uuid) — the audit_logs.audit_id index is UNIQUE
        # (server.py), so a timestamp-derived id risks a DuplicateKeyError
        # that would abort an otherwise-valid delete.
        "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
        "user_id": actor_user_id,           # whose record it was (audit_logs user_id convention)
        "actor_user_id": actor_user_id,     # explicit per spec
        "performed_by": attribution["performed_by"],
        "record_type": record_type,
        "record_id": record_id,
        "action": action,
        "entity_type": record_type,
        "entity_id": record_id,
        "trust_id": trust_id or (record or {}).get("trust_id", ""),
        "deleted_at": now,
        "snapshot_summary": build_snapshot(record, record_type),
        "details": {
            "performed_by": attribution["performed_by"],
            "impersonated_by_admin_id": attribution["impersonated_by_admin_id"],
            "record_type": record_type,
            "record_id": record_id,
            "deleted_at": now,
            "snapshot_summary": build_snapshot(record, record_type),
            **(extra or {}),
        },
        "timestamp": now,
        "ip_address": None,
    }
    if attribution["impersonated_by_admin_id"]:
        doc["impersonated_by_admin_id"] = attribution["impersonated_by_admin_id"]
        doc["details"]["impersonated_by_admin_id"] = attribution["impersonated_by_admin_id"]

    await db.audit_logs.insert_one(doc)
    logger.info(
        "DELETE_AUDIT | actor=%s performed_by=%s admin=%s type=%s id=%s",
        actor_user_id, attribution["performed_by"],
        attribution["impersonated_by_admin_id"] or "-", record_type, record_id,
    )
    return doc
