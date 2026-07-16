# Trust Health Score v2 — Revised Implementation Spec

**Date:** July 1, 2026
**Status:** Draft (post multi-agent review)
**Reviews:** Data Architecture, UX/Psychology, Fiduciary/Legal Domain

---

## Problem

The Trust Health Score (7 criteria, 100 pts) and the Risk Dashboard (8 risk modules) are disconnected. A trust can score 100/100 while the Risk Dashboard shows "Critical." The score measures record-keeping habits, not real governance risk. This is a credibility defect for a platform positioned as the premiere tool for trustees.

---

## Architecture: Composite Score Model

**Not negative-point criteria.** The score is composed of two independent layers, stored and returned as separate fields:

```
FINAL SCORE = apply_hard_floor(base_score + risk_penalty)

base_score: 0-100, from 7 criteria (additive, unchanged pattern)
risk_penalty: 0 to -50, from risk findings (deductive, separate field)
hard_floor: 50 if any critical-severity finding exists, else 0
```

### API Response Shape (revised)

```json
{
  "trust_id": "...",
  "total_score": 71,
  "max_score": 100,
  "color": "yellow",
  "base_score": 95,
  "risk_penalty": -24,
  "has_critical_risk": false,
  "criteria": [
    {"name": "Quarterly Minutes", "points": 15, "max_points": 15, "achieved": true, "description": "..."},
    {"name": "Task Compliance", "points": 15, "max_points": 15, "achieved": true, "description": "..."},
    ...
  ],
  "risk_findings": [
    {"severity": "high", "title": "Overdue tax filing", "module": "tax_calendar", "penalty": -12, "deeplink": "/tax-calendar"},
    {"severity": "medium", "title": "Missing trust instrument in vault", "module": "vault", "penalty": -5, "deeplink": "/vault"},
    ...
  ],
  "risk_penalty_breakdown": {
    "critical": {"count": 0, "penalty": 0},
    "high": {"count": 2, "penalty": -24},
    "medium": {"count": 0, "penalty": 0},
    "low": {"count": 0, "penalty": 0}
  },
  "calculated_at": "2026-07-01T..."
}
```

The `criteria` array stays 7 items, all positive points. `risk_findings` is a parallel array. The frontend renders them as separate sections.

---

## Penalty Tier System

### Severity Levels (revised from risk_dashboard.py)

The current 3-tier system (high/medium/low) becomes 4-tier with a new **critical** level:

| Severity | Per-Finding Penalty | Cap | Examples |
|----------|-------------------|-----|----------|
| **Critical** | -20 | hard floor at 50 | Overdue tax filings >30d, missing beneficiary notices (UTC §813), uninvested assets >180d |
| **High** | -12 | -25 | Overdue tax filings <30d, active separation alerts (excluded from penalty, see below), no state jurisdiction |
| **Medium** | -5 | -15 | Missing vault docs, cash-heavy portfolio >60%, pending communications, investment decline >20% |
| **Low** | -2 | -10 | Missing EIN |

### Hard Floor Logic

```python
if has_critical_finding:
    final_score = max(50, base_score + risk_penalty)
else:
    final_score = max(0, base_score + risk_penalty)
```

A trust with overdue tax filings (>30 days) cannot score above 50, regardless of how good the record-keeping is. This mirrors how fiduciary litigation works: a categorical breach overshadows procedural compliance.

### Double-Counting Resolution

**Separation Alerts stay in the base score only (criterion 7), excluded from risk penalties.**

The base score has more graduated logic for separation alerts (tiered by red/yellow count). The Risk Dashboard still displays separation alerts for awareness, but they no longer generate a penalty. The `gather_risk_findings()` function filters them out when returning findings for scoring purposes.

---

## Base Score Rebalancing

Two criteria weights change per the legal review:

| Criterion | Current | Revised | Rationale |
|-----------|---------|---------|-----------|
| Quarterly Minutes | 15 | 15 | unchanged |
| Task Compliance | 15 | 15 | unchanged |
| Compensation Alignment | 15 | 15 | unchanged |
| Distribution Documentation | 15 | 15 | unchanged |
| Annual Review | 10 | **15** | Keystone defensibility event. Courts and auditors look for annual review first. |
| Transaction Classification | 15 | **10** | Bookkeeping function. Important but not a top liability driver. |
| Separation Alert Health | 15 | 15 | unchanged |
| **Total** | 100 | 100 | |

---

