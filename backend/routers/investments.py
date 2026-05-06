# Investment tracking router — durable wealth / investment holdings
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user

router = APIRouter(tags=["investments"])


@router.post("/trusts/{trust_id}/investments")
async def create_investment(trust_id: str, investment: dict, user: dict = Depends(get_current_user)):
    """Record a new investment holding for this trust."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    doc = {
        "investment_id": f"inv_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "asset_name": investment["asset_name"],
        "asset_type": investment.get("asset_type", "other"),  # stock, bond, reit, crypto, real_estate, other
        "purchase_date": investment.get("purchase_date"),
        "cost_basis": float(investment.get("cost_basis", 0)),
        "current_value": float(investment.get("current_value", 0)),
        "quantity": float(investment.get("quantity", 1)),
        "unit": investment.get("unit", "shares"),  # shares, units, sqft, coins
        "custodian": investment.get("custodian"),   # Fidelity, Schwab, etc.
        "account_number_mask": investment.get("account_number_mask"),  # last 4 digits
        "notes": investment.get("notes"),
        "documents": [],  # list of vault document IDs
        "performance_snapshot": investment.get("performance_snapshot"),  # dict with total_return, ytd_return, etc
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.investments.insert_one(doc)
    return {"investment_id": doc["investment_id"], "message": "Investment recorded"}


@router.get("/trusts/{trust_id}/investments")
async def list_investments(trust_id: str, user: dict = Depends(get_current_user)):
    """List all investments for a trust."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    docs = await db.investments.find(
        {"trust_id": trust_id, "is_active": True},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    total_cost = sum(d.get("cost_basis", 0) for d in docs)
    total_value = sum(d.get("current_value", 0) for d in docs)
    total_return = total_value - total_cost
    total_return_pct = (total_return / total_cost * 100) if total_cost > 0 else 0

    return {
        "trust_id": trust_id,
        "investments": docs,
        "count": len(docs),
        "total_cost_basis": round(total_cost, 2),
        "total_current_value": round(total_value, 2),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
    }


@router.patch("/investments/{investment_id}")
async def update_investment(investment_id: str, update: dict, user: dict = Depends(get_current_user)):
    """Update an investment (new valuation, notes, mark inactive)."""
    inv = await db.investments.find_one({"investment_id": investment_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Investment not found")

    trust = await db.trusts.find_one({"trust_id": inv["trust_id"], "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    update_data = {k: v for k, v in update.items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.investments.update_one({"investment_id": investment_id}, {"$set": update_data})
    return {"message": "Investment updated"}


@router.get("/trusts/{trust_id}/investments/summary")
async def investment_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """High-level summary for dashboard widget."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    by_type = []
    pipeline = [
        {"$match": {"trust_id": trust_id, "is_active": True}},
        {"$group": {"_id": "$asset_type", "count": {"$sum": 1}, "value": {"$sum": "$current_value"}}}
    ]
    async for doc in db.investments.aggregate(pipeline):
        by_type.append({"asset_type": doc["_id"], "count": doc["count"], "value": round(doc["value"], 2)})

    total = sum(t["value"] for t in by_type)
    for t in by_type:
        t["pct"] = round(t["value"] / total * 100, 1) if total > 0 else 0

    return {"trust_id": trust_id, "by_type": by_type, "total_value": round(total, 2)}
