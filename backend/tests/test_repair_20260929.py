#!/usr/bin/env python3
"""Regression tests for the 2026-09-29 org-package root-cause repair pass.

Covers the fixes applied on top of the three-track verification:

- S1/A: captured require_org_grant + min_level=preparer on write routes
  (viewer grant cannot create; preparer grant can).
- B8: owner can see and act on member-created distributions.
- B9/HIGH-2: owner can see, submit-review, and approve org-member minutes
  (the approval deadlock).
- B10: preparer can generate an admin kit; viewer cannot.
- C: org-member schedule create stamps attribution + org activity rows.
- D1: /revoke/{token} requires the unguessable per-grant revoke_token —
  raw grant_id revokes nothing; stale/unknown tokens 404; audit row written.
- D6: invite tokens expire after 72h and are single-use (atomic accept).
- D4: kit delete actually deletes (deleted_count>0, row gone).

Runs fully in-process (mongomock), same harness as
test_institution_skeleton.py / test_institution_continuation.py.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

import database
from dependencies import _toggle_institution
from models import GrantLevel, ApprovalStatus

db = database.db


def _now():
    return datetime.now(timezone.utc).isoformat()


def _future(days=1, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


def _past(days=0, hours=1):
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


async def _seed_user(email, name="Test User"):
    uid = f"user_{email.split('@')[0]}"
    doc = {"user_id": uid, "email": email, "name": name, "created_at": _now(), "is_admin": False}
    await db.users.replace_one({"user_id": uid}, doc, upsert=True)
    return doc


async def _seed_trust(user, name="Test Trust"):
    tid = f"trust_{user['user_id']}_"
    existing = await db.trusts.find_one({"user_id": user["user_id"]}, sort={"trust_id": -1})
    suffix = 1
    if existing:
        try:
            suffix = int(existing["trust_id"].rsplit("_", 1)[1]) + 1
        except Exception:
            pass
    tid += str(suffix)
    doc = {
        "trust_id": tid,
        "user_id": user["user_id"],
        "name": name,
        "trust_type": "family",
        "created_at": _now(),
        "status": "active",
    }
    await db.trusts.insert_one(doc)
    return doc


async def _grant_member(owner, member, trust, org_id, mem_id, level=GrantLevel.preparer, days=30):
    exists = await db.orgs.find_one({"org_id": org_id})
    if not exists:
        await db.orgs.insert_one({
            "org_id": org_id, "name": "Test Org",
            "owner_user_id": owner["user_id"], "created_at": _now(),
        })
        await db.org_members.insert_one({
            "member_id": f"mem_owner_{org_id}", "org_id": org_id,
            "user_id": owner["user_id"], "email": owner["email"], "name": owner["name"],
            "role": "owner", "status": "active",
            "invited_at": _now(), "invited_by": owner["user_id"], "joined_at": _now(),
        })
    await db.org_members.insert_one({
        "member_id": mem_id, "org_id": org_id, "user_id": member["user_id"],
        "email": member["email"], "name": member["name"],
        "role": "member", "status": "active",
        "invited_at": _now(), "invited_by": owner["user_id"], "joined_at": _now(),
    })
    import secrets as _secrets
    await db.trust_grants.insert_one({
        "grant_id": f"grant_{mem_id}", "trust_id": trust["trust_id"],
        "org_id": org_id, "member_id": mem_id,
        "level": level.value if hasattr(level, "value") else level,
        "status": "active", "granted_by": owner["user_id"], "granted_at": _now(),
        "expires_at": _future(days),
        "revoke_token": _secrets.token_urlsafe(32),
        "revoke_token_expires_at": _future(days),
    })


@pytest_asyncio.fixture
async def seeded_db():
    for coll in [
        "users", "trusts", "orgs", "org_members", "trust_grants",
        "schedule_a_items", "distribution_records", "org_activity",
        "meeting_minutes", "minutes_records", "minutes_approval_status",
        "trust_admin_kits", "meeting_agendas", "trust_parties",
    ]:
        await db[coll].delete_many({})
    return db


def _rd():
    import routers.distributions as _rd
    _rd.db = db
    return _rd


def _rsa():
    import routers.schedule_a as _rsa
    _rsa.db = db
    return _rsa


def _rak():
    import routers.trust_admin_kits as _rak
    _rak.db = db
    return _rak


def _rmeet():
    import routers.meetings as _rmeet
    _rmeet.db = db
    return _rmeet


def _rorg():
    import routers.orgs as _rorg
    _rorg.db = db
    return _rorg


def _msvc():
    import services.meeting_service as _msvc
    _msvc.db = db
    return _msvc


async def _seed_member_distribution(owner, member, trust, dist_id="dist_rp1"):
    await db.distribution_records.insert_one({
        "distribution_id": dist_id, "trust_id": trust["trust_id"],
        "user_id": member["user_id"], "beneficiary_name": "Ben",
        "amount": 100.0, "date": "2026-09-01", "status": "review",
        "purpose_classification": "distribution", "authority_clause_ref": "",
        "notes": "", "solvency_confirmed": True, "recusal_acknowledged": False,
        "created_at": _now(),
    })


def _make_org_actor(member, trust, org_id, mem_id, level="preparer"):
    grant = {
        "grant_id": f"grant_{mem_id}", "trust_id": trust["trust_id"],
        "org_id": org_id, "member_id": mem_id,
        "level": level, "status": "active",
        "expires_at": _future(30),
    }
    return {**member, "org_grant": grant}


async def _seed_member_minutes(owner, member, trust, minutes_id="min_rp1"):
    await db.meeting_minutes.insert_one({
        "minutes_id": minutes_id, "trust_id": trust["trust_id"],
        "user_id": member["user_id"], "title": "Member minutes",
        "meeting_date": "2026-09-20", "status": "draft",
        "created_at": _now(),
    })
    await db.minutes_approval_status.insert_one({
        "approval_id": f"approval_{minutes_id}", "minutes_id": minutes_id,
        "trust_id": trust["trust_id"], "user_id": member["user_id"],
        "current_status": ApprovalStatus.draft.value,
        "drafter_user_id": member["user_id"], "drafter_name": member["name"],
        "action_log": [], "created_at": _now(),
    })


# =====================================================================
# 1+8. B8: owner sees member-created distribution and can PATCH it;
#         viewer grant cannot create (min_level).
# =====================================================================

class TestB8DistributionVisibility:
    @pytest.mark.asyncio
    async def test_owner_views_and_patches_member_distribution(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rd = _rd()
        owner = await _seed_user("b8_owner@example.com", "Owner")
        marge = await _seed_user("b8_marge@example.com", "Marge")
        trust = await _seed_trust(owner, "B8 Trust")
        await _grant_member(owner, marge, trust, "org_b8", "mem_b8")
        await _seed_member_distribution(owner, marge, trust)

        # Owner list includes the member-created row (B8)
        listed = await rd.get_distributions(trust_id=trust["trust_id"], skip=int(0), limit=int(50), user=owner)
        assert any(d.distribution_id == "dist_rp1" for d in listed["items"])

        from models import DistributionStatusUpdate
        body = DistributionStatusUpdate(status="declined")
        patched = await rd.patch_distribution_status("dist_rp1", body, user=owner)
        assert patched.distribution_id == "dist_rp1"  # owner reached the member-owned doc

        doc = await db.distribution_records.find_one({"distribution_id": "dist_rp1"})
        assert doc["status"] == "declined"

    @pytest.mark.asyncio
    async def test_viewer_grant_cannot_create_distribution(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rd = _rd()
        owner = await _seed_user("b8v_owner@example.com", "Owner")
        vista = await _seed_user("b8v_vista@example.com", "Vista")
        trust = await _seed_trust(owner, "B8V Trust")
        await _grant_member(owner, vista, trust, "org_b8v", "mem_b8v", level=GrantLevel.viewer)

        from models import DistributionCreate
        from fastapi import HTTPException
        body = DistributionCreate(
            trust_id=trust["trust_id"], beneficiary_name="Ben",
            amount=10.0, date="2026-09-01", status="review",
            purpose_classification="distribution",
        )
        class _BT:
            def add_task(self, *a, **k):
                pass
        with pytest.raises(HTTPException) as exc:
            await rd.create_distribution(body, _BT(), user=vista)
        assert exc.value.status_code == 403


# =====================================================================
# 2. B9/HIGH-2: owner sees member minutes + approve transition works.
# =====================================================================

class TestB9MinutesDeadlock:
    @pytest.mark.asyncio
    async def test_member_submits_owner_approves(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rmeet = _rmeet()
        msvc = _msvc()
        owner = await _seed_user("b9_owner@example.com", "Owner")
        marge = await _seed_user("b9_marge@example.com", "Marge")
        trust = await _seed_trust(owner, "B9 Trust")
        await _grant_member(owner, marge, trust, "org_b9", "mem_b9")
        await _seed_member_minutes(owner, marge, trust, "min_b9x")

        # Drafter (org member) submits their own minutes for review
        from routers.meetings import WorkflowActionBody
        submitted, err = await msvc.transition_minutes(
            "min_b9x", ApprovalStatus.pending_review, dict(marge), note=None,
        )
        assert err is None and submitted["current_status"] == "pending_review"

        # Owner sees the member-created minutes (previously false 404)
        doc = await msvc.get_minutes_record("min_b9x", owner["user_id"])
        assert doc is not None and doc["minutes_id"] == "min_b9x"
        assert doc["approval_status"] == "pending_review"

        # Owner walks it to approved — the deadlock is gone
        started, err2 = await msvc.transition_minutes(
            "min_b9x", ApprovalStatus.under_review, dict(owner),
        )
        assert err2 is None and started["current_status"] == "under_review"
        approved, err3 = await msvc.transition_minutes(
            "min_b9x", ApprovalStatus.approved, dict(owner), note="LGTM",
        )
        assert err3 is None and approved["current_status"] == "approved"
        assert approved["action_log"][-1]["action"] == "approved"
        assert approved["action_log"][-1]["performed_by_user_id"] == owner["user_id"]

    @pytest.mark.asyncio
    async def test_random_user_cannot_act_on_member_minutes(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        msvc = _msvc()
        owner = await _seed_user("b9r_owner@example.com", "Owner")
        marge = await _seed_user("b9r_marge@example.com", "Marge")
        stranger = await _seed_user("b9r_stranger@example.com", "Stranger")
        trust = await _seed_trust(owner, "B9R Trust")
        await _grant_member(owner, marge, trust, "org_b9r", "mem_b9r")
        await _seed_member_minutes(owner, marge, trust, "min_b9r")

        updated, err = await msvc.transition_minutes(
            "min_b9r", ApprovalStatus.approved, dict(stranger),
        )
        assert updated is None and err == "Minutes approval record not found."


# =====================================================================
# 3. B10 + min_level: preparer kit-gen works, viewer kit-gen 403s.
# =====================================================================

class TestB10Kits:
    @pytest.mark.asyncio
    async def test_preparer_generates_kit_and_owner_sees_it(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rak = _rak()
        owner = await _seed_user("b10_owner@example.com", "Owner")
        marge = await _seed_user("b10_marge@example.com", "Marge")
        trust = await _seed_trust(owner, "B10 Trust")
        await _grant_member(owner, marge, trust, "org_b10", "mem_b10")

        async def _stub_gather(trust_id, user_id):
            return {
                "trust_name": "B10 Trust", "trustee_name": "Marge",
                "ein": "12-3456789", "formation_date": "2020-01-01",
                "state_code": "CA", "jurisdiction": "California",
                "trust_type": "family", "vault_docs": [],
            }

        async def _stub_ai(system_prompt, user_content, max_tokens=None, temperature=None):
            import json as _json
            return _json.dumps({
                "kit_title": "Bank Account Kit",
                "summary": "s", "instructions": ["i1"], "forms": [],
            })

        rak._gather_trust_data = _stub_gather
        rak.ai_sonnet = _stub_ai

        actor = _make_org_actor(marge, trust, "org_b10", "mem_b10", level="preparer")
        await db.org_members.update_one(
            {"member_id": "mem_b10"}, {"$set": {"status": "active"}}
        )
        body = {"trust_id": trust["trust_id"], "kit_type": "bank_account",
                "user_inputs": {"institution_name": "ACME Bank"}}
        resp = await rak.generate_kit(body, user=actor)
        assert resp["kit_id"]

        # Owner now lists the member-generated kit (B8-family)
        listed = await rak.list_kits(trust_id=trust["trust_id"], user=owner)
        assert any(k["kit_id"] == resp["kit_id"] for k in listed["kits"])

    @pytest.mark.asyncio
    async def test_viewer_kit_gen_403(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rak = _rak()
        owner = await _seed_user("b10v_owner@example.com", "Owner")
        vista = await _seed_user("b10v_vista@example.com", "Vista")
        trust = await _seed_trust(owner, "B10V Trust")
        await _grant_member(owner, vista, trust, "org_b10v", "mem_b10v", level=GrantLevel.viewer)

        from fastapi import HTTPException
        actor = _make_org_actor(vista, trust, "org_b10v", "mem_b10v", level="viewer")
        body = {"trust_id": trust["trust_id"], "kit_type": "bank_account",
                "user_inputs": {"institution_name": "ACME Bank"}}
        with pytest.raises(HTTPException) as exc:
            await rak.generate_kit(body, user=actor)
        assert exc.value.status_code == 403


# =====================================================================
# 4. C: member schedule_a create stamps attribution + org activity row.
# =====================================================================

class TestCScheduleAActivity:
    @pytest.mark.asyncio
    async def test_member_create_writes_attribution_and_activity(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rsa = _rsa()
        owner = await _seed_user("c_sa_owner@example.com", "Owner")
        marge = await _seed_user("c_sa_marge@example.com", "Marge")
        trust = await _seed_trust(owner, "C SA Trust")
        await _grant_member(owner, marge, trust, "org_csa", "mem_csa")

        from models import ScheduleAItemCreate
        item = ScheduleAItemCreate(
            trust_id=trust["trust_id"], category="financial_accounts",
            description="Checking", date_conveyed="2026-01-01", approximate_value=5000.0,
        )
        actor = _make_org_actor(marge, trust, "org_csa", "mem_csa")
        resp = await rsa.create_schedule_a_item(item, user=actor)

        row = await db.schedule_a_items.find_one({"item_id": resp.item_id})
        assert row.get("attribution") and "Marge" in row["attribution"]

        events = []
        async for ev in db.org_activity.find({"trust_id": trust["trust_id"]}):
            events.append(ev)
        assert any(e["action"] == "schedule_a_item_added" for e in events)
        assert any("Marge" in (e.get("attribution") or "") for e in events)


# =====================================================================
# 5. D1: revoke endpoint — token mechanics.
# =====================================================================

class TestD1RevokeToken:
    @pytest.mark.asyncio
    async def test_raw_grant_id_cannot_revoke_token_required(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rorg = _rorg()
        owner = await _seed_user("d1_owner@example.com", "Owner")
        marge = await _seed_user("d1_marge@example.com", "Marge")
        trust = await _seed_trust(owner, "D1 Trust")
        await _grant_member(owner, marge, trust, "org_d1", "mem_d1")

        grant = await db.trust_grants.find_one({"grant_id": "grant_mem_d1"})
        from fastapi import HTTPException

        # Old exploit: POST /revoke/{token} with the raw grant_id. Now 404.
        with pytest.raises(HTTPException) as exc:
            await rorg.revoke_by_token(grant["grant_id"])
        assert exc.value.status_code == 404
        assert (await db.trust_grants.find_one({"grant_id": grant["grant_id"]}))["status"] == "active"

        # With the real revoke_token: success
        resp = await rorg.revoke_by_token(grant["revoke_token"])
        assert resp["status"] == "revoked"
        revoked = await db.trust_grants.find_one({"grant_id": grant["grant_id"]})
        assert revoked["status"] == "revoked" and revoked["revoke_reason"] == "token_revoke"
        # Audit row: the endpoint writes it system-side (log_org_activity's
        # grant-actor contract would no-op) — assert it landed.
        audit = await db.org_activity.find_one({"action": "grant_revoked_via_link"})
        assert audit and audit["org_id"] == grant["org_id"]

        # Single-use: second call with the same token 404s
        with pytest.raises(HTTPException) as exc2:
            await rorg.revoke_by_token(grant["revoke_token"])
        assert exc2.value.status_code == 404


# =====================================================================
# 6. D6: invite expiry + single-use accept.
# =====================================================================

class TestD6Invites:
    @pytest.mark.asyncio
    async def test_expired_invite_rejected_active_accepted_single_use(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rorg = _rorg()
        owner = await _seed_user("d6_owner@example.com", "Owner")
        trust = await _seed_trust(owner, "D6 Trust")

        from fastapi import HTTPException
        from models import GrantLevel as _GL
        await _grant_member(owner, invited_user if False else await _seed_user("d6_dummy@example.com"), trust, "org_d6", "mem_d6_dummy", level=_GL.viewer)

        # Fresh invite → accept works
        invited_user = await _seed_user("d6_new@example.com", "New Mem")
        inv = await rorg.invite_org_member(
            "org_d6",
            {"email": invited_user["email"], "name": invited_user["name"]},
            user=owner,
        )
        member_doc = await db.org_members.find_one({"member_id": inv["member_id"]})
        assert member_doc["invite_expires_at"]

        # Expire it manually → reject
        await db.org_members.update_one(
            {"member_id": inv["member_id"]},
            {"$set": {"invite_expires_at": _past()}},
        )
        with pytest.raises(HTTPException) as exc:
            await rorg.accept_org_invite(inv["invite_token"], user=invited_user)
        assert exc.value.status_code == 404
        assert (await db.org_members.find_one({"member_id": inv["member_id"]}))["status"] == "invited"

        # Restore validity → accept works
        await db.org_members.update_one(
            {"member_id": inv["member_id"]},
            {"$set": {"invite_expires_at": _future(hours=1)}},
        )
        resp = await rorg.accept_org_invite(inv["invite_token"], user=invited_user)
        assert resp["status"] == "active"

        # Single-use: re-accept → 404, status stays active
        with pytest.raises(HTTPException) as exc2:
            await rorg.accept_org_invite(inv["invite_token"], user=invited_user)
        assert exc2.value.status_code == 404
        assert (await db.org_members.find_one({"member_id": inv["member_id"]}))["status"] == "active"


# =====================================================================
# 7. D4: kit delete actually deletes.
# =====================================================================

class TestD4KitDelete:
    @pytest.mark.asyncio
    async def test_delete_kit_removes_row(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rak = _rak()
        owner = await _seed_user("d4_owner@example.com", "Owner")
        trust = await _seed_trust(owner, "D4 Trust")

        kit_id = "kit_d4_1"
        await db.trust_admin_kits.insert_one({
            "kit_id": kit_id, "trust_id": trust["trust_id"],
            "user_id": owner["user_id"], "kit_type": "bank_account",
            "kit_title": "Bank Kit", "status": "ready",
            "created_at": _now(),
        })

        import routers.trust_admin_kits as rak_mod
        resp = await rak_mod.delete_kit(kit_id, user=owner)
        assert resp["message"] == "Kit deleted"
        assert await db.trust_admin_kits.find_one({"kit_id": kit_id}) is None

        # Double-delete → 404 (not a fake success)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await rak_mod.delete_kit(kit_id, user=owner)
        assert exc.value.status_code == 404


# =====================================================================
# E: PATCH member role/status allowlist (quick hygiene check).
# =====================================================================

class TestEMemberValidation:
    @pytest.mark.asyncio
    async def test_invalid_role_status_rejected(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        rorg = _rorg()
        owner = await _seed_user("e_owner@example.com", "Owner")
        marge = await _seed_user("e_marge@example.com", "Marge")
        trust = await _seed_trust(owner, "E Trust")
        await _grant_member(owner, marge, trust, "org_e", "mem_e")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await rorg.update_org_member("org_e", "mem_e", {"role": "superadmin"}, user=owner)
        assert exc.value.status_code == 422
        with pytest.raises(HTTPException) as exc2:
            await rorg.update_org_member("org_e", "mem_e", {"status": "weird"}, user=owner)
        assert exc2.value.status_code == 422