## Changes by File

### 1. NEW: `backend/services/risk_gathering.py`

Extract a shared service function so both `risk_dashboard.py` and `governance.py` call the same logic. Eliminates the duplication pattern that caused the background task divergence.

```python
async def gather_risk_findings(
    trust_id: str,
    trust: dict,
    db,
    today: date,
    include_separation_alerts: bool = True
) -> list[dict]:
    """
    Gather raw risk findings across all risk modules.
    Single source of truth for risk detection.
    
    Args:
        include_separation_alerts: True for Risk Dashboard display,
                                    False for health score penalty (avoids double-counting)
    
    Returns: list of {type, severity, module, title, detail, action, deeplink}
    """
```

Severity graduation logic (new):
- **Tax Calendar**: overdue >30 days → `critical`, overdue ≤30 days → `high`, due ≤14 days → `medium`, due ≤30 days → `low`
- **State Compliance**: missing beneficiary notice → `critical` (was high), no state jurisdiction → `high` (was medium), UTC adoption gap → `medium`
- **Investments**: uninvested assets >180 days → `critical`, uninvested ≤180 days → `high`, cash-heavy >60% → `medium`, decline >20% → `medium`
- **Communications**: pending >30 days → `medium`, pending ≤30 days → `low`
- **Vault**: missing trust instrument → `medium`, missing tax returns → `medium`, missing minutes → `low`
- **EIN**: missing → `low`

When `include_separation_alerts=False`, filter out separation alert findings from the returned list.

### 2. `backend/routers/risk_dashboard.py`

Refactor: the endpoint calls `gather_risk_findings(include_separation_alerts=True)` and wraps the result with presentation logic (assessment labels, counts, by_module grouping). No breaking change to the API response shape.

Add the new `critical` severity to the assessment mapping:
```python
# Revised: critical > 0 → "critical", high > 0 → "elevated", medium > 0 → "caution", else → "healthy"
```

### 3. `backend/routers/governance.py`

**A. Update `CRITERIA_CONFIG` weights:**

```python
# Annual Review: 10 → 15
"annual_review": {
    "name": "Annual Review",
    "max_points": 15,  # was 10
    ...
}

# Transaction Classification: 15 → 10
"transaction_classification": {
    "name": "Transaction Classification",
    "max_points": 10,  # was 15
    ...
}
```

**B. Extend `_gather_score_data()`:**

Add risk findings to the returned dict:

```python
# After existing data gathering...
risk_findings = await gather_risk_findings(
    trust_id, trust, db, today, include_separation_alerts=False
)

data["risk_findings"] = risk_findings
data["critical_count"] = sum(1 for r in risk_findings if r["severity"] == "critical")
data["high_count"] = sum(1 for r in risk_findings if r["severity"] == "high")
data["medium_count"] = sum(1 for r in risk_findings if r["severity"] == "medium")
data["low_count"] = sum(1 for r in risk_findings if r["severity"] == "low")
```

**C. Update `_compute_health_score()`:**

After computing the 7 criteria (base_score), compute risk penalty:

```python
# --- Risk Penalty (separate from criteria) ---
critical_count = data.get("critical_count", 0)
high_count = data.get("high_count", 0)
medium_count = data.get("medium_count", 0)
low_count = data.get("low_count", 0)

CRITICAL_PENALTY = 20
HIGH_PENALTY = 12
MEDIUM_PENALTY = 5
LOW_PENALTY = 2

HIGH_CAP = 25
MEDIUM_CAP = 15
LOW_CAP = 10

critical_penalty = critical_count * CRITICAL_PENALTY  # no cap, but hard floor applies
high_penalty = min(high_count * HIGH_PENALTY, HIGH_CAP)
medium_penalty = min(medium_count * MEDIUM_PENALTY, MEDIUM_CAP)
low_penalty = min(low_count * LOW_PENALTY, LOW_CAP)

total_penalty = -(critical_penalty + high_penalty + medium_penalty + low_penalty)

has_critical = critical_count > 0

# --- Final Score with Hard Floor ---
base_score = sum(c["points"] for c in criteria)  # 7 criteria, max 100
if has_critical:
    final_score = max(50, base_score + total_penalty)
else:
    final_score = max(0, base_score + total_penalty)

# Color from final_score (not base_score)
if final_score >= 80:
    color = "green"
elif final_score >= 60:
    color = "yellow"
else:
    color = "red"
```

**D. Updated return shape:**

