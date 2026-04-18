# Alert detection service — rule-based commingling detection engine
# Runs on transaction create/update to surface separation risk patterns
import uuid
import logging
from datetime import datetime, timezone, timedelta
from database import db

logger = logging.getLogger(__name__)

ALERT_RULES = {
    "personal_vendor": {
        "severity": "red",
        "title": "Trust Paid Personal Vendor",
        "description_template": "Transaction of ${amount} from {entity_name} classified as '{classification}' but payee '{destination}' matches a known personal vendor."
    },
    "trust_paying_personal": {
        "severity": "red",
        "title": "Trust Paying Personal Obligation",
        "description_template": "Outflow of ${amount} from {entity_name} to personal account '{destination}' is not classified as Distribution or Compensation."
    },
    "large_unexplained": {
        "severity": "yellow",
        "title": "Large Unexplained Transfer",
        "description_template": "Outflow of ${amount} from {entity_name} classified as 'Other' with no memo or supporting document."
    },
    "round_number_recurring": {
        "severity": "yellow",
        "title": "Round-Number Recurring Payment",
        "description_template": "Recurring ${amount} transfers from {entity_name} detected ({count} occurrences) — not linked to a Compensation Resolution."
    },
    "same_day_reversal": {
        "severity": "yellow",
        "title": "Same-Day Cross-Entity Reversal",
        "description_template": "Money moved from {entity_name} to {destination} and back on {date} — may indicate sham transaction."
    },
    "unclassified_aging": {
        "severity": "yellow",
        "title": "Unclassified Transaction Aging",
        "description_template": "Transaction of ${amount} in {entity_name} has been classified as 'Other' for over 7 days without a memo."
    },
    "unlinked_governance": {
        "severity": "yellow",
        "title": "Transfer Without Linked Governance Action",
        "description_template": "{classification} of ${amount} in {entity_name} is not linked to a {expected_link}."
    }
}

# Default thresholds
LARGE_TRANSFER_THRESHOLD = 5000.0
PERSONAL_KEYWORDS = ["personal", "individual", "private", "self"]
AGING_DAYS = 7


async def _create_alert(trust_id, entity_id, transaction_id, alert_type, user_id, format_args):
    """Create an alert if one doesn't already exist for this transaction + type"""
    existing = await db.separation_alerts.find_one({
        "transaction_id": transaction_id,
        "alert_type": alert_type,
        "status": "active"
    })
    if existing:
        return None  # Don't duplicate

    rule = ALERT_RULES[alert_type]
    alert_id = f"alert_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    description = rule["description_template"].format(**format_args)

    doc = {
        "alert_id": alert_id,
        "trust_id": trust_id,
        "entity_id": entity_id,
        "transaction_id": transaction_id,
        "user_id": user_id,
        "alert_type": alert_type,
        "severity": rule["severity"],
        "title": rule["title"],
        "description": description,
        "status": "active",
        "resolution_type": None,
        "resolution_note": None,
        "resolved_at": None,
        "created_at": now
    }

    await db.separation_alerts.insert_one(doc)
    logger.info(f"Alert created: {alert_type} for txn {transaction_id}")
    return alert_id


async def check_transaction_alerts(txn_doc: dict):
    """Run all alert rules against a single transaction. Called after create/update."""
    trust_id = txn_doc["trust_id"]
    entity_id = txn_doc["entity_id"]
    txn_id = txn_doc["transaction_id"]
    user_id = txn_doc["user_id"]

    # Fetch entity name
    entity = await db.entities.find_one({"entity_id": entity_id}, {"_id": 0, "name": 1, "entity_type": 1})
    entity_name = entity.get("name", "Unknown") if entity else "Unknown"

    direction = txn_doc.get("direction", "")
    classification = txn_doc.get("governance_classification", "")
    amount = txn_doc.get("amount", 0)
    destination = txn_doc.get("destination_account", "")
    source = txn_doc.get("source_account", "")
    memo = txn_doc.get("purpose_memo", "")
    doc_name = txn_doc.get("document_name")
    date = txn_doc.get("date", "")

    fmt = {
        "amount": f"{amount:,.2f}",
        "entity_name": entity_name,
        "classification": classification,
        "destination": destination,
        "source": source,
        "date": date,
    }

    # ---- Rule 1: Trust paying personal obligation ----
    # Outflow from trust entity to personal account, NOT classified as Distribution or Compensation
    if direction == "outflow" and classification not in ("Distribution", "Compensation"):
        dest_lower = destination.lower()
        if any(kw in dest_lower for kw in PERSONAL_KEYWORDS):
            await _create_alert(trust_id, entity_id, txn_id, "trust_paying_personal", user_id, fmt)

    # ---- Rule 2: Personal vendor paid by trust ----
    # Check against user's personal vendors list
    if direction == "outflow" and classification == "Operational Expense":
        personal_vendors = await db.personal_vendors.find(
            {"user_id": user_id},
            {"_id": 0, "vendor_name": 1}
        ).to_list(200)
        vendor_names = [v["vendor_name"].lower() for v in personal_vendors]
        if any(vn in dest_lower for vn in vendor_names if vn):
            fmt["destination"] = destination
            await _create_alert(trust_id, entity_id, txn_id, "personal_vendor", user_id, fmt)

    # ---- Rule 3: Large unexplained transfer ----
    if direction == "outflow" and classification == "Other" and amount >= LARGE_TRANSFER_THRESHOLD:
        if not memo.strip() and not doc_name:
            await _create_alert(trust_id, entity_id, txn_id, "large_unexplained", user_id, fmt)

    # ---- Rule 4: Unlinked governance action ----
    if classification == "Distribution" and not txn_doc.get("linked_distribution_id"):
        fmt["expected_link"] = "Distribution Authorization"
        await _create_alert(trust_id, entity_id, txn_id, "unlinked_governance", user_id, fmt)

    if classification == "Compensation" and not txn_doc.get("linked_compensation_payment_id"):
        fmt["expected_link"] = "Compensation Resolution"
        await _create_alert(trust_id, entity_id, txn_id, "unlinked_governance", user_id, fmt)


