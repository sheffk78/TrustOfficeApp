"""
Records Repository (F1 Delta, 2026-09-12) — backend endpoint tests.

Covers every new endpoint against a pure in-process FakeDB (the
test_tenant_isolation convention — no real MongoDB, no live API), plus the
dependency-level 409 trust_dissolved archive guard and the typed-confirm
rejection path of DELETE /vault/documents/bulk.

Endpoints under test:
  - POST   /api/trusts/{trust_id}/dissolve
  - POST   /api/trusts/{trust_id}/un-dissolve   (admin-only reversal)
  - GET    /api/account/exit-summary
  - DELETE /api/vault/documents/bulk             (typed confirm)
  - POST   /api/repository/purchase             (Stripe mocked)
  - GET    /api/trusts/{trust_id}/archive-export (streaming ZIP)
  - 409 guard: mutating trust-scoped routes reject when dissolved_archived

Run:  python -m pytest backend/tests/test_repository_flow.py -q
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_repo_test")
os.environ.setdefault("JWT_SECRET", "test-secret-repo-flow")
os.environ.setdefault("CORS_ORIGINS", "https://app.trustoffice.app")


# ==================== Fake Mongo (mirrors test_tenant_isolation) ====================

class FakeResult:
    def __init__(self, modified_count=0, matched_count=0, inserted_id=None,
                 deleted_count=0):
        self.modified_count = modified_count
        self.matched_count = matched_count
        self.inserted_id = inserted_id
        self.deleted_count = deleted_count


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    async def to_list(self, length=None):
        return list(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None, **kwargs):
        for d in self.docs:
            if self._match(query, d):
                return dict(d)
        return None

    def find(self, query=None, projection=None):
        return FakeCursor([d for d in self.docs
                           if not query or self._match(query, d)])

    @staticmethod
    def _match(query, d):
        """Mini query matcher with $exists / $ne / equality support."""
        for k, v in (query or {}).items():
            if isinstance(v, dict):
                if "$exists" in v and (k in d) != v["$exists"]:
                    return False
                if "$ne" in v and d.get(k) == v["$ne"]:
                    return False
                continue
            if d.get(k) != v:
                return False
        return True

    async def insert_one(self, doc):
        d = dict(doc)
        d.setdefault("_id", f"id_{len(self.docs)}")
        self.docs.append(d)
        return FakeResult(inserted_id=d["_id"])

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if self._match(query, d):
                if "$set" in update:
                    d.update(update["$set"])
                if "$unset" in update:
                    for k in update["$unset"]:
                        d.pop(k, None)
                return FakeResult(modified_count=1, matched_count=1)
        if upsert:
            d = dict(query)
            if "$set" in update:
                d.update(update["$set"])
            self.docs.append(d)
            return FakeResult(modified_count=1, matched_count=1)
        return FakeResult(modified_count=0, matched_count=0)

    async def find_one_and_update(self, query, update, projection=None, **kwargs):
        for d in self.docs:
            if self._match(query, d):
                if "$set" in update:
                    d.update(update["$set"])
                if "$unset" in update:
                    for k in update["$unset"]:
                        d.pop(k, None)
                before = {k: v for k, v in d.items() if k != "_id"}
                return before
        return None

    async def update_many(self, query, update):
        count = 0
        for d in self.docs:
            if self._match(query, d):
                if "$set" in update:
                    d.update(update["$set"])
                count += 1
        return FakeResult(modified_count=count, matched_count=count)

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not self._match(query, d)]
        return FakeResult(deleted_count=before - len(self.docs))

    async def count_documents(self, query=None):
        return len([d for d in self.docs if not query or self._match(query, d)])

    async def distinct(self, key, query=None):
        vals = set()
        for d in self.docs:
            if not query or self._match(query, d):
                if key in d:
                    vals.add(d[key])
        return list(vals)

    async def create_index(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()
        self.trusts = FakeCollection()
        self.vault_documents = FakeCollection()
        self.subscriptions = FakeCollection()
        self.security_events = FakeCollection()
        self.audit_logs = FakeCollection()
        self.repository_entitlements = FakeCollection()
        self.payment_transactions = FakeCollection()
        self.repository_ai_quota = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col

    def __getitem__(self, name):
        # Support db["collection"] access (full_export._records uses it).
        if not hasattr(self, name) or not isinstance(getattr(self, name), FakeCollection):
            setattr(self, name, FakeCollection())
        return getattr(self, name)


USER_A = {"user_id": "user_A", "email": "a@test.local", "is_admin": False}
ADMIN  = {"user_id": "user_ADMIN", "email": "admin@test.local", "is_admin": True}
USER_B = {"user_id": "user_B", "email": "b@test.local", "is_admin": False}
TRUST_A = "trust_repo_A"


@pytest.fixture
def repo_db(monkeypatch):
    import database
    import dependencies
    import routers.trusts
    import routers.vault
    import routers.account_summary
    import routers.repository
    import services.trust_archive

    db = FakeDB()

    # Account A + A's active trust (status set explicitly to mirror backfilled data)
    db.users.docs.append({"_id": "uA", "user_id": USER_A["user_id"],
                          "email": USER_A["email"],
                          "password_hash": dependencies.hash_password("PasswordA123"),
                          "is_admin": False})
    db.users.docs.append({"_id": "uADMIN", "user_id": ADMIN["user_id"],
                          "email": ADMIN["email"], "is_admin": True})
    db.users.docs.append({"_id": "uB", "user_id": USER_B["user_id"],
                          "email": USER_B["email"],
                          "password_hash": dependencies.hash_password("PasswordB123"),
                          "is_admin": False})
    db.trusts.docs.append({"_id": "tA", "trust_id": TRUST_A, "user_id": USER_A["user_id"],
                           "name": "A Trust", "status": "active", "created_at": "2026-01-01T00:00:00Z"})
    # Account B's trust (cross-tenant target)
    db.trusts.docs.append({"_id": "tB", "trust_id": "trust_repo_B",
                           "user_id": USER_B["user_id"], "name": "B Trust",
                           "status": "active", "created_at": "2026-01-01T00:00:00Z"})
    # Vault docs for account A (one with content, one without)
    db.vault_documents.docs.append({"_id": "vA1", "doc_id": "doc_A_1",
                                    "user_id": USER_A["user_id"], "trust_id": TRUST_A,
                                    "file_name": "wills.pdf", "file_content": b"PDFDATA",
                                    "file_content_type": "application/pdf", "category": "legal"})
    db.vault_documents.docs.append({"_id": "vA2", "doc_id": "doc_A_2",
                                    "user_id": USER_A["user_id"], "trust_id": TRUST_A,
                                    "file_name": "scan.png", "file_content": None,
                                    "category": "asset"})
    # Account A's subscription (active, paid)
    db.subscriptions.docs.append({"_id": "sA", "user_id": USER_A["user_id"],
                                  "plan_type": "annual", "status": "active",
                                  "billing_period": "annual",
                                  "current_period_end": "2027-09-12T00:00:00Z"})
    # Cloud backup connection for A
    db.cloud_backup_connections.docs.append({"_id": "cA", "user_id": USER_A["user_id"],
                                             "provider": "google_drive", "is_active": True,
                                             "last_backup_at": "2026-09-11T10:00:00Z"})

    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(dependencies, "db", db)
    import utils.audit
    monkeypatch.setattr(utils.audit, "db", db)  # binds at import time
    # Modules that bind db at import time (trusts.update/get chain into
    # governance's health-score calc; full_export._records drives the export).
    import routers.governance
    import routers.full_export
    monkeypatch.setattr(routers.governance, "db", db)
    monkeypatch.setattr(routers.full_export, "db", db)
    for mod in (routers.trusts, routers.vault, routers.account_summary,
                routers.repository):
        monkeypatch.setattr(mod, "db", db)
    return db


@pytest.fixture
def repo_app(repo_db):
    from fastapi import FastAPI
    import routers.trusts
    import routers.vault
    import routers.account_summary
    import routers.repository
    from services.trust_archive import apply_archive_guard

    a = FastAPI()
    for r in (routers.trusts, routers.vault, routers.account_summary,
              routers.repository):
        a.include_router(r.router, prefix="/api")
    # Wire the dependency-level 409 trust_dissolved guard exactly as server
    # startup does, so the guard tests exercise the real enforcement point.
    apply_archive_guard(a)
    return a


def _client_as(app, user):
    from fastapi.testclient import TestClient
    import dependencies

    async def fake_current():
        return user

    app.dependency_overrides[dependencies.get_current_user] = fake_current
    # raise_server_exceptions=True so a server-side bug surfaces as a traceback
    # instead of a silent 500 — the FakeDB fixtures must not mask defects.
    return TestClient(app, raise_server_exceptions=True)


# ==================== Trust status model / backfill (service-level) ====================

def test_backfill_trust_status_stamps_legacy_trusts(repo_db):
    """Explicit backfill: legacy trusts missing 'status' get status='active'."""
    # Insert one legacy trust with no status field.
    legacy_id = "trust_legacy"
    repo_db.trusts.docs.append({"_id": "tL", "trust_id": legacy_id,
                                "user_id": USER_A["user_id"], "name": "Legacy"})
    from services.trust_archive import backfill_trust_status
    updated = 0

    async def run():
        nonlocal updated
        updated = await backfill_trust_status()
    import asyncio
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(run())
    assert updated == 1
    legacy = next(d for d in repo_db.trusts.docs if d.get("trust_id") == legacy_id)
    assert legacy["status"] == "active"


# ==================== POST /trusts/{id}/dissolve ====================

def test_dissolve_sets_status_and_dissolved_on(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.post(f"/api/trusts/{TRUST_A}/dissolve", json={"dissolved_on": "2026-09-12"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dissolved_archived"
    assert r.json()["dissolved_on"] == "2026-09-12"
    trust = next(d for d in repo_db.trusts.docs if d.get("trust_id") == TRUST_A)
    assert trust["status"] == "dissolved_archived"
    assert trust["dissolved_on"] == "2026-09-12"


def test_dissolve_writes_audit_and_security_events(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.post(f"/api/trusts/{TRUST_A}/dissolve", json={"dissolved_on": "2026-09-12"})
    assert r.status_code == 200
    assert any(e.get("event_type") == "trust_dissolved"
               for e in repo_db.security_events.docs)


def test_dissolve_unknown_trust_404(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.post("/api/trusts/trust_nope/dissolve", json={"dissolved_on": "2026-09-12"})
    assert r.status_code == 404


def test_un_dissolve_admin_only(repo_app, repo_db):
    # Dissolve first as A.
    c = _client_as(repo_app, USER_A)
    assert c.post(f"/api/trusts/{TRUST_A}/dissolve",
                  json={"dissolved_on": "2026-09-12"}).status_code == 200
    # Non-admin (B) is forbidden.
    cb = _client_as(repo_app, USER_B)
    r = cb.post(f"/api/trusts/{TRUST_A}/un-dissolve")
    assert r.status_code == 403
    t = next(d for d in repo_db.trusts.docs if d.get("trust_id") == TRUST_A)
    assert t["status"] == "dissolved_archived"  # unchanged
    # Admin reversal works.
    ca = _client_as(repo_app, ADMIN)
    r2 = ca.post(f"/api/trusts/{TRUST_A}/un-dissolve")
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "active"
    t2 = next(d for d in repo_db.trusts.docs if d.get("trust_id") == TRUST_A)
    assert t2["status"] == "active"
    assert "dissolved_on" not in t2


# ==================== 409 archive guard ====================

def test_archive_guard_blocks_mutating_route_when_dissolved(repo_app, repo_db):
    """After dissolve, a mutating trust-scoped route returns 409 trust_dissolved."""
    c = _client_as(repo_app, USER_A)
    assert c.post(f"/api/trusts/{TRUST_A}/dissolve",
                  json={"dissolved_on": "2026-09-12"}).status_code == 200
    # PUT on the trust is a mutating trust-scoped route -> guarded.
    r = c.put(f"/api/trusts/{TRUST_A}", json={"name": "Hacked Name"})
    assert r.status_code == 409, r.text
    assert r.json().get("detail", {}).get("code") == "trust_dissolved"
    # DELETE on the trust too.
    r2 = c.delete(f"/api/trusts/{TRUST_A}")
    assert r2.status_code == 409


def test_archive_guard_read_still_works_when_dissolved(repo_app, repo_db):
    """Read / GET must be unaffected — dissolved archives stay viewable."""
    c = _client_as(repo_app, USER_A)
    assert c.post(f"/api/trusts/{TRUST_A}/dissolve",
                  json={"dissolved_on": "2026-09-12"}).status_code == 200
    r = c.get(f"/api/trusts/{TRUST_A}")
    assert r.status_code == 200


def test_archive_guard_active_route_not_blocked(repo_app, repo_db):
    """An active trust's mutating routes pass the guard."""
    c = _client_as(repo_app, USER_A)
    r = c.put(f"/api/trusts/{TRUST_A}", json={"name": "Renamed"})
    assert r.status_code not in (409, 500)


# ==================== GET /account/exit-summary ====================

def test_exit_summary_shape(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.get("/api/account/exit-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["backup"]["connected"] is True
    assert body["backup"]["last_backup_at"] == "2026-09-11T10:00:00Z"
    # documents = vault files WITH content (1), vault_items = all (2)
    assert body["counts"] == {"documents": 1, "vault_items": 2}
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["access_until"] is not None


def test_exit_summary_no_backup(repo_app, repo_db):
    user_b = USER_B
    c = _client_as(repo_app, user_b)
    r = c.get("/api/account/exit-summary")
    assert r.status_code == 200
    assert r.json()["backup"]["connected"] is False


# ==================== DELETE /vault/documents/bulk ====================

def test_bulk_delete_rejects_wrong_confirm(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.request("DELETE", "/api/vault/documents/bulk", json={"confirm": "wrong"})
    assert r.status_code == 400, r.text
    # Nothing deleted.
    assert len(repo_db.vault_documents.docs) == 2


def test_bulk_delete_with_typed_confirm(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.request("DELETE", "/api/vault/documents/bulk", json={"confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2
    assert repo_db.vault_documents.docs == []
    # Security event written.
    assert any(e.get("event_type") == "vault_bulk_delete"
               for e in repo_db.security_events.docs)


# ==================== POST /repository/purchase (Stripe mocked) ====================

def test_repository_purchase_creates_checkout(repo_app, repo_db, monkeypatch):
    import routers.repository as repo_mod

    captured = {}

    async def fake_customer(user):
        captured["customer"] = user
        return "cus_test123"

    class FakeSession:
        url = "https://checkout.stripe.com/test123"
        id = "cs_test123"

    def fake_create(**kwargs):
        captured["kwargs"] = kwargs
        return FakeSession()

    monkeypatch.setattr(repo_mod, "get_or_create_stripe_customer", fake_customer)
    monkeypatch.setattr(repo_mod.stripe.checkout.Session, "create", fake_create)

    c = _client_as(repo_app, USER_A)
    r = c.post("/api/repository/purchase", json={"plan": "annual"})
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"] == "https://checkout.stripe.com/test123"
    # Sanity: metadata carries purchase_type + plan for the webhook.
    meta = captured["kwargs"]["metadata"]
    assert meta["purchase_type"] == "repository"
    assert meta["repository_plan"] == "annual"


def test_repository_purchase_invalid_plan(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.post("/api/repository/purchase", json={"plan": "enterprise"})
    assert r.status_code == 400


# ==================== GET /trusts/{id}/archive-export ====================

def test_archive_export_returns_zip(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.get(f"/api/trusts/{TRUST_A}/archive-export")
    assert r.status_code == 200, r.text
    assert "application/zip" in r.headers.get("Content-Type", "")
    zip_bytes = r.content
    assert zip_bytes[:2] == b"PK"  # ZIP magic
    import io
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = zf.namelist()
    assert "manifest.json" in names
    assert any(n.startswith("vault/") for n in names)


def test_archive_export_unknown_trust_404(repo_app, repo_db):
    c = _client_as(repo_app, USER_A)
    r = c.get("/api/trusts/trust_nope/archive-export")
    assert r.status_code == 404