```python
return {
    "criteria": criteria,          # 7 items, positive points only
    "base_score": base_score,      # NEW
    "risk_penalty": total_penalty, # NEW (negative number)
    "has_critical_risk": has_critical,  # NEW
    "total_score": final_score,
    "color": color,
    "risk_findings": data.get("risk_findings", []),  # NEW
    "risk_penalty_breakdown": {    # NEW
        "critical": {"count": critical_count, "penalty": -critical_penalty},
        "high": {"count": high_count, "penalty": -high_penalty},
        "medium": {"count": medium_count, "penalty": -medium_penalty},
        "low": {"count": low_count, "penalty": -low_penalty},
    }
}
```

**E. Update `calculate_health_score()` response:**

```python
response = {
    "trust_id": trust_id,
    "total_score": result["total_score"],
    "max_score": 100,
    "color": result["color"],
    "base_score": result["base_score"],
    "risk_penalty": result["risk_penalty"],
    "has_critical_risk": result["has_critical_risk"],
    "criteria": result["criteria"],
    "risk_findings": result["risk_findings"],
    "risk_penalty_breakdown": result["risk_penalty_breakdown"],
    "calculated_at": datetime.utcnow().isoformat()
}
```

**F. Performance: Cache risk findings.**

Add a simple TTL cache to avoid running 8+ DB queries on every dashboard load:

```python
# In _gather_score_data(), before gathering:
cached = await db.risk_findings_cache.find_one(
    {"trust_id": trust_id, "cached_at": {"$gte": datetime.utcnow() - timedelta(minutes=5)}}
)
if cached:
    risk_findings = cached["findings"]
else:
    risk_findings = await gather_risk_findings(...)
    await db.risk_findings_cache.update_one(
        {"trust_id": trust_id},
        {"$set": {"findings": risk_findings, "cached_at": datetime.utcnow()}},
        upsert=True
    )
```

For the `save_snapshot=True` path (governance endpoint, daily snapshots), always gather fresh. For `save_snapshot=False` (dashboard), use cache.

### 4. `backend/background_tasks.py`

**Delete `_calculate_health_score_internal()` entirely.** Replace with import from governance.py:

```python
# Remove lines 501-586 (the stale 5-criteria function)
# Replace with:
from routers.governance import calculate_health_score

async def _calculate_health_score_internal(trust_id, user_id):
    """Wrapper that calls the real scoring function."""
    db = await get_db()
    result = await calculate_health_score(trust_id, user_id, db, save_snapshot=True)
    return result
```

If circular import is a concern, use late import inside the function body.

**This is a prerequisite. Must ship in the same PR as the penalty layer.** Otherwise daily snapshots will use the stale 5-criteria logic while the live endpoint uses 7-criteria + penalties, and the history endpoint's date-deduplication will preserve the stale snapshot.

### 5. `backend/services/chat_service.py` (bug fix)

**Pre-existing bug:** Line ~306 projects `{total_score: 1, score_color: 1, criteria: 1}` from `health_score_snapshots`, but actual fields are `score_value` and `color`, and `criteria` is not stored. The AI assistant always gets `health_score = {total: 0, color: "red"}`.

Fix:
```python
# Before (broken):
projection = {"total_score": 1, "score_color": 1, "criteria": 1}

# After:
projection = {"score_value": 1, "color": 1, "base_score": 1, "risk_penalty": 1}
```

And update the field references downstream to use `score_value` and `color` instead of `total_score` and `score_color`.

### 6. Snapshot Schema Migration

**New snapshot document:**

```python
{
    "snapshot_id": "...",
    "trust_id": "...",
    "user_id": "...",
    "schema_version": 2,               # NEW
    "base_score": 82,                  # NEW
    "risk_penalty": -10,               # NEW
    "score_value": 72,                 # total = base + penalty (floored)
    "color": "yellow",
    "calculated_at": "...",
    "criteria_breakdown": [            # NEW — for audit/debugging
        {"name": "Quarterly Minutes", "points": 15, "max_points": 15, "achieved": true},
        ...
    ],
    "risk_findings_count": {           # NEW — lightweight summary
        "critical": 0, "high": 2, "medium": 1, "low": 0
    }
}
```

**One-time backfill migration script:**

