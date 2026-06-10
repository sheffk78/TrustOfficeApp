# Risk Dashboard router — aggregated exposure across all modules
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta, date
from collections import Counter

from database import db
from dependencies import get_current_user

router = APIRouter(tags=["risk_dashboard"])


@router.get("/trusts/{trust_id}/risk-dashboard")
async def get_risk_dashboard(trust_id: str, user: dict = Depends(get_current_user)):
    """Comprehensive risk analysis: tax, compliance, communications, investments, vault."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    risks = []
    today = date.today()

    # === TAX RISK ===
    tax_entries = await db.tax_calendar.find(
        {"trust_id": trust_id, "tax_year": today.year, "filing_status": "pending"},
        {"_id": 0}
    ).sort("due_date", 1).to_list(20)

    overdue_tax = []
    upcoming_tax = []
    for e in tax_entries:
        due = date.fromisoformat(e["due_date"])
        days = (due - today).days
        if days < 0:
            overdue_tax.append({
                "type": "tax_deadline",
                "severity": "high",
                "title": f"Overdue: {e['description']}",
                "detail": f"Was due {abs(days)} days ago ({e['due_date']})",
                "action": "File immediately or request extension",
                "module": "tax_calendar",
                "deeplink": "/tax-calendar",
            })
        elif days <= 30:
            upcoming_tax.append({
                "type": "tax_deadline",
                "severity": "medium" if days <= 14 else "low",
                "title": f"Upcoming: {e['description']}",
                "detail": f"Due in {days} days ({e['due_date']})",
                "action": "Prepare filing or engage accountant",
                "module": "tax_calendar",
                "deeplink": "/tax-calendar",
            })

    risks.extend(overdue_tax)
    risks.extend(upcoming_tax)

    # === STATE COMPLIANCE RISK ===
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
                        "severity": "high",
                        "title": f"Beneficiary notice not yet sent in {profile['state_name']}",
                        "detail": f"State requires notice within {profile.get('notice_timing_days', 'N/A')} days of trust events.",
                        "action": "Send formal notice to all beneficiaries and log in Communications",
                        "module": "state_compliance",
                        "deeplink": "/communications",
                    })
    else:
        risks.append({
            "type": "no_state",
            "severity": "medium",
            "title": "No state jurisdiction set for this trust",
            "detail": "Cannot determine compliance requirements (UTC adoption, notice rules, accounting frequency).",
            "action": "Go to Settings → Trust Profile and set the state",
            "module": "state_compliance",
            "deeplink": "/settings",
        })

    # === COMMUNICATION RISK ===
    pending_actions = await db.communications.count_documents({
        "trust_id": trust_id, "action_required": True, "action_completed": False
    })
    if pending_actions > 0:
        risks.append({
            "type": "pending_actions",
            "severity": "medium",
            "title": f"{pending_actions} uncompleted follow-up action(s) in communication log",
            "detail": "Trustee duties may be compromised by outstanding beneficiary requests.",
            "action": "Review Communication Log and complete pending actions",
            "module": "communications",
            "deeplink": "/communications",
        })

    # === DOCUMENT VAULT RISK ===
    vault_summary = None
    total_docs = await db.vault_documents.count_documents({"trust_id": trust_id})
    critical_cats = ["trust_instrument", "schedule_a", "minutes", "tax_return"]
    present_cats = set()
    async for doc in db.vault_documents.find({"trust_id": trust_id}):
        present_cats.add(doc.get("category", "other"))

    missing_critical = [c for c in critical_cats if c not in present_cats]
    for m in missing_critical:
        labels = {
            "trust_instrument": "Trust Instrument",
            "schedule_a": "Schedule A (Assets)",
            "minutes": "Meeting Minutes",
            "tax_return": "Tax Return",
        }
        risks.append({
            "type": "missing_document",
            "severity": "medium",
            "title": f"{labels.get(m, m)} not found in Document Vault",
            "detail": "Critical governance documents should be organized and accessible.",
            "action": "Add document reference to the Trust Document Vault",
            "module": "vault",
            "deeplink": "/vault",
        })

    # === PORTFOLIO CONCENTRATION RISK (cash-heavy / uninvested assets) ===
    total_investments = await db.investments.count_documents({"trust_id": trust_id, "is_active": True})
    schedule_a_items = await db.schedule_a_items.find(
        {"trust_id": trust_id, "status": "active"},
        {"_id": 0, "category": 1, "approximate_value": 1}
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

    # === SEPARATION ALERTS (existing) ===
    alert_count = await db.alerts.count_documents({"trust_id": trust_id, "status": "active"})
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

    # === SCORE ===
    high = sum(1 for r in risks if r["severity"] == "high")
    medium = sum(1 for r in risks if r["severity"] == "medium")
    low = sum(1 for r in risks if r["severity"] == "low")

    # Overall assessment
    if high > 0:
        assessment = "critical"
        assessment_label = "Critical Attention Required"
    elif medium > 0:
        assessment = "elevated"
        assessment_label = "Elevated Risk"
    elif len(risks) > 0:
        assessment = "caution"
        assessment_label = "Caution Areas"
    else:
        assessment = "healthy"
        assessment_label = "Low Risk"

    # Group by module
    by_module = {}
    for r in risks:
        mod = r["module"]
        if mod not in by_module:
            by_module[mod] = []
        by_module[mod].append(r)

    return {
        "trust_id": trust_id,
        "trust_name": trust.get("name"),
        "assessment": assessment,
        "assessment_label": assessment_label,
        "risk_count": len(risks),
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
        "risks": risks,
        "by_module": by_module,
    }
