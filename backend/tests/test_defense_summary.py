#!/usr/bin/env python3
"""Phase 3 — defense summary PDF + expiring share link + batch client packet."""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TOGGLE_INSTITUTION", "true")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

import database
import dependencies
import routers.orgs as _orgs
import routers.defense_summary as ds

db = database.db

NOW_ISO = datetime.now(timezone.utc).isoformat()


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    import mongomock_motor
    import routers.org_queue as _oq
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for mod in (database, dependencies, _orgs, _oq, ds):
        monkeypatch.setattr(mod, "db", fresh)
    globals()["db"] = fresh
    for c in ("orgs", "org_members", "trusts", "users", "trust_grants",
              "meeting_minutes", "minutes_approval_status", "distributions",
              "governance_tasks", "health_score_snapshots", "share_links"):
        await db[c].delete_many({})
    yield


@pytest.fixture
def owner_user():
    return {"user_id": "u_owner", "email": "owner@x.com", "name": "Owner", "is_admin": False}


@pytest.fixture
def advisor_user():
    return {"user_id": "u_adv", "email": "adv@firm.com", "name": "Advisor", "is_admin": False}


async def _seed_granted(advisor_user):
    await db.trusts.insert_one({
        "trust_id": "t_1", "name": "Client Trust", "user_id": "u_owner",
        "grantor_name": "G", "trustee_full_name": "T", "creation_date": "2024-01-01",
    })
    await db.orgs.insert_one({"org_id": "org_1", "name": "Firm"})
    await db.org_members.insert_one({
        "member_id": "mem_1", "org_id": "org_1", "user_id": advisor_user["user_id"],
        "email": advisor_user["email"], "status": "active", "role": "owner",
    })
    await db.trust_grants.insert_one({
        "grant_id": "g1", "trust_id": "t_1", "org_id": "org_1",
        "member_id": "mem_1", "level": "preparer", "status": "active",
    })


@pytest.mark.asyncio
async def test_owner_gets_watermarked_pdf(ctx, owner_user):
    await db.trusts.insert_one({"trust_id": "t_1", "name": "Client Trust", "user_id": "u_owner"})
    await db.health_score_snapshots.insert_one({"trust_id": "t_1", "score": 84, "created_at": NOW_ISO})
    resp = await ds.defense_summary_pdf("t_1", user=owner_user)
    assert resp.media_type == "application/pdf"
    assert resp.body[:5] == b"%PDF-"
    from pypdf import PdfReader
    import io as _io
    text = "".join(p.extract_text() or "" for p in PdfReader(_io.BytesIO(resp.body)).pages)
    assert "TrustOffice" in text  # watermarked (white-label off default)


@pytest.mark.asyncio
async def test_granted_member_can_get_summary(ctx, advisor_user):
    await _seed_granted(advisor_user)
    resp = await ds.defense_summary_pdf("t_1", user=advisor_user)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_white_label_pdf_strips_brand(ctx, advisor_user, monkeypatch):
    await _seed_granted(advisor_user)
    async def fake_white(uid): return True
    monkeypatch.setattr(ds, "is_white_label", fake_white)
    resp = await ds.defense_summary_pdf("t_1", user=advisor_user)
    assert resp.body[:5] == b"%PDF-"
    from pypdf import PdfReader
    import io as _io
    text = "".join(p.extract_text() or "" for p in PdfReader(_io.BytesIO(resp.body)).pages)
    assert "TrustOffice" not in text  # fully white-label — zero brand mentions


@pytest.mark.asyncio
async def test_share_link_expiry_and_replacement(ctx, advisor_user):
    await _seed_granted(advisor_user)
    out = await ds.defense_share_link("t_1", user=advisor_user)
    assert out["token"].startswith("dsum_")
    # token fetch works BEFORE any re-share + always white-label
    resp = await ds.defense_summary_by_token(out["token"])
    assert resp.media_type == "application/pdf"
    # share again → old revoked, exactly one active
    out2 = await ds.defense_share_link("t_1", user=advisor_user)
    active = [d async for d in db.share_links.find({"trust_id": "t_1", "revoked_at": {"$exists": False}})]
    assert len(active) == 1
    # old token now dead (revoked)
    with pytest.raises(Exception) as ei_old:
        await ds.defense_summary_by_token(out["token"])
    assert ei_old.value.status_code in (404, 410)
    # expiry → 410 on the ACTIVE token
    old = datetime.now(timezone.utc) - timedelta(days=8)
    await db.share_links.update_one({"token": out2["token"]}, {"$set": {"expires_at": old.isoformat()}})
    with pytest.raises(Exception) as ei:
        await ds.defense_summary_by_token(out2["token"])
    assert ei.value.status_code == 410


@pytest.mark.asyncio
async def test_client_packet_zip_composition(ctx, advisor_user):
    await _seed_granted(advisor_user)
    await db.trusts.insert_one({"trust_id": "t_2", "name": "Other Trust", "user_id": "u_owner"})  # granted? t_2 NOT granted for advisor, owner owns both
    # owner sees both; advisor only t_1 (grant scoped)
    resp_owner = await ds.client_packet("u_owner", user=advisor_user)
    # advisor has grant on t_1 only → packet includes ONLY granted trusts
    import io, zipfile as _zf
    z = _zf.ZipFile(io.BytesIO(resp_owner.body))
    names = z.namelist()
    assert "00-cover.pdf" in names
    assert any("t_1" in n for n in names)
    assert not any("t_2" in n for n in names)


@pytest.mark.asyncio
async def test_packet_empty_and_forbidden(ctx, advisor_user):
    with pytest.raises(Exception) as ei:
        await ds.client_packet("u_ghost", user=advisor_user)
    assert ei.value.status_code == 404
    # stranger with no grants → 403
    await db.trusts.insert_one({"trust_id": "t_9", "name": "Stranger Trust", "user_id": "u_owner"})
    with pytest.raises(Exception) as ei2:
        await ds.client_packet("u_owner", user=advisor_user)
    assert ei2.value.status_code == 403

@pytest.mark.asyncio
async def test_org_packet_zip(ctx, advisor_user):
    await _seed_granted(advisor_user)
    resp = await ds.org_packet("org_1", user=advisor_user)
    import io, zipfile as _zf
    z = _zf.ZipFile(io.BytesIO(resp.body))
    names = z.namelist()
    assert "00-cover.pdf" in names and any("t_1" in n for n in names)
    # non-member org → 403/404
    with pytest.raises(Exception) as ei:
        await ds.org_packet("org_none", user=advisor_user)
    assert ei.value.status_code in (403, 404)
