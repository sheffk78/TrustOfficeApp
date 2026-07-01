"""
Shared risk gathering service — single source of truth for risk detection.
Both risk_dashboard.py and governance.py call this function.
"""
from datetime import date, datetime, timezone, timedelta
from typing import List


async def gather_risk_findings(
    trust_id: str,
    trust: dict,
    db,
    today: date,
    include_separation_alerts: bool = True,
) -> List[dict]:
    """
    Gather raw risk findings across all risk modules.
    Single source of truth for risk detection.

    Args:
        include_separation_alerts: True for Risk Dashboard display,
                                    False for health score penalty (avoids double-counting).
    Returns: list of {type, severity, module, title, detail, action, deeplink}
    """
    risks: List[dict] = []

    # === TAX RISK (with severity graduation) ===
    tax_entries = await db.tax_calendar.find(
        {"trust_id": trust_id, "tax_year": today.year, "filing_status": "pending"},
        {"_id": 0},
    ).sort("due_date", 1).to_list(20)

    for e in tax_entries:
        due = date.fromisoformat(e["due_date"])
        days = (due - today).days
        if days < 0:
            abs_days = abs(days)
            if abs_days > 30:
                severity = "critical"
            else:
                severity = "high"
            risks.append({
                "type": "tax_deadline",
                "severity": severity,
                "title": f"Overdue: {e['description']}",
                "detail": f"Was due {abs_days} days ago ({e['due_date']})",
                "action": "File immediately or request extension",
                "module": "tax_calendar",
                "deeplink": "/tax-calendar",
            })
        elif days <= 14:
            risks.append({
                "type": "tax_deadline",
                "severity": "medium",
                "title": f"Upcoming: {e['description']}",
                "detail": f"Due in {days} days ({e['due_date']})",
                "action": "Prepare filing or engage accountant",
                "module": "tax_calendar",
                "deeplink": "/tax-calendar",
            })
        elif days <= 30:
            risks.append({
                "type": "tax_deadline",
                "severity": "low",
                "title": f"Upcoming: {e['description']}",
                "detail": f"Due in {days} days ({e['due_date']})",
                "action": "Prepare filing or engage accountant",
                "module": "tax_calendar",
                "deeplink": "/tax-calendar",
            })

    # === STATE COMPLIANCE RISK (with severity graduation) ===
    state_code = trust.get("state_code")
    if state_code:
        profile = await db.state_compliance_profiles.find_one(
            {"_id": state_code.upper()}, {"_id": 0}
        )
        if profile:
            if profile.get("utc_adopted") == "no":
                risks.append({
                    "type": "utc_gap",
                    "severity": "medium",
                    "title": f"{profile['state_name']} has not adopted the UTC",
                    "detail": "Legacy common-law rules may expose trust to court action on trustee removal.",
                    "action": "Review trust instrument for explicit trustee removal language",
                    "module": "state_compliance",
                    "deeplink": "/state-compliance",
                })
            if profile.get("notice_required"):
                compliance = await db.trust_state_compliance.find_one(
                    {"trust_id": trust_id, "state_code": state_code.upper()}, {"_id": 0}
                )
                if compliance and not compliance.get("notice_last_sent"):
                    risks.append({
                        "type": "notice_required",
                        "severity": "critical",
                        "title": f"Beneficiary notice not yet sent in {profile['state_name']}",
                        "detail": f"State requires notice within {profile.get('notice_timing_days', 'N/A')} days of trust events.",
                        "action": "Send formal notice to all beneficiaries and log in Communications",
                        "module": "state_compliance",
                        "deeplink": "/communications",
                    })
    else:
        risks.append({
            "type": "no_state",
            "severity": "high",
            "title": "No state jurisdiction set for this trust",
            "detail": "Cannot determine compliance requirements (UTC adoption, notice rules, accounting frequency).",
            "action": "Go to Settings → Trust Profile and set the state",
            "module": "state_compliance",
            "deeplink": "/settings",
        })

    # === COMMUNICATION RISK (with severity graduation) ===
    pending_comms = await db.communications.find(
        {"trust_id": trust_id, "action_required": True, "action_completed": False},
        {"_id": 0, "created_at": 1},
    ).to_list(100)

    pending_count = len(pending_comms)
    if pending_count > 0:
        oldest_days = 0
        now = datetime.now(timezone.utc)
        for c in pending_comms:
            created = c.get("created_at", "")
            if created:
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if "T" in created else datetime.fromisoformat(created).replace(tzinfo=timezone.utc)
                    age = (now - created_dt).days
                    if age > oldest_days:
                        oldest_days = age
                except (ValueError, TypeError):
                    pass

        if oldest_days > 30:
            comm_severity = "medium"
        else:
            comm_severity = "low"

        risks.append({
            "type": "pending_actions",
            "severity": comm_severity,
            "title": f"{pending_count} uncompleted follow-up action(s) in communication log",
            "detail": "Trustee duties may be compromised by outstanding beneficiary requests.",
            "action": "Review Communication Log and complete pending actions",
            "module": "communications",
            "deeplink": "/communications",
        })

    # === DOCUMENT VAULT RISK (with severity graduation) ===
    critical_cats = ["trust_instrument", "schedule_a", "minutes", "tax_return"]
    present_cats = set()
    async for doc in db.vault_documents.find({"trust_id": trust_id}):
        present_cats.add(doc.get("category", "other"))

    vault_severity_map = {
        "trust_instrument": "medium",
        "schedule_a": "low",
        "minutes": "low",
        "tax_return": "medium",
    }
    vault_labels = {
        "trust_instrument": "Trust Instrument",
        "schedule_a": "Schedule A (Assets)",
        "minutes": "Meeting Minutes",
        "tax_return": "Tax Return",
    }
    missing_critical = [c for c in critical_cats if c not in present_cats]
    for m in missing_critical:
        risks.append({
            "type": "missing_document",
            "severity": vault_severity_map.get(m, "medium"),
            "title": f"{vault_labels.get(m, m)} not found in Document Vault",
            "detail": "Critical governance documents should be organized and accessible.",
            "action": "Add document reference to the Trust Document Vault",
            "module": "vault",
            "deeplink": "/vault",
        })

    # === PORTFOLIO CONCENTRATION RISK (with severity graduation) ===
    total_investments = await db.investments.count_documents({"trust_id": trust_id, "is_active": True})
    schedule_a_items = await db.schedule_a_items.find(
        {"trust_id": trust_id, "status": "active"},
        {"_id": 0, "category": 1, "approximate_value": 1},
    ).to_list(1000)

    # Rule A: Trust has assets on Schedule A but zero investments recorded
    if total_investments == 0 and len(schedule_a_items) > 0:
        total_schedule_a_value = sum(item.get("approximate_value", 0) or 0 for item in schedule_a_items)
        if total_schedule_a_value > 0:
            risks.append({
                "type": "uninvested_assets",
                "severity": "high",
                "title": "Trust assets may be uninvested",
                "detail": f"No investment holdings tracked. Schedule A shows ${total_schedule_a_value:,.0f} in assets — review for idle cash exposure under the Prudent Investor Rule.",
                "action": "Add investment holdings or document why assets are held in cash",
                "module": "investments",
                "deeplink": "/investments",
            })

    # Rule B: Cash-heavy portfolio — financial accounts > 60% of total tracked investments
    if total_investments > 0:
        cash_items = [i for i in schedule_a_items if i.get("category") == "financial_accounts"]
        cash_value = sum(item.get("approximate_value", 0) or 0 for item in cash_items)
        total_invested = 0
        async for inv in db.investments.find({"trust_id": trust_id, "is_active": True}):
            total_invested += inv.get("current_value", 0) or 0

        if cash_value > 0 and total_invested > 0 and (cash_value / (cash_value + total_invested)) > 0.6:
            cash_pct = (cash_value / (cash_value + total_invested)) * 100
            risks.append({
                "type": "cash_heavy_portfolio",
                "severity": "medium",
                "title": f"Portfolio may be cash-heavy ({cash_pct:.0f}% in financial accounts)",
                "detail": f"${cash_value:,.0f} in financial accounts vs ${total_invested:,.0f} invested. Cash-heavy portfolios may breach the Prudent Investor Rule.",
                "action": "Evaluate allocation and rebalance or document investment rationale",
                "module": "investments",
                "deeplink": "/investments",
            })

    # === INVESTMENT DECLINE RISK ===
    async for inv in db.investments.find({"trust_id": trust_id, "is_active": True}):
        if inv.get("current_value", 0) < inv.get("cost_basis", 0) * 0.8:
            pct = (1 - (inv["current_value"] / inv["cost_basis"])) * 100 if inv["cost_basis"] > 0 else 0
            risks.append({
                "type": "investment_decline",
                "severity": "medium",
                "title": f"{inv['asset_name']} down {pct:.0f}% from cost basis",
                "detail": f"Current value ${inv['current_value']:,.2f} vs cost ${inv['cost_basis']:,.2f}",
                "action": "Review investment thesis and consider rebalancing",
                "module": "investments",
                "deeplink": "/investments",
            })

    # === SEPARATION ALERTS (optionally excluded for score penalty) ===
    if include_separation_alerts:
        alert_count = await db.separation_alerts.count_documents({"trust_id": trust_id, "status": "active"})
        if alert_count > 0:
            risks.append({
                "type": "separation_alert",
                "severity": "high",
                "title": f"{alert_count} active separation alert(s)",
                "detail": "Potential commingling or self-dealing detected. Immediate review required.",
                "action": "Review alerts and classify/document transactions",
                "module": "alerts",
                "deeplink": "/alerts",
            })

    # === EIN / TAX PROFILE ===
    if not trust.get("ein"):
        risks.append({
            "type": "no_ein",
            "severity": "low",
            "title": "Trust EIN not recorded",
            "detail": "Cannot generate accurate tax calendar reminders or track filings.",
            "action": "Add EIN in Trust Profile → Settings",
            "module": "tax_calendar",
            "deeplink": "/settings",
        })

    return risks