```python
# For all existing snapshots without schema_version:
db.health_score_snapshots.update_many(
    {"schema_version": {"$exists": False}},
    {"$set": {
        "schema_version": 1,
        "base_score": "$score_value",  # pre-penalty, score_value IS base_score
        "risk_penalty": 0,
        "risk_findings_count": {"critical": 0, "high": 0, "medium": 0, "low": 0}
    }}
)
```

Note: MongoDB doesn't support referencing existing fields in `$set` with `$` syntax directly. Use a bulk write script that reads each document, computes the new fields, and updates. This is a one-time operation.

```python
async def backfill_snapshots(db):
    cursor = db.health_score_snapshots.find({"schema_version": {"$exists": False}})
    async for doc in cursor:
        await db.health_score_snapshots.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "schema_version": 1,
                "base_score": doc["score_value"],
                "risk_penalty": 0,
                "risk_findings_count": {"critical": 0, "high": 0, "medium": 0, "low": 0}
            }}
        )
```

### 7. `frontend/src/pages/GovernancePage.js`

**A. Score circle shows final score (`total_score`), not base.**

The circle already reads `governance.total_score`. No change needed there. The number will now reflect penalties.

**B. Add subtext below the score circle:**

```jsx
{governance.risk_penalty < 0 && (
  <div className="text-xs text-subtle-text mt-2 text-center">
    Governance: {governance.base_score}/100
    {governance.has_critical_risk && (
      <span className="text-error font-medium block mt-1">
        Critical risk found — score capped at 50
      </span>
    )}
  </div>
)}
```

**C. Criteria list unchanged.**

The 7 criteria render exactly as before. No negative points, no 8th item.

**D. New "Areas Needing Attention" section (below criteria, above scoring guide):**

```jsx
{governance.risk_findings?.length > 0 && (
  <div className="mt-6">
    <h3 className="text-lg font-semibold text-text mb-3">
      Areas Needing Attention
    </h3>
    <p className="text-sm text-subtle-text mb-4">
      These items from your Risk Dashboard are affecting your score.
      Resolve them to recover points.
    </p>
    <div className="space-y-2">
      {governance.risk_findings.map((risk, i) => (
        <div key={i} className="card-trust p-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={
              risk.severity === 'critical' ? 'text-error text-lg' :
              risk.severity === 'high' ? 'text-error text-base' :
              risk.severity === 'medium' ? 'text-warning text-base' :
              'text-subtle-text text-base'
            }>
              {risk.severity === 'critical' || risk.severity === 'high' ? '!' : '•'}
            </span>
            <div>
              <p className="text-sm text-text font-medium">{risk.title}</p>
              <p className="text-xs text-subtle-text">{risk.detail}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-error">
              -{Math.abs(risk.penalty || 0)} pts
            </span>
            <Link to={risk.deeplink} className="text-gold text-sm hover:underline">
              Resolve →
            </Link>
          </div>
        </div>
      ))}
    </div>
  </div>
)}
```

**E. Update "How Scoring Works" guide:**

Change heading from "7-Criteria Assessment" to dynamic:

```jsx
<h3>Governance Score</h3>
<p className="text-sm text-subtle-text">
  Your score combines {governance.criteria?.length || 7} governance criteria
  with risk findings from your Risk Dashboard.
</p>
```

Add a second card explaining the penalty system:

```jsx
<div className="card-trust p-4">
  <h4 className="text-sm font-semibold mb-2">Risk Deductions</h4>
  <p className="text-xs text-subtle-text mb-3">
    Active risks from your Risk Dashboard reduce your score.
    Resolve them on the Risk Dashboard to recover points.
  </p>
  <ul className="text-xs space-y-1 text-subtle-text">
    <li>Critical risks: -20 pts each (score capped at 50)</li>
    <li>High risks: -12 pts each (max -25)</li>
    <li>Medium risks: -5 pts each (max -15)</li>
    <li>Low risks: -2 pts each (max -10)</li>
  </ul>
</div>
```

**F. Update hardcoded labels:**

- `"7-Criteria Assessment"` → dynamic or `"Governance Score"`
- `"/ 100"` denominator stays (max_score is still 100)

### 8. Score-Change Notification

When a score calculation detects a drop of 5+ points compared to the previous snapshot due to new risk findings, create an in-app notification:

