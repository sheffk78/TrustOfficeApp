"""Tests for the TrustOffice "leads service" lane (routers/leads_service.py).

Phase 1 OS-overview-card endpoints: scoped key auth (X-Service-Key) + three
read/write routes against the leads + lead_activities collections.

Uses an in-memory mongomock_motor shim (no real DB, no network), mounting the
router directly on a minimal FastAPI app and driving it with TestClient ÃÂ¢ÃÂÃÂ the
same matrix as tests/test_org_entry_http_e2e.py.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_leads_service")
os.environ.setdefault("JWT_SECRET", "test-secret-leads-service")
# Dummy service key for local tests; never a real provisioned key.
os.environ.setdefault("TRUSTOFFICE_LEADS_SERVICE_KEY", "test-service-key-1234")

import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
import routers.leads_service as leads_service

SERVICE_KEY = "test-service-key-1234"
AUTH = {"X-Service-Key": SERVICE_KEY}

db = database.db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Fresh collections around every test."""
    colls = ("leads", "lead_activities", "users", "subscriptions")
    for coll in colls:
        await db[coll].delete_many({})
    yield
    for coll in colls:
        await db[coll].delete_many({})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(leads_service.router, prefix="/api")
    return TestClient(app)


async def _seed_leads(n=3, with_activities=True):
    """Insert n leads (lead_0 is newest) and 3 activities each."""
    now = datetime.now(timezone.utc)
    for i in range(n):
        lid = f"lead_{i}"
        ts = now - timedelta(hours=i)
        await db.leads.insert_one(
            {
                "lead_id": lid,
                "name": f"Lead {i}",
                "email": f"lead{i}@example.com",
                "phone": f"555-000-{i}",
                "stage": "new",
                "source": "blog-subscribe",
                "created_at": ts.isoformat(),
                "updated_at": ts.isoformat(),
                "notes": "",
            }
        )
        if with_activities:
            for j in range(3):
                # activities 0..2 get progressively newer timestamps
                await db.lead_activities.insert_one(
                    {
                        "activity_id": f"act_{lid}_{j}",
                        "lead_id": lid,
                        "action_type": "note",
                        # >160 chars to verify truncation downstream
                        "content": f"activity {j} for lead {i} " + "y" * 200,
                        "created_at": now - timedelta(minutes=(3 - j) * 10),
                    }
                )


# ==================== auth ====================

class TestAuth:
    def test_missing_key_returns_401(self, client):
        r = client.get("/api/service/leads/latest")
        assert r.status_code == 401
        assert "Missing service key" in r.json()["detail"]

    def test_wrong_key_returns_401(self, client):
        r = client.get(
            "/api/service/leads/latest",
            headers={"X-Service-Key": "definitely-not-it"},
        )
        assert r.status_code == 401
        assert "Invalid service key" in r.json()["detail"]

    def test_service_not_configured_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("TRUSTOFFICE_LEADS_SERVICE_KEY", raising=False)
        r = client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"]


# ==================== GET /latest ====================

class TestLatest:
    @pytest.mark.asyncio
    async def test_latest_returns_newest_three_with_activities(self, client):
        await _seed_leads(5)
        r = client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "asOf" in body
        assert "leads" in body
        leads = body["leads"]
        assert len(leads) == 3
        # newest first: lead_0 is the most recent
        assert [l["lead_id"] for l in leads] == ["lead_0", "lead_1", "lead_2"]
        for lead in leads:
            # projected fields present, no _id
            assert "lead_id" in lead and "_id" not in lead
            assert {"name", "email", "phone", "stage", "source", "created_at",
                    "updated_at", "notes"} <= set(lead.keys())
            # exactly 3 activities, each truncated + iso timestamps
            acts = lead["activities"]
            assert len(acts) == 3
            for a in acts:
                assert set(a.keys()) == {"action_type", "content", "created_at"}
                assert a["content"].startswith("activity")
                assert len(a["content"]) == 160  # truncated to 160 chars
                # iso timestamp parses
                datetime.fromisoformat(a["created_at"])

    @pytest.mark.asyncio
    async def test_latest_empty_when_no_leads(self, client):
        r = client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["leads"] == []


