# Risk Dashboard router — aggregated exposure across all modules
# Uses shared gather_risk_findings() from services/risk_gathering.py
from fastapi import APIRouter, HTTPException, Depends
from datetime import date

from database import db
from dependencies import get_current_user
from services.risk_gathering import gather_risk_findings

router = APIRouter(tags=["risk_dashboard"])


@router.get("/trusts/{trust_id}/risk-dashboard")
async def get_risk_dashboard(trust_id: str, user: dict = Depends(get_current_user)):
    """Comprehensive risk analysis: tax, compliance, communications, investments, vault."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    today = date.today()

    # Use shared service — include separation alerts for dashboard display
    risks = await gather_risk_findings(
        trust_id, trust, db, today, include_separation_alerts=True
    )

    # === SCORE ===
    critical = sum(1 for r in risks if r["severity"] == "critical")
    high = sum(1 for r in risks if r["severity"] == "high")
    medium = sum(1 for r in risks if r["severity"] == "medium")
    low = sum(1 for r in risks if r["severity"] == "low")

    # Overall assessment (revised 4-tier with critical)
    if critical > 0:
        assessment = "critical"
        assessment_label = "Critical Attention Required"
    elif high > 0:
        assessment = "elevated"
        assessment_label = "Elevated Risk"
    elif medium > 0:
        assessment = "caution"
        assessment_label = "Caution Areas"
    elif len(risks) > 0:
        assessment = "caution"
        assessment_label = "Minor Caution"
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

    # === COMPLIANCE SUMMARY (for Risk Dashboard card) ===
    compliance_summary = None
    state_code = trust.get("state_code")
    if state_code:
        compliance = await db.trust_state_compliance.find_one(
            {"trust_id": trust_id, "state_code": state_code.upper()}, {"_id": 0}
        )
        if compliance:
            next_deadline = None
            for field in ['notice_next_due', 'accounting_next_due']:
                val = compliance.get(field)
                if val:
                    if not next_deadline or val < next_deadline:
                        next_deadline = val
            compliance_summary = {
                "score": compliance.get("compliance_score", 100),
                "alert_active": compliance.get("alert_active", False),
                "next_deadline": next_deadline,
            }
        else:
            # No compliance record yet — show defaults so the card always renders
            compliance_summary = {
                "score": 100,
                "alert_active": False,
                "next_deadline": None,
            }

    return {
        "trust_id": trust_id,
        "trust_name": trust.get("name"),
        "assessment": assessment,
        "assessment_label": assessment_label,
        "risk_count": len(risks),
        "critical_count": critical,
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
        "risks": risks,
        "by_module": by_module,
        "compliance_summary": compliance_summary,
    }