# Benevolence policy router — policy creation, versioning, publishing, and export
from fastapi import APIRouter, HTTPException, Depends, Response
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db, client
from dependencies import get_current_user, require_write_access, should_show_watermark
from models import BenevolencePolicyCreate, BenevolencePolicyUpdate, BenevolencePolicyResponse, BenevolencePolicyVersionResponse
from utils.audit import log_audit_event
from services.benevolence_policy_pdf import generate_policy_pdf

router = APIRouter(tags=["benevolence_policy"])


# ==================== POLICY CRUD ====================

@router.post("/benevolence/policies", response_model=BenevolencePolicyVersionResponse)
async def create_benevolence_policy(policy: BenevolencePolicyCreate, user: dict = Depends(require_write_access)):
    """Create a new benevolence policy with its first draft version."""
    trust = await db.trusts.find_one({"trust_id": policy.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")
    if not trust.get("benevolence_enabled"):
        raise HTTPException(status_code=400, detail="Benevolence mode is not enabled for this trust. Enable it in trust settings or upgrade your plan at trustoffice.app/settings/billing.")

    existing = await db.benevolence_policies.find_one({"trust_id": policy.trust_id, "user_id": user["user_id"]})
    if existing:
        raise HTTPException(status_code=409, detail="A benevolence policy already exists for this trust. Use the amend endpoint to create a new version.")

    now = datetime.now(timezone.utc).isoformat()
    policy_id = f"benpol_{uuid.uuid4().hex[:12]}"
    version_id = f"benpolv_{uuid.uuid4().hex[:12]}"

    policy_doc = {
        "policy_id": policy_id,
        "trust_id": policy.trust_id,
        "user_id": user["user_id"],
        "current_version_id": version_id,
        "current_version_label": policy.version_label,
        "current_version_status": "draft",
        "created_at": now,
        "updated_at": None,
    }

    version_doc = _policy_version_to_doc(
        policy_version_id=version_id,
        policy_id=policy_id,
        trust_id=policy.trust_id,
        user_id=user["user_id"],
        policy=policy,
        version_number=1,
        status="draft",
        created_at=now,
        created_by=user["user_id"],
    )

    # Insert policy container and first version (sequential — Railway MongoDB
    # is not a replica set, so transactions are not available).
    await db.benevolence_policies.insert_one(policy_doc)
    await db.benevolence_policy_versions.insert_one(version_doc)

    await log_audit_event(user["user_id"], "benevolence_policy_created", "benevolence_policy", policy_id, {
        "policy_id": policy_id,
        "version_id": version_id,
        "version_label": policy.version_label,
        "trust_name": trust.get("name", ""),
    })

    return BenevolencePolicyVersionResponse(**{k: v for k, v in version_doc.items() if k != "_id"})


@router.get("/benevolence/policies/{trust_id}", response_model=BenevolencePolicyResponse)
async def get_benevolence_policy(trust_id: str, user: dict = Depends(get_current_user)):
    """Get the policy container for a trust (with current version summary)."""
    policy = await db.benevolence_policies.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not policy:
        raise HTTPException(status_code=404, detail="No benevolence policy found for this trust. Create one to get started.")
    return BenevolencePolicyResponse(**policy)


@router.get("/benevolence/policies/{trust_id}/versions", response_model=List[BenevolencePolicyVersionResponse])
async def list_policy_versions(trust_id: str, user: dict = Depends(get_current_user)):
    """List all versions for a trust's policy (draft + published + superseded)."""
    policies = await db.benevolence_policy_versions.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("version_number", -1).to_list(50)
    return [BenevolencePolicyVersionResponse(**p) for p in policies]


@router.get("/benevolence/policies/{trust_id}/active", response_model=BenevolencePolicyVersionResponse)
async def get_active_policy_version(trust_id: str, user: dict = Depends(get_current_user)):
    """Get the currently published (active) version of the policy."""
    policy = await db.benevolence_policies.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not policy:
        raise HTTPException(status_code=404, detail="No benevolence policy found for this trust.")
    if not policy.get("current_version_id"):
        raise HTTPException(status_code=404, detail="No version is currently active.")

    version = await db.benevolence_policy_versions.find_one(
        {"policy_version_id": policy["current_version_id"], "user_id": user["user_id"], "status": "published"},
        {"_id": 0}
    )
    if not version:
        raise HTTPException(status_code=404, detail="Active version not found.")
    return BenevolencePolicyVersionResponse(**version)


@router.get("/benevolence/policies/versions/{policy_version_id}", response_model=BenevolencePolicyVersionResponse)
async def get_policy_version(policy_version_id: str, user: dict = Depends(get_current_user)):
    """Get a single policy version by ID."""
    version = await db.benevolence_policy_versions.find_one(
        {"policy_version_id": policy_version_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found.")
    return BenevolencePolicyVersionResponse(**version)


@router.put("/benevolence/policies/versions/{policy_version_id}", response_model=BenevolencePolicyVersionResponse)
async def edit_policy_version(policy_version_id: str, update: BenevolencePolicyUpdate, user: dict = Depends(require_write_access)):
    """Edit a DRAFT policy version. Published versions are immutable."""
    version = await db.benevolence_policy_versions.find_one(
        {"policy_version_id": policy_version_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found.")
    if version["status"] != "draft":
        raise HTTPException(status_code=400, detail="Only draft versions can be edited. Published or superseded versions are immutable.")

    update_data = {}
    update_payload = {k: v for k, v in update.dict().items() if v is not None}

    # Handle nested list fields
    list_fields = ["eligibility_criteria", "assistance_types", "committee_members", "documentation_requirements"]
    for field in list_fields:
        if field in update_payload:
            update_data[field] = update_payload[field]

    # Simple fields
    simple_fields = [
        "version_label", "charitable_class", "charitable_class_description",
        "per_recipient_annual_limit", "approval_process", "approval_threshold",
        "designated_gift_prohibition", "employee_benevolence_note",
        "board_approval_date", "board_approval_reference", "effective_date", "notes"
    ]
    for field in simple_fields:
        if field in update_payload:
            update_data[field] = update_payload[field]

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.benevolence_policy_versions.update_one(
        {"policy_version_id": policy_version_id},
        {"$set": update_data}
    )

    updated = await db.benevolence_policy_versions.find_one({"policy_version_id": policy_version_id}, {"_id": 0})

    await log_audit_event(user["user_id"], "benevolence_policy_draft_saved", "benevolence_policy", version["policy_id"], {
        "version_id": policy_version_id,
        "fields_changed": list(update_data.keys()),
    })

    return BenevolencePolicyVersionResponse(**updated)


@router.post("/benevolence/policies/versions/{policy_version_id}/publish", response_model=BenevolencePolicyVersionResponse)
async def publish_policy_version(
    policy_version_id: str,
    request: dict,
    user: dict = Depends(require_write_access)
):
    """Publish a draft version. Supersedes any previously published version."""
    version = await db.benevolence_policy_versions.find_one(
        {"policy_version_id": policy_version_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found.")
    if version["status"] != "draft":
        raise HTTPException(status_code=400, detail="Only draft versions can be published.")

    now = datetime.now(timezone.utc).isoformat()
    policy_id = version["policy_id"]

    # Supersede currently published version, publish the new version, and update
    # the policy container — sequential operations (Railway MongoDB is not a
    # replica set, so transactions are not available).
    current_published = await db.benevolence_policy_versions.find_one(
        {"policy_id": policy_id, "status": "published"},
        {"_id": 0},
    )
    if current_published:
        await db.benevolence_policy_versions.update_one(
            {"policy_version_id": current_published["policy_version_id"]},
            {"$set": {"status": "superseded", "updated_at": now}},
        )

    # Build published version update
    update_fields = {
        "status": "published",
        "published_at": now,
        "updated_at": now,
    }
    if request.get("board_approval_date"):
        update_fields["board_approval_date"] = request["board_approval_date"]
    if request.get("board_approval_reference"):
        update_fields["board_approval_reference"] = request["board_approval_reference"]

    await db.benevolence_policy_versions.update_one(
        {"policy_version_id": policy_version_id},
        {"$set": update_fields},
    )

    # Update policy container to point to this version
    await db.benevolence_policies.update_one(
        {"policy_id": policy_id},
        {"$set": {
            "current_version_id": policy_version_id,
            "current_version_label": version["version_label"],
            "current_version_status": "published",
            "updated_at": now,
        }},
    )

    await log_audit_event(user["user_id"], "benevolence_policy_published", "benevolence_policy", policy_id, {
        "version_id": policy_version_id,
        "version_label": version["version_label"],
        "board_approval_date": request.get("board_approval_date"),
    })

    updated = await db.benevolence_policy_versions.find_one({"policy_version_id": policy_version_id}, {"_id": 0})
    return BenevolencePolicyVersionResponse(**updated)


@router.post("/benevolence/policies/{trust_id}/amend", response_model=BenevolencePolicyVersionResponse)
async def amend_policy(
    trust_id: str,
    policy: BenevolencePolicyUpdate,
    user: dict = Depends(require_write_access)
):
    """Create a new draft version copying from the current published version."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")

    current_policy = await db.benevolence_policies.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not current_policy:
        raise HTTPException(status_code=404, detail="No existing policy to amend. Create a new policy first.")

    published_version = await db.benevolence_policy_versions.find_one(
        {"policy_id": current_policy["policy_id"], "status": "published"},
        {"_id": 0}
    )
    if not published_version:
        raise HTTPException(status_code=404, detail="No published version to amend from. Create a policy and publish it first.")

    # Count existing versions, insert the new draft, and update the policy
    # container — sequential operations (Railway MongoDB is not a replica set,
    # so transactions are not available).
    version_count = await db.benevolence_policy_versions.count_documents(
        {"policy_id": current_policy["policy_id"]},
    )

    now = datetime.now(timezone.utc).isoformat()
    new_version_id = f"benpolv_{uuid.uuid4().hex[:12]}"

    # Copy all fields from published version, override with any new values from request
    new_version = dict(published_version)
    new_version["policy_version_id"] = new_version_id
    new_version["version_number"] = version_count + 1
    new_version["version_label"] = policy.version_label or f"{published_version['version_number'] + 1}.0"
    new_version["status"] = "draft"
    new_version["supersedes_version_id"] = published_version["policy_version_id"]
    new_version["published_at"] = None

    # Override fields from the request
    update_data = {k: v for k, v in policy.dict().items() if v is not None}
    for key, value in update_data.items():
        if isinstance(value, list) and value:
            new_version[key] = value
        elif isinstance(value, str) and value:
            new_version[key] = value

    new_version["created_at"] = now
    new_version["updated_at"] = now
    new_version["created_by"] = user["user_id"]

    await db.benevolence_policy_versions.insert_one(new_version)

    # Update policy container to point to the new draft
    await db.benevolence_policies.update_one(
        {"policy_id": current_policy["policy_id"]},
        {"$set": {
            "current_version_id": new_version_id,
            "current_version_label": new_version["version_label"],
            "current_version_status": "draft",
            "updated_at": now,
        }},
    )

    await log_audit_event(user["user_id"], "benevolence_policy_amended", "benevolence_policy", current_policy["policy_id"], {
        "new_version_id": new_version_id,
        "supersedes_version_id": published_version["policy_version_id"],
    })

    new_version.pop("_id", None)
    return BenevolencePolicyVersionResponse(**new_version)


@router.delete("/benevolence/policies/versions/{policy_version_id}")
async def delete_policy_version(policy_version_id: str, user: dict = Depends(require_write_access)):
    """Delete a DRAFT policy version. Published or superseded versions cannot be deleted."""
    version = await db.benevolence_policy_versions.find_one(
        {"policy_version_id": policy_version_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found.")
    if version["status"] != "draft":
        raise HTTPException(status_code=400, detail="Only draft versions can be deleted. Published or superseded versions are permanent.")

    await db.benevolence_policy_versions.delete_one({"policy_version_id": policy_version_id})

    await log_audit_event(user["user_id"], "benevolence_policy_draft_deleted", "benevolence_policy", version["policy_id"], {
        "deleted_version_id": policy_version_id,
    })

    return {"message": "Draft version deleted"}


# ==================== PDF EXPORT ====================

@router.get("/benevolence/policies/{trust_id}/export/pdf")
async def export_policy_pdf(trust_id: str, version_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Generate a styled PDF of the benevolence policy (active version or specified)."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")

    # Resolve version
    if version_id:
        version = await db.benevolence_policy_versions.find_one(
            {"policy_version_id": version_id, "user_id": user["user_id"]},
            {"_id": 0}
        )
    else:
        policy = await db.benevolence_policies.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
        if not policy or not policy.get("current_version_id"):
            raise HTTPException(status_code=404, detail="No published policy version available.")
        version = await db.benevolence_policy_versions.find_one(
            {"policy_version_id": policy["current_version_id"], "user_id": user["user_id"]},
            {"_id": 0}
        )

    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found.")

    show_watermark = await should_show_watermark(user["user_id"])
    pdf_bytes = await generate_policy_pdf(version, trust, show_watermark)

    filename = f"benevolence_policy_{version['version_label']}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


# ==================== HELPERS ====================

def _policy_version_to_doc(policy_version_id, policy_id, trust_id, user_id, policy, version_number, status, created_at, created_by):
    """Convert a BenevolencePolicyCreate to a MongoDB document."""
    return {
        "policy_version_id": policy_version_id,
        "policy_id": policy_id,
        "trust_id": trust_id,
        "user_id": user_id,
        "version_number": version_number,
        "version_label": policy.version_label,
        "status": status,
        "charitable_class": policy.charitable_class,
        "charitable_class_description": policy.charitable_class_description,
        "eligibility_criteria": [c.dict() for c in (policy.eligibility_criteria or [])],
        "assistance_types": [a.dict() for a in (policy.assistance_types or [])],
        "per_recipient_annual_limit": policy.per_recipient_annual_limit,
        "approval_process": policy.approval_process,
        "approval_threshold": policy.approval_threshold,
        "committee_members": [m.dict() for m in (policy.committee_members or [])],
        "documentation_requirements": [d.dict() for d in (policy.documentation_requirements or [])],
        "designated_gift_prohibition": policy.designated_gift_prohibition,
        "employee_benevolence_note": policy.employee_benevolence_note,
        "board_approval_date": policy.board_approval_date,
        "board_approval_reference": policy.board_approval_reference,
        "effective_date": policy.effective_date,
        "supersedes_version_id": policy.supersedes_version_id,
        "notes": policy.notes,
        "published_at": None,
        "created_at": created_at,
        "updated_at": None,
        "created_by": created_by,
    }


# ==================== INDEX MANAGEMENT ====================

async def ensure_indexes():
    """Create indexes for the benevolence policy collections.

    Call this at application startup (wired into server.py startup_event) or
    on first use.  Idempotent — MongoDB create_index is a no-op if the index
    already exists with the same spec.
    """
    # benevolence_policies: one policy per (trust_id, user_id)
    await db.benevolence_policies.create_index(
        [("trust_id", 1), ("user_id", 1)],
        unique=True,
        name="benpol_trust_user_unique",
    )

    # benevolence_policy_versions: lookup by policy + status (e.g. find published)
    await db.benevolence_policy_versions.create_index(
        [("policy_id", 1), ("status", 1)],
        name="benpolv_policy_status",
    )

    # benevolence_policy_versions: lookup by version id + user (access control)
    await db.benevolence_policy_versions.create_index(
        [("policy_version_id", 1), ("user_id", 1)],
        name="benpolv_version_user",
    )