async def run_pattern_alerts(trust_id: str, user_id: str):
    """Run cross-transaction pattern detection. Called periodically or on-demand."""
    now = datetime.now(timezone.utc)

    # Fetch all active transactions for this trust
    txns = await db.transactions.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).to_list(10000)

    if not txns:
        return

    # Entity name lookup
    entity_ids = list(set(t["entity_id"] for t in txns))
    entities = await db.entities.find(
        {"entity_id": {"$in": entity_ids}},
        {"_id": 0, "entity_id": 1, "name": 1}
    ).to_list(100)
    entity_map = {e["entity_id"]: e["name"] for e in entities}

    # ---- Rule 5: Round-number recurring payments ----
    from collections import Counter
    outflows = [t for t in txns if t["direction"] == "outflow" and not t.get("linked_compensation_payment_id")]
    amount_counts = Counter()
    amount_txns = {}
    for t in outflows:
        amt = t["amount"]
        if amt == round(amt) and amt >= 100:  # Round number, at least $100
            key = (t["entity_id"], amt)
            amount_counts[key] += 1
            amount_txns.setdefault(key, []).append(t)

    for (eid, amt), count in amount_counts.items():
        if count >= 3:  # 3+ recurring same-amount = flag
            # Alert on the most recent one
            recent_txn = sorted(amount_txns[(eid, amt)], key=lambda x: x["date"], reverse=True)[0]
            fmt = {
                "amount": f"{amt:,.2f}",
                "entity_name": entity_map.get(eid, "Unknown"),
                "count": count
            }
            await _create_alert(trust_id, eid, recent_txn["transaction_id"], "round_number_recurring", user_id, fmt)

    # ---- Rule 6: Same-day cross-entity reversals ----
    by_date = {}
    for t in txns:
        by_date.setdefault(t["date"], []).append(t)

    for date_key, day_txns in by_date.items():
        if len(day_txns) < 2:
            continue
        # Check for A→B and B→A on same day
        for i, t1 in enumerate(day_txns):
            for t2 in day_txns[i+1:]:
                if (t1["entity_id"] != t2["entity_id"] and
                    t1["direction"] != t2["direction"] and
                    abs(t1["amount"] - t2["amount"]) < 1.0):  # Same amount (within $1)
                    fmt = {
                        "entity_name": entity_map.get(t1["entity_id"], "Unknown"),
                        "destination": entity_map.get(t2["entity_id"], "Unknown"),
                        "date": date_key,
                        "amount": f"{t1['amount']:,.2f}"
                    }
                    await _create_alert(trust_id, t1["entity_id"], t1["transaction_id"], "same_day_reversal", user_id, fmt)

    # ---- Rule 7: Unclassified aging (>7 days) ----
    cutoff = (now - timedelta(days=AGING_DAYS)).isoformat()
    aging = [t for t in txns if t.get("governance_classification") == "Other"
             and not t.get("purpose_memo", "").strip()
             and t.get("created_at", "") < cutoff]

    for t in aging:
        fmt = {
            "amount": f"{t['amount']:,.2f}",
            "entity_name": entity_map.get(t["entity_id"], "Unknown"),
        }
        await _create_alert(trust_id, t["entity_id"], t["transaction_id"], "unclassified_aging", user_id, fmt)


async def auto_resolve_alert_if_fixed(txn_doc: dict):
    """Auto-resolve certain alerts when the underlying issue is fixed"""
    txn_id = txn_doc["transaction_id"]
    now = datetime.now(timezone.utc).isoformat()

    # If transaction now has a governance link, resolve unlinked alerts
    if txn_doc.get("linked_distribution_id") or txn_doc.get("linked_compensation_payment_id"):
        await db.separation_alerts.update_many(
            {"transaction_id": txn_id, "alert_type": "unlinked_governance", "status": "active"},
            {"$set": {"status": "resolved", "resolution_type": "linked", "resolution_note": "Governance action linked", "resolved_at": now}}
        )

    # If "Other" classification now has a memo, resolve aging/unexplained alerts
    if txn_doc.get("governance_classification") != "Other":
        await db.separation_alerts.update_many(
            {"transaction_id": txn_id, "alert_type": {"$in": ["unclassified_aging", "large_unexplained"]}, "status": "active"},
            {"$set": {"status": "resolved", "resolution_type": "classified", "resolution_note": f"Reclassified to {txn_doc.get('governance_classification')}", "resolved_at": now}}
        )
    elif txn_doc.get("purpose_memo", "").strip():
        await db.separation_alerts.update_many(
            {"transaction_id": txn_id, "alert_type": "unclassified_aging", "status": "active"},
            {"$set": {"status": "resolved", "resolution_type": "classified", "resolution_note": "Memo added", "resolved_at": now}}
        )

    # If destination no longer has personal keywords, resolve trust_paying_personal
    dest = txn_doc.get("destination_account", "").lower()
    if not any(kw in dest for kw in PERSONAL_KEYWORDS):
        await db.separation_alerts.update_many(
            {"transaction_id": txn_id, "alert_type": "trust_paying_personal", "status": "active"},
            {"$set": {"status": "resolved", "resolution_type": "classified", "resolution_note": "Destination updated", "resolved_at": now}}
        )
