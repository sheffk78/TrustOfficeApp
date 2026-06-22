# Exports router - handles CSV exports of trust data (Premium feature)
from fastapi import APIRouter, Depends, Response
from datetime import datetime, timezone
from typing import Optional

from database import db
from dependencies import get_current_user, require_premium_feature, Feature, get_task_status

router = APIRouter(tags=["exports"])


# ==================== CSV EXPORT ENDPOINTS (Premium Feature) ====================

@router.get("/export/minutes")
async def export_minutes_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export minutes records as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    minutes = await db.minutes_records.find(query, {"_id": 0}).sort("meeting_date", -1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(m["trust_id"] for m in minutes))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Minutes Type,Meeting Date,Participants,Decisions,Created At"]
    for m in minutes:
        trust_name = trust_map.get(m["trust_id"], "Unknown").replace(",", ";")
        minutes_type = m.get("minutes_type", "").replace("_", " ").title()
        meeting_date = m.get("meeting_date", "")[:10]
        participants = m.get("participants_text", "").replace(",", ";").replace("\n", " ")[:200]
        decisions = m.get("decisions_text", "").replace(",", ";").replace("\n", " ")[:500]
        created_at = m.get("created_at", "")[:10]
        
        csv_lines.append(f'"{trust_name}","{minutes_type}","{meeting_date}","{participants}","{decisions}","{created_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=minutes_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/distributions")
async def export_distributions_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export distribution records as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    dists = await db.distribution_records.find(query, {"_id": 0}).sort("date", -1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(d["trust_id"] for d in dists))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Beneficiary,Amount,Date,Category,Authority Reference,Notes,Status,Approved By,Approved At"]
    for d in dists:
        trust_name = trust_map.get(d["trust_id"], "Unknown").replace(",", ";")
        beneficiary = d.get("beneficiary_name", "").replace(",", ";")
        amount = d.get("amount", 0)
        date = d.get("date", "")[:10]
        category = d.get("purpose_classification", "").replace("_", " ").title()
        authority = d.get("authority_clause_ref", "").replace(",", ";")[:100]
        notes = d.get("notes", "").replace(",", ";").replace("\n", " ")[:200]
        status = "Approved" if d.get("approved_at") else "Pending"
        approved_by = d.get("approved_by", "") or ""
        approved_at = (d.get("approved_at", "") or "")[:10]
        
        csv_lines.append(f'"{trust_name}","{beneficiary}",{amount},"{date}","{category}","{authority}","{notes}","{status}","{approved_by}","{approved_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=distributions_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/compensation")
async def export_compensation_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export compensation payments as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    payments = await db.compensation_payments.find(query, {"_id": 0}).sort("date", -1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(p["trust_id"] for p in payments))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Amount,Date,Classification,Exceeds Plan,Created At"]
    for p in payments:
        trust_name = trust_map.get(p["trust_id"], "Unknown").replace(",", ";")
        amount = p.get("amount", 0)
        date = p.get("date", "")[:10]
        classification = p.get("classification_text", "").replace(",", ";")[:200]
        exceeds = "Yes" if p.get("exceeds_plan_flag") else "No"
        created_at = p.get("created_at", "")[:10]
        
        csv_lines.append(f'"{trust_name}",{amount},"{date}","{classification}","{exceeds}","{created_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=compensation_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/tasks")
async def export_tasks_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export governance tasks as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    tasks = await db.governance_tasks.find(query, {"_id": 0}).sort("due_date", 1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(t["trust_id"] for t in tasks))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Task Type,Due Date,Description,Status,Completed At"]
    for t in tasks:
        trust_name = trust_map.get(t["trust_id"], "Unknown").replace(",", ";")
        task_type = t.get("task_type", "").replace("_", " ").title()
        due_date = t.get("due_date", "")[:10]
        description = t.get("description", "").replace(",", ";").replace("\n", " ")[:200]
        status = get_task_status(t.get("due_date", ""), t.get("completed_at"))
        completed_at = (t.get("completed_at", "") or "")[:10]
        
        csv_lines.append(f'"{trust_name}","{task_type}","{due_date}","{description}","{status}","{completed_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tasks_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/expenses")
async def export_expenses_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export expense records as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(e["trust_id"] for e in expenses)) if expenses else []
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100) if trust_ids else []
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Date,Payee,Category,Amount,Status,Notes"]
    for e in expenses:
        trust_name = trust_map.get(e["trust_id"], "Unknown").replace(",", ";")
        date = e.get("date", "")[:10]
        payee = e.get("payee", "").replace(",", ";")
        category = e.get("category", "").replace(",", ";")
        amount = e.get("amount", 0)
        status = e.get("status", "")
        notes = e.get("notes", "").replace(",", ";").replace("\n", " ")[:200] if e.get("notes") else ""
        
        csv_lines.append(f'"{trust_name}","{date}","{payee}","{category}",{amount},"{status}","{notes}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=expenses_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )
