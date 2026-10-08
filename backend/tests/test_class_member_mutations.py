#!/usr/bin/env python3
"""
Integration tests: TrustOffice named class-member mutations (build session 2).

- REAL mongod launched as a LOCAL single-node replica set on a scratch port +
  scratch dbpath (mongomock cannot do multi-document transactions). rs.initiate
  at fixture start; process killed + dbpath removed at teardown.
- Real FastAPI app via TestClient (httpx) — no prod contact, no external APIs.
- Users are seeded directly into Mongo (direct signup is disabled by design,
  checkout-first) and logs in through the real /api/auth/login endpoint.
- Exercises the real HTTP surface: POST members, POST status, PATCH member,
  PATCH class, DELETE class cascade, cap validation, tenant isolation, and
  forced-transaction rollback.

Run: backend/.venv/bin/python -m pytest backend/tests/test_class_member_mutations.py -p no:warnings -q
"""
import asyncio
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Capture the REAL motor client class at THIS module's import time. Other
# suites in this repo mongomock-patch motor.motor_asyncio.AsyncIOMotorClient
# at their module import (established repo pattern), and pytest imports every
# module before any fixture runs — this file sorts first ('class_' < 'migrat_')
# so the pristine class is still here. The fixture below refuses to proceed if
# the patch already happened (loud failure, never silent mock contamination).
import motor.motor_asyncio as _motor_aio
# conftest captures the PRISTINE class before any suite's mongomock patch:
from conftest import REAL_MOTOR_CLIENT_CLASS as _REAL_ASYNC_CLIENT

# ============ scratch replica-set fixture (module scope) ============
REPLSET_PORT = None

# SUITE-ISOLATION GATE (precedent: test_p2_beneficiary_dashboard's env gate):
# this file spawns a real replica set, rebinds the app's motor client on a
# persistent loop, and patches nothing globally — but pytest-asyncio/motor
# loop-binding makes cross-file in-process isolation impossible to guarantee
# (established 2026-10-07: full-suite aggregation contaminated unrelated
# suites). So: runs ONLY in its dedicated invocation (or explicit opt-in);
# skipped everywhere else. Run:  TR_MEMBER_MUTATIONS_SUITE=1 backend/.venv/bin/python -m pytest backend/tests/test_class_member_mutations.py
pytestmark = pytest.mark.skipif(
    os.environ.get("TR_MEMBER_MUTATIONS_SUITE", "") != "1",
    reason="replica-set integration suite — run standalone with TR_MEMBER_MUTATIONS_SUITE=1",
)
MONGOD_PROC = None
MONGO_DBPATH = None
TEST_DB_NAME = "trustoffice_member_mutations_test"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_listening(port: int, timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise RuntimeError(f"mongod never listened on {port}")


@pytest.fixture(scope="session")
def replica_set():
    """Local single-node replica set for transaction support; killed at teardown."""
    global REPLSET_PORT, MONGOD_PROC, MONGO_DBPATH
    REPLSET_PORT = _free_port()
    MONGO_DBPATH = tempfile.mkdtemp(prefix="to-replicaset-")
    mongod = "/opt/homebrew/bin/mongod"
    if not os.path.exists(mongod):
        mongod = shutil.which("mongod")
        if not mongod:
            pytest.exit("mongod not found — needed for replica-set integration tests", 4)
    proc = subprocess.Popen(
        [
            mongod,
            "--replSet", "rs0",
            "--port", str(REPLSET_PORT),
            "--dbpath", MONGO_DBPATH,
            "--bind_ip", "127.0.0.1",
            "--quiet",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    MONGOD_PROC = proc
    _wait_listening(REPLSET_PORT)

    # rs.initiate with the member bound to 127.0.0.1 so the driver reconnects cleanly
    from pymongo import MongoClient
    client = MongoClient(f"mongodb://127.0.0.1:{REPLSET_PORT}/?directConnection=true",
                         serverSelectionTimeoutMS=30000)
    deadline = time.time() + 30
    initiated = False
    while time.time() < deadline and not initiated:
        try:
            client.admin.command({"replSetInitiate": {"_id": "rs0", "members": [{"_id": 0, "host": f"127.0.0.1:{REPLSET_PORT}"}]}})
            initiated = True
        except Exception:
            time.sleep(0.5)
    if not initiated:
        raise RuntimeError("rs.initiate failed on scratch replica set")
    # wait until PRIMARY
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            hello = client.admin.command("hello")
            if hello.get("isWritablePrimary") or hello.get("ismaster"):
                break
        except Exception:
            pass
        time.sleep(0.5)

    yield {
        "port": REPLSET_PORT,
        "uri": f"mongodb://127.0.0.1:{REPLSET_PORT}",
        "db_name": TEST_DB_NAME,
    }

    try:
        client.close()
    except Exception:
        pass
    if MONGOD_PROC and MONGOD_PROC.poll() is None:
        MONGOD_PROC.send_signal(signal.SIGTERM)
        try:
            MONGOD_PROC.wait(timeout=10)
        except subprocess.TimeoutExpired:
            MONGOD_PROC.kill()
            MONGOD_PROC.wait(timeout=5)
    shutil.rmtree(MONGO_DBPATH, ignore_errors=True)


@pytest.fixture(scope="session")
def app_http(replica_set):
    """
    Real FastAPI app pointed at the scratch replica set. Import AFTER
    os.environ is set so backend/database.py binds the scratch URI.
    """
    os.environ["MONGO_URL"] = replica_set["uri"]
    os.environ["DB_NAME"] = replica_set["db_name"]
    os.environ["RATE_LIMIT_DISABLED"] = "1"
    os.environ["JWT_SECRET"] = "member-mutations-test-secret-not-used-in-prod"
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"
    os.environ["MAILERCLOUD_API_KEY"] = ""   # no external email calls
    os.environ["DISCORD_WEBHOOK_URL"] = ""   # no external Discord posts
    os.environ["TIDYCAL_API_TOKEN"] = ""
    os.environ["POSTMARK_SERVER_TOKEN"] = ""

    import database as database_mod
    # safety: refuse to run against anything but the scratch db
    assert TEST_DB_NAME in (replica_set["db_name"],), "db name mismatch"

    # ---- ONE persistent event loop for the whole session ---------------
    # Motor binds futures to the loop running at first use. TestClient spins
    # fresh loops per request (portal), which makes motor futures from earlier
    # requests "attached to a different loop". So: create the motor client
    # EXPLICITLY bound to a long-lived loop, patch database.client/db BEFORE
    # importing the app (routers do `from database import db` at import time),
    # serve the app via an httpx ASGI transport on that same loop, and run ALL
    # app-touching work (requests AND direct motor calls) on it via run(coro).
    import threading
    import httpx

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    if getattr(_motor_aio.AsyncIOMotorClient, "__module__", "").startswith("mongomock"):
        # A sibling suite's module-level mongomock patch landed before us AND
        # the pristine capture failed — refuse loudly rather than running the
        # whole suite against mongomock (transactions + auth would be fake).
        raise RuntimeError(
            "motor AsyncIOMotorClient was mongomock-patched before this fixture; "
            "test ordering broke the real-driver capture"
        )

    new_client = _REAL_ASYNC_CLIENT(
        replica_set["uri"],
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
        maxPoolSize=20,
        io_loop=loop,  # bind every motor future to the persistent loop
    )
    old_client_ref, old_db_ref = database_mod.client, database_mod.db
    _rebinds: list = []  # (module, attr, previous_value) — undone at teardown
    database_mod.client = new_client
    database_mod.db = new_client[replica_set["db_name"]]
    motor_db = database_mod.db

    # Sibling suites patch motor's client class at their module import BEFORE
    # `import database` runs there, so sys.modules['database'] can already carry
    # a mongomock client — and every module that did `from database import db`
    # at import time (all routers) is then bound to that stale mock. Rebind:
    # walk every already-imported module and repoint module attributes holding
    # the stale client/db at this fixture's real ones.
    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith((
            "dependencies", "routers", "server", "database", "services",
            "chat_service", "action_", "actions_", "approval_handler",
            "trust_admin_service", "trust_brief", "trust_retrieval",
            "ledger_sync", "alert_detection", "background_tasks",
            "cloud_backup_scheduler", "compliance_monitor", "email_service",
            "discord_service", "action_layer", "action_registry",
        )):
            continue
        try:
            mod_attrs = list(vars(mod).items())
        except Exception:
            continue
        for attr, val in mod_attrs:
            if val is old_client_ref:
                _rebinds.append((mod, attr, val))
                setattr(mod, attr, new_client)
            elif val is old_db_ref:
                _rebinds.append((mod, attr, val))
                setattr(mod, attr, database_mod.db)

    def run(coro):
        """Run a coroutine on the persistent loop; result/exception surfaces here."""
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    _state["loop"] = loop
    _state["run"] = run

    from server import app  # routers already bound to database_mod.db above
    _transport = httpx.ASGITransport(app=app)
    _http = httpx.Client(
        base_url="http://testserver", transport=_transport,
    )

    def call(method: str, url: str, headers=None, json=None):
        """Dispatch an HTTP request to the app on the persistent loop."""
        # httpx.Request needs an absolute URL — the ASGI scope must carry a
        # scheme, and starlette chokes on '' for relative URLs.
        if url.startswith("/"):
            url = f"http://testserver{url}"

        async def _one():
            resp = await _transport.handle_async_request(
                httpx.Request(method, url, headers=headers or {}, json=json)
            )
            body = b""
            async for chunk in resp.stream:
                body += chunk
            return httpx.Response(
                resp.status_code, headers=resp.headers, content=body, request=httpx.Request(method, url)
            )
        return run(_one())

    # Startup/shutdown handlers run on the same loop (indexes etc.)
    run(_lifespan_startup(app))

    _state["http"] = HttpWrapper(call)
    yield _state["http"]

    run(_lifespan_shutdown(app))
    # httpx 0.28 ASGITransport has no close(); the httpx.Client.close would
    # raise AttributeError — skip client close entirely (transport is stateless).
    new_client.close()
    loop.call_soon_threadsafe(loop.stop)
    # RESTORE every module binding this fixture changed — otherwise app modules
    # stay bound to this (now-dead) replica set and every later suite in the
    # same pytest session fails against a dead db (full-suite contamination,
    # established 2026-10-07: 70 failures traced to exactly this).
    database_mod.client, database_mod.db = old_client_ref, old_db_ref
    for mod, attr, previous in _rebinds:
        setattr(mod, attr, previous)


async def _lifespan_startup(app):
    """Run the app's startup handlers (index creation) on the persistent loop."""
    for handler in app.router.on_startup:
        res = handler()
        if asyncio.iscoroutine(res):
            await res


async def _lifespan_shutdown(app):
    for handler in app.router.on_shutdown:
        res = handler()
        if asyncio.iscoroutine(res):
            await res


class HttpWrapper:
    """requests-like facade over the persistent-loop ASGI transport."""

    def __init__(self, call):
        self._call = call


    def get(self, url, headers=None, json=None):
        return self._call("GET", url, headers=headers, json=json)

    def post(self, url, headers=None, json=None):
        return self._call("POST", url, headers=headers, json=json)

    def patch(self, url, headers=None, json=None):
        return self._call("PATCH", url, headers=headers, json=json)

    def delete(self, url, headers=None, json=None):
        return self._call("DELETE", url, headers=headers, json=json)


# ============ app/users/trusts seeded within a module-scope session ============
USER1_ID = f"user_{uuid.uuid4().hex[:10]}"
USER1_EMAIL = f"member-mut-1-{uuid.uuid4().hex[:8]}@example.com"
USER1_PASSWORD = "MemberMut#1-2026"
USER2_ID = f"user_{uuid.uuid4().hex[:10]}"
USER2_EMAIL = f"member-mut-2-{uuid.uuid4().hex[:8]}@example.com"
USER2_PASSWORD = "MemberMut#2-2026"
TRUST1_ID = f"trust_{uuid.uuid4().hex[:10]}"
TRUST2_ID = f"trust_{uuid.uuid4().hex[:10]}"

_state = {}


def _mongo():
    """Sync pymongo handle for test-side seeding/verification."""
    from pymongo import MongoClient
    client = MongoClient(
        f"mongodb://127.0.0.1:{REPLSET_PORT}/?directConnection=true",
        serverSelectionTimeoutMS=30000,
    )
    return client[TEST_DB_NAME]


def _seed_user_and_trust(mdb, user_id, email, password, trust_id):
    from dependencies import hash_password
    now = "2026-10-07T00:00:00+00:00"
    mdb.users.insert_one({
        "user_id": user_id, "email": email, "name": "Member Mutations Test",
        "password_hash": hash_password(password), "is_admin": False,
        "created_at": now,
    })
    mdb.subscriptions.insert_one({
        "user_id": user_id, "plan_type": "trustee", "status": "active",
        "current_period_end": "2027-10-07T00:00:00+00:00",
        "is_legacy_price": False,
    })
    mdb.trusts.insert_one({
        "trust_id": trust_id, "user_id": user_id, "name": f"Trust {trust_id}",
        "status": "active", "created_at": now,
    })
    mdb.trust_unit_certificates.insert_one({
        "certificate_id": f"cert_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id, "user_id": user_id,
        "holder_name": "Seed Holder", "holder_identifier": "",
        "holder_type": "individual", "units": 100, "status": "active",
        "certificate_number": 1, "issue_date": now, "notes": "", "email": None, "phone": None,
    })


@pytest.fixture(scope="module")
def client_headers(app_http):
    """Seed users/trusts once; return {user1: headers, user2: headers} + db handle."""
    mdb = _mongo()
    _seed_user_and_trust(mdb, USER1_ID, USER1_EMAIL, USER1_PASSWORD, TRUST1_ID)
    _seed_user_and_trust(mdb, USER2_ID, USER2_EMAIL, USER2_PASSWORD, TRUST2_ID)

    r1 = _state["http"].post("/api/auth/login", json={"email": USER1_EMAIL, "password": USER1_PASSWORD})
    assert r1.status_code == 200, f"user1 login failed: {r1.text[:300]}"
    r2 = _state["http"].post("/api/auth/login", json={"email": USER2_EMAIL, "password": USER2_PASSWORD})
    assert r2.status_code == 200, f"user2 login failed: {r2.text[:300]}"

    _state["h1"] = {"Authorization": f"Bearer {r1.json()['token']}"}
    _state["h2"] = {"Authorization": f"Bearer {r2.json()['token']}"}
    _state["db"] = mdb
    return _state


@pytest.fixture()
def fresh_class(client_headers):
    """Fresh class per test on a FRESH trust — the 100%-cap aggregate is
    per-trust, so reusing one trust across tests starves later creates."""
    c = client_headers
    n = c["trust_seq"] = c.get("trust_seq", 0) + 1
    trust_id = f"{TRUST1_ID}_t{n}"
    c["db"].trusts.insert_one({
        "trust_id": trust_id, "user_id": USER1_ID,
        "name": f"Trust Variant {n}", "status": "active",
        "created_at": "2026-10-07T00:00:00+00:00",
    })
    c["trust_id"] = trust_id
    return c


CB_PREFIX = "/api/beneficiaries/class-beneficiaries"


def _create_class(headers, trust_id, percentage=100.0, description="", notes=""):
    r = _state["http"].post(
        CB_PREFIX,
        headers=headers,
        json={
            "trust_id": trust_id,
            "class_type": "children",
            "description": description,
            "percentage": percentage,
            "notes": notes,
            "distribution_convention": "per_capita",
        },
    )
    assert r.status_code == 200, f"class create failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _fresh(c, pct):
    """Fresh trust (unique cap envelope) + fresh 1-class roster; returns (c, cb)."""
    n = c["trust_seq"] = c.get("trust_seq", 0) + 1
    trust_id = f"{TRUST1_ID}_t{n}"
    c["db"].trusts.insert_one({
        "trust_id": trust_id, "user_id": USER1_ID,
        "name": f"Trust Variant {n}", "status": "active",
        "created_at": "2026-10-07T00:00:00+00:00",
    })
    cb = _create_class(c["h1"], trust_id, percentage=pct)
    return c, cb, trust_id


def _add_member(headers, cb_id, name, **extra):
    return _state["http"].post(f"{CB_PREFIX}/{cb_id}/members", headers=headers,
                               json={"name": name, **extra})


# ==================== 1. add member → shares recompute ====================

def test_add_member_recomputes_shares_and_version(client_headers):
    c, cb, _ = _fresh(client_headers, 100.0)
    assert cb["member_count"] == 0
    cb_id = cb["class_beneficiary_id"]

    r1 = _add_member(c["h1"], cb_id, " Emma Stone ")
    assert r1.status_code == 200, r1.text[:300]
    m1 = r1.json()
    assert m1["name"] == "Emma Stone"  # trimmed
    assert m1["member_status"] == "active"
    assert m1["member_order"] == 1
    assert m1["member_share_percent"] == 100.0
    assert m1["member_share_ppm"] == 1_000_000
    assert m1["share_preview"]["per_member_share_percent_after"] == [100.0]

    r2 = _add_member(c["h1"], cb_id, "Oliver Stone")
    m2 = r2.json()
    assert m2["member_order"] == 2
    # 100% / 2 → 50% each (integers, no drift)
    assert m2["member_share_percent"] == 50.0

    roster = _state["http"].get(f"{CB_PREFIX}/{cb_id}/members", headers=c["h1"]).json()
    assert roster["active_member_count"] == 2
    assert set(roster["per_member_share_percent"].values()) == {50.0}
    assert roster["sum_check"] is True

    cls_doc = c["db"].class_beneficiaries.find_one({"class_beneficiary_id": cb_id})
    assert cls_doc["member_version"] >= 2  # bumped per member mutation
    assert cls_doc["member_count"] == 2
    assert cls_doc["active_member_count"] == 2

    # per-member shares are DERIVED — no per-member storage
    member_row = c["db"].class_beneficiary_members.find_one({"class_member_id": m1["class_member_id"]})
    assert "member_share_percent" not in member_row
    assert "member_share_ppm" not in member_row

    events = list(c["db"].class_member_events.find({"class_beneficiary_id": cb_id}))
    assert [e["event_type"] for e in events] == ["member_added", "member_added"]
    assert events[0]["user_id"] == USER1_ID
    assert events[0]["after"]["name"] == "Emma Stone"


# ==================== 2. deceased status → excluded from split ====================

def test_deceased_status_excluded_from_split(client_headers):
    c, cb, _ = _fresh(client_headers, 50.0)
    cb_id = cb["class_beneficiary_id"]
    m1 = _add_member(c["h1"], cb_id, "A").json()
    m2 = _add_member(c["h1"], cb_id, "B").json()
    m3 = _add_member(c["h1"], cb_id, "C").json()
    roster = _state["http"].get(f"{CB_PREFIX}/{cb_id}/members", headers=c["h1"]).json()
    # 50% pool / 3 → largest-remainder: 16.6667 / 16.6667 / 16.6666 (sum = 50.0000)
    vals = sorted(roster["per_member_share_percent"].values(), reverse=True)
    assert vals == [16.6667, 16.6667, 16.6666]
    assert round(sum(roster["per_member_share_percent"].values()), 4) == 50.0

    r = _state["http"].post(
        f"{CB_PREFIX}/{cb_id}/members/{m2['class_member_id']}/status",
        headers=c["h1"],
        json={"status": "deceased", "reason": "Passed away — recorded in minutes"},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["before_status"] == "active"
    assert body["after_status"] == "deceased"
    assert body["member"]["member_status"] == "deceased"
    assert body["member"]["status_reason"].startswith("Passed away")
    # before/after preview: 3 actives → 2 actives
    assert body["share_preview"]["active_members_before"] == 3
    assert body["share_preview"]["active_members_after"] == 2
    assert body["share_preview"]["per_member_share_percent_before"] == [16.6667, 16.6667, 16.6666]
    assert body["share_preview"]["per_member_share_percent_after"] == [25.0, 25.0]
    assert body["share_preview"]["sum_check"] is True

    roster = _state["http"].get(f"{CB_PREFIX}/{cb_id}/members", headers=c["h1"]).json()
    assert roster["member_count"] == 3  # rows remain — no hard delete
    assert roster["active_member_count"] == 2
    shares = {item["name"]: item["member_share_percent"] for item in roster["items"]}
    assert shares["B"] == 0
    assert shares["A"] == 25.0 and shares["C"] == 25.0

    cls_doc = c["db"].class_beneficiaries.find_one({"class_beneficiary_id": cb_id})
    assert cls_doc["member_count"] == 3
    assert cls_doc["active_member_count"] == 2
    assert cls_doc["member_version"] >= 4

    events = list(c["db"].class_member_events.find(
        {"class_beneficiary_id": cb_id, "event_type": "member_status_changed"}
    ))
    assert len(events) == 1
    assert events[0]["before"] == {"member_status": "active"}
    assert events[0]["after"] == {"member_status": "deceased"}
    assert events[0]["reason"].startswith("Passed away")


# ==================== 2b. status validation ====================

def test_status_requires_reason_and_valid_value(client_headers):
    c, cb, _ = _fresh(client_headers, 10.0)
    cb_id = cb["class_beneficiary_id"]
    m = _add_member(c["h1"], cb_id, "X").json()

    r = _state["http"].post(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}/status",
        headers=c["h1"], json={"status": "deceased", "reason": "   "},
    )
    assert r.status_code in (400, 422)
    r = _state["http"].post(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}/status",
        headers=c["h1"], json={"status": "vanished", "reason": "why"},
    )
    assert r.status_code in (400, 422)
    r = _state["http"].post(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}/status",
        headers=c["h1"], json={"status": "removed", "reason": "Removed at trustee direction"},
    )
    assert r.status_code == 200
    assert r.json()["after_status"] == "removed"


# ==================== 3. rename → name_history grows ====================

def test_rename_appends_name_history(client_headers):
    c, cb, _ = _fresh(client_headers, 100.0)
    cb_id = cb["class_beneficiary_id"]
    m = _add_member(c["h1"], cb_id, "Sarah Lee").json()

    r = _state["http"].patch(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}",
        headers=c["h1"], json={"name": " Sarah Lin "},
    )
    assert r.status_code == 200, r.text[:300]
    updated = r.json()
    assert updated["name"] == "Sarah Lin"
    assert len(updated["name_history"]) == 1
    entry = updated["name_history"][0]
    assert entry["previous_name"] == "Sarah Lee"
    assert entry["changed_by_user_id"] == USER1_ID
    assert entry["changed_at"]

    # second rename — history grows, never a silent overwrite
    r2 = _state["http"].patch(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}",
        headers=c["h1"], json={"name": "Sarah Lin-Chen"},
    )
    assert r2.status_code == 200
    assert [h["previous_name"] for h in r2.json()["name_history"]] == ["Sarah Lee", "Sarah Lin"]

    events = list(c["db"].class_member_events.find(
        {"class_member_id": m["class_member_id"], "event_type": "member_updated"}
    ))
    assert len(events) == 2
    assert events[0]["before"] == {"name": "Sarah Lee"}
    assert events[1]["after"] == {"name": "Sarah Lin-Chen"}

    r3 = _state["http"].patch(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}",
        headers=c["h1"], json={"name": "Sarah Lin-Chen"},
    )
    assert r3.status_code == 400  # identical rename refused


# ==================== 4. PATCH class → recompute / cap ====================

def test_patch_class_percentage_recomputes(client_headers):
    c, cb, _ = _fresh(client_headers, 30.0)
    cb_id = cb["class_beneficiary_id"]
    _add_member(c["h1"], cb_id, "P1")
    _add_member(c["h1"], cb_id, "P2")

    r = _state["http"].patch(
        f"{CB_PREFIX}/{cb_id}", headers=c["h1"],
        json={"percentage": 60.0, "notes": "post-death update"},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["class"]["percentage"] == 60.0
    assert body["share_preview"]["pool_percentage_ppm"] == 600_000
    assert set(body["share_preview"]["per_member_share_percent"].values()) == {30.0}
    assert body["share_preview"]["sum_check"] is True

    cls_doc = c["db"].class_beneficiaries.find_one({"class_beneficiary_id": cb_id})
    assert cls_doc["notes"] == "post-death update"
    assert cls_doc["member_version"] >= 1  # bump on percentage change

    events = list(c["db"].class_member_events.find(
        {"class_beneficiary_id": cb_id, "event_type": "class_updated"}
    ))
    assert len(events) == 1
    assert events[0]["class_member_id"] is None
    assert events[0]["before"] == {"percentage": 30.0, "notes": ""}
    assert events[0]["after"] == {"percentage": 60.0, "notes": "post-death update"}


def test_patch_class_cap_violation_rejected(client_headers):
    c = client_headers
    n = c["trust_seq"] = c.get("trust_seq", 0) + 1
    cap_trust = f"{TRUST1_ID}_cap{n}"
    c["db"].trusts.insert_one({"trust_id": cap_trust, "user_id": USER1_ID,
        "name": f"Trust Variant cap{n}", "status": "active",
        "created_at": "2026-10-07T00:00:00+00:00"})
    cb1 = _create_class(c["h1"], cap_trust, percentage=60.0)
    _create_class(c["h1"], cap_trust, percentage=40.0)
    # 60 + 40 = 100 currently; moving cb1 to 50 gives 50 + 40 = 90 ≤ 100 — allowed
    r = _state["http"].patch(
        f"{CB_PREFIX}/{cb1['class_beneficiary_id']}", headers=c["h1"],
        json={"percentage": 50.0},
    )
    assert r.status_code == 200, r.text[:200]
    # restore cb1 to 61 → 61 + 40 = 101 > 100 → rejected (same aggregate rule as create)
    r2 = _state["http"].patch(
        f"{CB_PREFIX}/{cb1['class_beneficiary_id']}", headers=c["h1"],
        json={"percentage": 61.0},
    )
    assert r2.status_code == 400
    assert "100%" in r2.json()["detail"]


def test_create_path_cap_still_enforced(client_headers):
    c = client_headers
    n = c["trust_seq"] = c.get("trust_seq", 0) + 1
    cap_trust = f"{TRUST1_ID}_cap{n}"
    c["db"].trusts.insert_one({"trust_id": cap_trust, "user_id": USER1_ID,
        "name": f"Trust Variant cap{n}", "status": "active",
        "created_at": "2026-10-07T00:00:00+00:00"})
    _create_class(c["h1"], cap_trust, percentage=60.0)
    r = _state["http"].post(CB_PREFIX, headers=c["h1"], json={
        "trust_id": cap_trust, "class_type": "custom", "percentage": 41.0,
        "description": "", "notes": "",
    })
    assert r.status_code == 400


# ==================== 5. cascade delete removes member docs ====================

def test_class_delete_cascades_members(client_headers):
    c, cb, _ = _fresh(client_headers, 20.0)
    cb_id = cb["class_beneficiary_id"]
    m1 = _add_member(c["h1"], cb_id, "Del One").json()
    m2 = _add_member(c["h1"], cb_id, "Del Two").json()

    r = _state["http"].delete(f"{CB_PREFIX}/{cb_id}", headers=c["h1"])
    assert r.status_code == 200, r.text[:300]
    assert r.json() == {"status": "deleted"}  # contract unchanged

    assert c["db"].class_beneficiaries.find_one({"class_beneficiary_id": cb_id}) is None
    assert c["db"].class_beneficiary_members.find_one({"class_member_id": m1["class_member_id"]}) is None
    assert c["db"].class_beneficiary_members.find_one({"class_member_id": m2["class_member_id"]}) is None
    # audit events survive the doc deletion
    events = list(c["db"].class_member_events.find(
        {"class_beneficiary_id": cb_id, "event_type": "member_removed"}
    ))
    assert len(events) == 2

    r2 = _state["http"].delete(f"{CB_PREFIX}/{cb_id}", headers=c["h1"])
    assert r2.status_code == 404


# ==================== 6. forced transaction failure → no orphans ====================

def test_forced_txn_failure_leaves_no_orphan(client_headers, monkeypatch):
    c, cb, _ = _fresh(client_headers, 15.0)
    cb_id = cb["class_beneficiary_id"]
    class_doc = c["db"].class_beneficiaries.find_one({"class_beneficiary_id": cb_id})
    version_before = class_doc.get("member_version", 0)

    member_doc = {
        "class_member_id": f"cm_{uuid.uuid4().hex[:12]}",
        "class_beneficiary_id": cb_id,
        "trust_id": TRUST1_ID, "user_id": USER1_ID,
        "name": "Rollback Kid", "member_status": "active",
        "member_order": 99, "created_at": "2026-10-07T00:00:00+00:00",
    }
    event = {
        "event_id": f"cme_{uuid.uuid4().hex[:16]}", "trust_id": TRUST1_ID,
        "user_id": USER1_ID, "class_beneficiary_id": cb_id,
        "class_member_id": member_doc["class_member_id"],
        "event_type": "member_added", "before": None, "after": member_doc,
        "reason": "should roll back", "created_at": "2026-10-07T00:00:00+00:00",
    }

    async def failing_ops(session):
        import database as database_mod
        await database_mod.db.class_beneficiary_members.insert_one(member_doc, session=session)
        await database_mod.db.class_member_events.insert_one(event, session=session)
        # force the failure AFTER the writes, INSIDE the transaction
        raise RuntimeError("forced failure — everything must roll back")

    seen = {}

    async def run_failing_txn():
        import database as database_mod
        from routers.beneficiaries import _run_with_txn
        await _run_with_txn(database_mod.client, failing_ops)

    # Force the transaction branch ON (bypass the capability probe cache) so
    # this test exercises real atomic-rollback semantics on the replica set.
    import routers.beneficiaries as rb

    async def always_supported(client):
        seen["called"] = True
        return True

    monkeypatch.setattr(rb, "_txn_supported", always_supported)

    # Run INSIDE the same persistent loop the motor futures are bound to —
    # a fresh loop would recreate the "attached to a different loop" failure.
    raised = None
    try:
        c["run"](run_failing_txn())
    except RuntimeError as exc:
        raised = exc
    assert raised is not None and "forced failure" in str(raised)
    assert seen.get("called") is True

    # member doc rolled back — no orphan
    assert c["db"].class_beneficiary_members.find_one(
        {"class_member_id": member_doc["class_member_id"]}
    ) is None
    # event rolled back
    assert c["db"].class_member_events.find_one({"event_id": event["event_id"]}) is None
    # class intact + member_count intact
    cls_doc = c["db"].class_beneficiaries.find_one({"class_beneficiary_id": cb_id})
    assert cls_doc is not None
    assert cls_doc["member_count"] == 0
    real_m = _add_member(c["h1"], cb_id, "Real Member")
    assert real_m.status_code == 200
    assert real_m.json()["member_order"] == 1  # orphan never took the rank
    cls_doc = c["db"].class_beneficiaries.find_one({"class_beneficiary_id": cb_id})
    assert cls_doc["member_count"] == 1
    assert cls_doc["member_version"] >= version_before


# ==================== 7. tenant isolation ====================

def test_tenant_isolation_status_and_visibility(client_headers):
    c, cb, _ = _fresh(client_headers, 100.0)
    cb_id = cb["class_beneficiary_id"]
    m = _add_member(c["h1"], cb_id, "Private Member").json()

    # user2 cannot see user1's members via user2's token
    r = _state["http"].get(f"{CB_PREFIX}/{cb_id}/members", headers=c["h2"])
    assert r.status_code == 404  # user1-scoped class → not found for user2

    # user2 cannot mutate user1's member even with its id
    r2 = _state["http"].post(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}/status",
        headers=c["h2"], json={"status": "removed", "reason": "attacker reason"},
    )
    assert r2.status_code == 404
    r3 = _state["http"].patch(
        f"{CB_PREFIX}/{cb_id}/members/{m['class_member_id']}",
        headers=c["h2"], json={"name": "Hijacked"},
    )
    assert r3.status_code == 404
    r4 = _state["http"].delete(f"{CB_PREFIX}/{cb_id}", headers=c["h2"])
    assert r4.status_code == 404

    # nothing changed
    row = c["db"].class_beneficiary_members.find_one({"class_member_id": m["class_member_id"]})
    assert row["name"] == "Private Member" and row["member_status"] == "active"

    # events ledger is owner-scoped
    events = list(c["db"].class_member_events.find({"class_member_id": m["class_member_id"]}))
    assert all(e["user_id"] == USER1_ID for e in events)