# ==================== POST /{lead_id}/note ====================

class TestAddNote:
    @pytest.mark.asyncio
    async def test_note_lands_in_lead_activities(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.post(
            "/api/service/leads/lead_0/note",
            headers=AUTH,
            json={"content": "  spoke with lead, very interested  "},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True}

        acts = [
            a
            async for a in db.lead_activities.find({"lead_id": "lead_0"})
        ]
        assert len(acts) == 1
        assert acts[0]["action_type"] == "manual"
        assert acts[0]["content"] == "spoke with lead, very interested"  # trimmed

    @pytest.mark.asyncio
    async def test_empty_note_rejected(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.post(
            "/api/service/leads/lead_0/note",
            headers=AUTH,
            json={"content": "   "},
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_lead_note_returns_404(self, client):
        r = client.post(
            "/api/service/leads/lead_nope/note",
            headers=AUTH,
            json={"content": "hi"},
        )
        assert r.status_code == 404


# ==================== PATCH /{lead_id}/stage ====================

class TestSetStage:
    @pytest.mark.asyncio
    async def test_stage_change_updates_lead_and_logs_activity(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.patch(
            "/api/service/leads/lead_0/stage",
            headers=AUTH,
            json={"stage": "warm"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True, "stage": "warm"}

        lead = await db.leads.find_one({"lead_id": "lead_0"})
        assert lead["stage"] == "warm"

        acts = [
            a
            async for a in db.lead_activities.find({"lead_id": "lead_0"})
        ]
        assert len(acts) == 1
        assert acts[0]["action_type"] == "system"
        assert "Stage set to warm from OS overview by Kit" == acts[0]["content"]

    @pytest.mark.asyncio
    async def test_bad_stage_returns_400(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.patch(
            "/api/service/leads/lead_0/stage",
            headers=AUTH,
            json={"stage": "not-a-real-stage"},
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_lead_stage_returns_404(self, client):
        r = client.patch(
            "/api/service/leads/lead_nope/stage",
            headers=AUTH,
            json={"stage": "warm"},
        )
        assert r.status_code == 404


# ==================== P2: PEOPLE SERVICE (routers/people_service.py) ====================
# Same fake-db pattern: the router module shares database.db with this file,
# so seeding leads/lead_activities/users/subscriptions here is exactly what
# the endpoints read. The P2 app mounts both routers to prove /latest keeps
# working alongside the new routes.

import routers.people_service as people_service  # noqa: E402


@pytest.fixture
def people_client():
    app = FastAPI()
    app.include_router(leads_service.router, prefix="/api")
    app.include_router(people_service.router, prefix="/api")
    return TestClient(app)


async def _seed_user_sub(
    email="buyer1@example.com",
    user_id="user_buyer1",
    plan="trustee",
    status="active",
    created_at=None,
    with_user=True,
    stripe_sub=None,
):
    """One subscription (+ optional user doc) in the fake db."""
    now = created_at or datetime.now(timezone.utc)
    sub = {
        "subscription_id": "sub_test_" + user_id,
        "user_id": user_id,
        "plan_type": plan,
        "status": status,
        "stripe_subscription_id": stripe_sub or f"stripe_sub_{user_id}",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.subscriptions.insert_one(sub)
    if with_user:
        await db.users.insert_one(
            {
                "user_id": user_id,
                "email": email,
                "full_name": "Buyer " + user_id,
                "first_name": "Buyer",
                "last_name": user_id,
                "created_at": now.isoformat(),
            }
        )
    return sub


async def _seed_converted_lead(
    email="converted@example.com",
    lead_id="lead_conv",
    user_id="user_buyer1",
    name="Converted Person",
):
    """A converted lead with a converted activity + a later non-stage activity."""
    now = datetime.now(timezone.utc)
    await db.leads.insert_one(
        {
            "lead_id": lead_id,
            "name": name,
            "email": email,
            "stage": "converted",
            "source": "trustee-101-landing",
            "created_at": (now - timedelta(days=20)).isoformat(),
            "updated_at": (now - timedelta(days=1)).isoformat(),
            "user_id": user_id,
            "converted_at": (now - timedelta(days=2)).isoformat(),
            "notes": "",
        }
    )
    await db.lead_activities.insert_many(
        [
            {
                "activity_id": "act_" + lead_id + "_created",
                "lead_id": lead_id,
                "action_type": "created",
                "content": "Lead captured via trustee-101-landing",
                "created_at": now - timedelta(days=20),
            },
            {
                "activity_id": "act_" + lead_id + "_converted",
                "lead_id": lead_id,
                "action_type": "converted",
                "content": "Lead converted to subscriber (user_id "
                + user_id
                + ") — linked from warm",
                "created_at": now - timedelta(days=2),
            },
            # a newer non-stage activity after conversion (last_activity_at)
            {
                "activity_id": "act_" + lead_id + "_email",
                "lead_id": lead_id,
                "action_type": "email",
                "content": "Sent via MailerCloud: receipt for your subscription",
                "created_at": now - timedelta(hours=5),
            },
        ]
    )


class TestNoiseSender:
    @pytest.mark.parametrize(
        "addr,name,expected",
        [
            ("no-reply@trustoffice.app", None, True),
            ("noreply@stripe.com", None, True),
            ("dmarc@trustoffice.app", None, True),
            ("postmaster@gmail.com", None, True),
            ("bounce+123abc@sendgrid.net", None, True),
            ("bounces+9@em.mailercloud.net", None, True),
            ("mailer-daemon@mx1.example.com", None, True),
            ("claude@anthropic.com", None, True),
            ("notifications@github.com", None, True),
            ("alerts@google.com", None, True),
            ("googleads-noreply@google.com", None, True),  # domain + token
            ("someone@anthropic.com", None, True),
            ("someone@google.com", None, True),
            ("real.person@example.com", None, False),
            ("Claudette Brice", "claudette.brice@example.com", False),
            ("claudette.fan@example.com", None, False),  # word-boundary check
            ("kit@anthropicwatchers.org", None, False),  # substring, not domain
            ("bob@gmail.community", None, False),  # domain must match exactly
            ("", None, False),
            # display name trips even when the address is a relay alias
            ("alias+cafetcg@example.com", "Google Alerts", True),
        ],
    )
    def test_cases(self, addr, name, expected):
        assert (
            people_service.is_noise_sender(email=addr, name=name or "") is expected
        )


class TestPeopleRoster:
    @pytest.mark.asyncio
    async def test_converted_lead_becomes_purchaser(self, people_client):
        await _seed_converted_lead(user_id="user_conv")
        await _seed_user_sub(email="converted@example.com", user_id="user_conv")
        r = people_client.get("/api/service/people", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "as_of" in body and "counts" in body and "people" in body
        people = body["people"]
        assert len(people) == 1
        person = people[0]
        assert person["kind"] == "purchaser"
        assert person["id"].startswith("purchaser:")
        assert person["email"] == "converted@example.com"
        assert person["stage"] is None
        assert person["plan"] == "trustee"
        # purchased_at = conversion activity / converted_at (never invented)
        assert person["purchased_at"] is not None
        datetime.fromisoformat(person["purchased_at"])
        counts = body["counts"]
        assert counts["purchasers"] == 1 and counts["leads"] == 0

    @pytest.mark.asyncio
    async def test_dedupe_by_email_converted_wins(self, people_client):
        now = datetime.now(timezone.utc)
        # two lead docs with the same email (cased differently); one converted
        await db.leads.insert_one(
            {
                "lead_id": "lead_dup_a",
                "name": "Dup A",
                "email": "dup@example.com",
                "stage": "converted",
                "source": "web",
                "created_at": (now - timedelta(hours=10)).isoformat(),
                "updated_at": now.isoformat(),
                "user_id": "user_dup",
                "notes": "",
            }
        )
        await db.leads.insert_one(
            {
                "lead_id": "lead_dup_b",
                "name": "Dup B",
                "email": "DUP@example.com",
                "stage": "warm",
                "source": "referral",
                "created_at": (now - timedelta(hours=1)).isoformat(),
                "updated_at": now.isoformat(),
                "notes": "",
            }
        )
        r = people_client.get("/api/service/people", headers=AUTH)
        body = r.json()
        assert len(body["people"]) == 1
        person = body["people"][0]
        assert person["kind"] == "purchaser"  # converted wins
        assert body["counts"]["purchasers"] == 1
        assert body["counts"]["leads"] == 0

    @pytest.mark.asyncio
    async def test_non_converted_leads_stay_leads_sorted_by_activity(self, people_client):
        now = datetime.now(timezone.utc)
        for i, (lid, hours_ago) in enumerate([("lead_a", 50), ("lead_b", 1)]):
            await db.leads.insert_one(
                {
                    "lead_id": lid,
                    "name": f"Lead {lid}",
                    "email": f"{lid}@example.com",
                    "stage": "engaged" if i == 0 else "warm",
                    "source": "seo-blog",
                    "created_at": (now - timedelta(days=5)).isoformat(),
                    "updated_at": now.isoformat(),
                    "notes": "",
                }
            )
            await db.lead_activities.insert_one(
                {
                    "activity_id": f"act_{lid}",
                    "lead_id": lid,
                    "action_type": "email",
                    "content": f"Sent welcome email to {lid}",
                    "created_at": now - timedelta(hours=hours_ago),
                }
            )
        r = people_client.get("/api/service/people", headers=AUTH)
        body = r.json()
        people = body["people"]
        assert [p["kind"] for p in people] == ["lead", "lead"]
        # lead_b has the newer last_activity_at -> first among leads
        assert people[0]["email"] == "lead_b@example.com"
        assert people[0]["stage"] == "warm"
        assert people[0]["last_activity_at"] is not None
        assert body["counts"]["leads"] == 2
        assert body["counts"]["by_stage"] == {"engaged": 1, "warm": 1}

    @pytest.mark.asyncio
    async def test_subscription_only_purchaser_included(self, people_client):
        # buyer never created a lead
        await _seed_user_sub(email="subonly@example.com", user_id="user_subonly")
        r = people_client.get("/api/service/people", headers=AUTH)
        body = r.json()
        sub_people = [p for p in body["people"] if p["email"] == "subonly@example.com"]
        assert len(sub_people) == 1
        person = sub_people[0]
        assert person["kind"] == "purchaser"
        assert person["source"] == "subscription"
        assert person["plan"] == "trustee"
        assert person["purchased_at"] is not None
        assert body["counts"]["purchasers"] == 1
        assert body["counts"]["leads"] == 0

    @pytest.mark.asyncio
    async def test_noise_senders_excluded_and_counted(self, people_client):
        now = datetime.now(timezone.utc)
        for i, (lid, email, name) in enumerate(
            [
                ("lead_nr", "no-reply@trustoffice.app", "No Reply"),
                ("lead_cl", "claude@anthropic.com", "Claude"),
                ("lead_ga", "alias@example.com", "Google Alerts"),
                ("lead_ok", "realperson@example.com", "Real Person"),
            ]
        ):
            await db.leads.insert_one(
                {
                    "lead_id": lid,
                    "name": name,
                    "email": email,
                    "stage": "new",
                    "source": "seed",
                    "created_at": (now - timedelta(hours=i)).isoformat(),
                    "updated_at": now.isoformat(),
                    "notes": "",
                }
            )
        r = people_client.get("/api/service/people", headers=AUTH)
        body = r.json()
        emails = [p["email"] for p in body["people"]]
        assert emails == ["realperson@example.com"]
        assert body["counts"]["excluded_noise"] == 3

    @pytest.mark.asyncio
    async def test_purchasers_sorted_before_leads(self, people_client):
        now = datetime.now(timezone.utc)
        # a super-recent lead and an old purchaser
        await db.leads.insert_one(
            {
                "lead_id": "lead_recent",
                "name": "Recent Lead",
                "email": "recent@example.com",
                "stage": "new",
                "source": "web",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "notes": "",
            }
        )
        await db.lead_activities.insert_one(
            {
                "activity_id": "act_recent",
                "lead_id": "lead_recent",
                "action_type": "note",
                "content": "just came in",
                "created_at": now,
            }
        )
        await db.leads.insert_one(
            {
                "lead_id": "lead_oldpurch",
                "name": "Old Purchaser",
                "email": "oldpurch@example.com",
                "stage": "converted",
                "source": "web",
                "created_at": (now - timedelta(days=30)).isoformat(),
                "updated_at": (now - timedelta(days=25)).isoformat(),
                "user_id": "user_oldpurch",
                "converted_at": (now - timedelta(days=25)).isoformat(),
                "notes": "",
            }
        )
        r = people_client.get("/api/service/people", headers=AUTH)
        body = r.json()
        people = body["people"]
        assert [p["kind"] for p in people] == ["purchaser", "lead"]
        assert people[0]["email"] == "oldpurch@example.com"


class TestPeopleCounts:
    @pytest.mark.asyncio
    async def test_counts_endpoint_matches_roster(self, people_client):
        await _seed_converted_lead(user_id="user_conv")
        await _seed_user_sub(email="converted@example.com", user_id="user_conv")
        await _seed_user_sub(email="subonly@example.com", user_id="user_subonly")
        roster = people_client.get("/api/service/people", headers=AUTH).json()
        counts = people_client.get("/api/service/people/counts", headers=AUTH).json()
        assert counts["counts"] == roster["counts"]
        assert "as_of" in counts


class TestPersonEmails:
    @pytest.mark.asyncio
    async def test_latest_10_activities_newest_first(self, people_client):
        now = datetime.now(timezone.utc)
        for i in range(12):
            await db.lead_activities.insert_one(
                {
                    "activity_id": f"act_{i}",
                    "lead_id": "lead_emails",
                    "action_type": "email",
                    "content": f"Sent via MailerCloud: weekly digest {i} - body here",
                    "created_at": now - timedelta(hours=i),
                }
            )
        person_id = "lead:lead_emails"
        r = people_client.get(
            f"/api/service/people/{person_id}/emails", headers=AUTH
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["person"]["id"] == person_id
        assert body["person"]["email"] == ""
        emails = body["emails"]
        assert len(emails) == 10  # capped
        assert "as_of" in body
        # newest first (i=0 is the newest)
        assert "digest 0" in emails[0]["subject"] or "digest 0" in emails[0]["snippet"]

    @pytest.mark.asyncio
    async def test_unknown_person_id_returns_200_empty_not_404(self, people_client):
        r = people_client.get("/api/service/people/nobody:idk/emails", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["emails"] == []
        assert body["person"]["id"] == "nobody:idk"

    @pytest.mark.asyncio
    async def test_unknown_purchaser_id_200_empty(self, people_client):
        r = people_client.get(
            "/api/service/people/purchaser:ghost@example.com/emails", headers=AUTH
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["emails"] == []
        assert body["person"]["email"] == "ghost@example.com"

    @pytest.mark.asyncio
    async def test_email_direction_and_subject_snippet_split(self, people_client):
        now = datetime.now(timezone.utc)
        await db.lead_activities.insert_many(
            [
                {
                    "activity_id": "act_out",
                    "lead_id": "lead_email_dir",
                    "action_type": "email",
                    "content": "Sent via MailerCloud: Your trust checklist - inside: 5 steps to fund your trust",
                    "created_at": now - timedelta(hours=2),
                },
                {
                    "activity_id": "act_note",
                    "lead_id": "lead_email_dir",
                    "action_type": "manual",
                    "content": "spoke on phone, wants pricing",
                    "created_at": now - timedelta(hours=1),
                },
                {
                    "activity_id": "act_stage",
                    "lead_id": "lead_email_dir",
                    "action_type": "system",
                    "content": "Stage set to warm from OS overview by Kit",
                    "created_at": now,
                },
            ]
        )
        r = people_client.get(
            "/api/service/people/lead:lead_email_dir/emails", headers=AUTH
        )
        body = r.json()
        by_subject = {e["subject"]: e for e in body["emails"]}
        out_row = by_subject["Sent via MailerCloud: Your trust checklist"]
        assert out_row["direction"] == "out"
        assert out_row["snippet"].startswith("inside: 5 steps")
        assert len(out_row["snippet"]) <= 160
        assert out_row["type"] == "email"
        note_row = by_subject["spoke on phone, wants pricing"]
        assert note_row["direction"] == "system"  # manual notes are system rows
        stage_row = by_subject["Stage set to warm from OS overview by Kit"]
        assert stage_row["direction"] == "system"
        # newest first overall
        ats = [e["at"] for e in body["emails"]]
        assert ats == sorted(ats, reverse=True)

    @pytest.mark.asyncio
    async def test_inbound_collection_used_when_discovered(self, people_client, monkeypatch):
        now = datetime.now(timezone.utc)
        await db.leads.insert_one(
            {
                "lead_id": "lead_inbound",
                "name": "Inbound Person",
                "email": "person@example.com",
                "stage": "warm",
                "source": "seed",
                "created_at": (now - timedelta(days=3)).isoformat(),
                "updated_at": now.isoformat(),
                "notes": "",
            }
        )
        await db.lead_activities.insert_one(
            {
                "activity_id": "act_out_only",
                "lead_id": "lead_inbound",
                "action_type": "email",
                "content": "Sent welcome email",
                "created_at": now - timedelta(hours=1),
            }
        )
        # simulate a LIVE db with an inbound collection (runtime discovery)
        inbound = db["emails"]
        await inbound.insert_one(
            {
                "to": "person@example.com",
                "from": "friend@other.com",
                "subject": "Question about trusts",
                "snippet": "Can I move my house into the trust?",
                "type": "inbound",
                "created_at": now,
            }
        )

        async def fake_discovery():
            return "emails"

        monkeypatch.setattr(people_service, "_inbound_collection_name", fake_discovery)
        r = people_client.get(
            "/api/service/people/lead:lead_inbound/emails", headers=AUTH
        )
        assert r.status_code == 200, r.text
        body = r.json()
        directions = [e["direction"] for e in body["emails"]]
        assert "in" in directions
        inbound_row = next(e for e in body["emails"] if e["direction"] == "in")
        assert inbound_row["subject"] == "Question about trusts"
        # newest (inbound, now) sorts before the 1h-old outbound send
        assert inbound_row is body["emails"][0]

    @pytest.mark.asyncio
    async def test_no_inbound_invented_without_discovery(self, people_client):
        # default fixture: discovery returns None => only lead_activities rows
        await _seed_converted_lead(user_id="user_conv")
        person_id = "lead:lead_conv"
        r = people_client.get(
            f"/api/service/people/{person_id}/emails", headers=AUTH
        )
        body = r.json()
        for e in body["emails"]:
            assert e["direction"] != "in"
        assert body["person"]["email"] == "converted@example.com"


class TestBackwardCompatLatest:
    @pytest.mark.asyncio
    async def test_latest_still_works_alongside_people_routes(self, people_client):
        await _seed_leads(2)
        r = people_client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "asOf" in body
        assert len(body["leads"]) == 2
        for lead in body["leads"]:
            assert set(lead.keys()) == {
                "lead_id",
                "name",
                "email",
                "phone",
                "stage",
                "source",
                "created_at",
                "updated_at",
                "notes",
                "activities",
            }

    @pytest.mark.asyncio
    async def test_latest_empty_db_still_fine(self, people_client):
        r = people_client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["leads"] == []


class TestPeopleAuth:
    def test_people_missing_key_401(self, people_client):
        r = people_client.get("/api/service/people")
        assert r.status_code == 401

    def test_people_invalid_key_401(self, people_client):
        r = people_client.get(
            "/api/service/people", headers={"X-Service-Key": "wrong"}
        )
        assert r.status_code == 401

    def test_people_emails_missing_key_401(self, people_client):
        r = people_client.get("/api/service/people/lead:x/emails")
        assert r.status_code == 401

    def test_people_counts_missing_key_401(self, people_client):
        r = people_client.get("/api/service/people/counts")
        assert r.status_code == 401