```python
# In calculate_health_score(), after computing final_score:
if save_snapshot:
    prev = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id},
        sort=[("calculated_at", -1)]
    )
    if prev and prev.get("score_value", 100) - final_score >= 5:
        # Score dropped 5+ points
        new_findings = [r for r in risk_findings if r["severity"] in ("critical", "high")]
        if new_findings:
            await db.notifications.insert_one({
                "user_id": user_id,
                "trust_id": trust_id,
                "type": "score_drop",
                "title": "Your Trust Health Score changed",
                "message": f"Your score is now {final_score}/100. "
                           f"{len(new_findings)} new risk{'s' if len(new_findings) > 1 else ''} "
                           f"affecting your score. Review and resolve to recover points.",
                "action_path": "/governance",
                "created_at": datetime.utcnow(),
                "read": False
            })
```

Framing: "Your score is now X/100" (neutral statement) + "N new risks affecting your score" (actionable) + "Review and resolve to recover points" (autonomy/recovery framing, not blame).

---

## Implementation Order

| Step | File | Description | Prerequisite? |
|------|------|-------------|---------------|
| 1 | `backend/services/risk_gathering.py` | New shared service. Extract risk gathering logic. | None |
| 2 | `backend/routers/risk_dashboard.py` | Refactor endpoint to call shared service. Add critical severity. | Step 1 |
| 3 | `backend/background_tasks.py` | Delete stale function. Import real `calculate_health_score()`. | **Prerequisite for step 5** |
| 4 | `backend/services/chat_service.py` | Fix snapshot field name bug. | None (independent) |
| 5 | Snapshot backfill script | Add schema_version, base_score, risk_penalty to existing snapshots. | Step 3 |
| 6 | `backend/routers/governance.py` | Rebalance weights. Add risk gathering to _gather_score_data. Add penalty computation. Update response shape. Add risk findings cache. | Steps 1, 3 |
| 7 | `frontend/src/pages/GovernancePage.js` | Composite display. "Areas Needing Attention" section. Updated scoring guide. Dynamic labels. | Step 6 |
| 8 | Score-change notification | In-app notification on 5+ point drop from new risk findings. | Step 6 |
| 9 | Test | Verify with trusts that have known risk findings. Confirm hard floor, penalty caps, double-counting exclusion. | Steps 6-8 |
| 10 | Deploy | Backend first, then frontend. Run backfill script during deploy. | Step 9 |

**Ship as one PR.** Splitting risks the snapshot inconsistency window where some snapshots use the old schema and some use the new.

---

## What's Deferred (Not in This Spec)

- **Missing fiduciary risks** (accounting delivery obligations, duty of impartiality, IPS existence, delegation review, beneficiary info request response). The legal review identified these as gaps in both the score and Risk Dashboard. Adding them requires new backend data tracking and is a separate feature effort.
- **Weighted criteria** (all criteria roughly equal weight). Worth revisiting after this ships and we have data on which criteria correlate with audit outcomes.
- **Trend chart decomposition** (showing base vs penalty as separate lines over time). The snapshot schema now stores both, so this is a future frontend enhancement.
- **Risk Dashboard UI changes.** The Risk Dashboard page itself stays as-is. It now feeds into the score but its display doesn't change (except the new "critical" severity badge).

---

## Testing Checklist

- [ ] Trust with 0 risk findings: score unchanged from current behavior
- [ ] Trust with 1 high finding: base - 12, no hard floor
- [ ] Trust with 1 critical finding: score capped at 50 even if base is 100
- [ ] Trust with separation alerts: penalty does NOT include separation (only base score criterion 7)
- [ ] Trust with 3 high findings: penalty capped at -25, not -36
- [ ] Trust with critical + high + medium: hard floor at 50 applies, penalty still calculated
- [ ] Snapshot backfill: old snapshots get schema_version=1, base_score=score_value, risk_penalty=0
- [ ] New snapshots: include base_score, risk_penalty, criteria_breakdown, risk_findings_count
- [ ] chat_service: AI assistant now reads correct score from snapshots
- [ ] Background task: daily snapshots use 7-criteria + penalty, not stale 5-criteria
- [ ] Dashboard load: risk findings served from cache (no 8 extra DB queries)
- [ ] Governance endpoint: risk findings gathered fresh (not cached)
- [ ] Frontend: score circle shows total_score (post-penalty)
- [ ] Frontend: "Areas Needing Attention" section renders risk_findings with deeplinks
- [ ] Frontend: scoring guide shows penalty explanation
- [ ] Frontend: no "7-Criteria" hardcoded text
- [ ] Notification: fires on 5+ point drop from new risk findings
- [ ] Notification: does NOT fire on score increase or <5 point change