# Penalty constants
PENALTY_PER_FINDING = {
    "critical": 20,
    "high": 12,
    "medium": 5,
    "low": 2,
}

PENALTY_CAP = {
    "high": 25,
    "medium": 15,
    "low": 10,
    # critical: no cap (hard floor applies instead)
}


def compute_risk_penalty(findings: List[dict]) -> dict:
    """
    Compute total risk penalty from findings.
    Separation alerts should already be filtered out before calling this.

    Returns:
        {
            "total_penalty": int (negative),
            "has_critical": bool,
            "breakdown": {
                "critical": {"count": int, "penalty": int (negative)},
                "high": {"count": int, "penalty": int (negative)},
                "medium": {"count": int, "penalty": int (negative)},
                "low": {"count": int, "penalty": int (negative)},
            },
            "findings_with_penalty": list of findings with penalty field added,
        }
    """
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for r in findings:
        sev = r.get("severity", "low")
        if sev in counts:
            counts[sev] += 1

    critical_penalty = counts["critical"] * PENALTY_PER_FINDING["critical"]
    high_penalty = min(counts["high"] * PENALTY_PER_FINDING["high"], PENALTY_CAP["high"])
    medium_penalty = min(counts["medium"] * PENALTY_PER_FINDING["medium"], PENALTY_CAP["medium"])
    low_penalty = min(counts["low"] * PENALTY_PER_FINDING["low"], PENALTY_CAP["low"])

    total_penalty = -(critical_penalty + high_penalty + medium_penalty + low_penalty)
    has_critical = counts["critical"] > 0

    # Add per-finding penalty for frontend display
    per_finding_penalty = {
        "critical": -PENALTY_PER_FINDING["critical"],
        "high": -PENALTY_PER_FINDING["high"],
        "medium": -PENALTY_PER_FINDING["medium"],
        "low": -PENALTY_PER_FINDING["low"],
    }
    findings_with_penalty = []
    for r in findings:
        r_copy = dict(r)
        r_copy["penalty"] = per_finding_penalty.get(r.get("severity", "low"), 0)
        findings_with_penalty.append(r_copy)

    return {
        "total_penalty": total_penalty,
        "has_critical": has_critical,
        "breakdown": {
            "critical": {"count": counts["critical"], "penalty": -critical_penalty},
            "high": {"count": counts["high"], "penalty": -high_penalty},
            "medium": {"count": counts["medium"], "penalty": -medium_penalty},
            "low": {"count": counts["low"], "penalty": -low_penalty},
        },
        "findings_with_penalty": findings_with_penalty,
    }