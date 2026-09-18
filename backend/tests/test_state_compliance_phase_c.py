"""State Compliance Phase C tests (JOB-20260917-TO-STATE-COMPLIANCE-C1).

Verifies:
1. Accounting prefill renders real figures from seeded transactions.
2. Delivery log add/update endpoints work (documents_log).
3. GET per-trust state-compliance response includes documents_log.
4. Auth: another user cannot PATCH someone else' log.
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-state-compliance-tests")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from database import db as real_db
import routers.state_compliance as sc
import routers.beneficiary_reports as beneficiary_reports
import services.beneficiary_report_service as brs


class FakeCollection:
    """Minimal in-memory MongoDB collection substitute."""

    def __init__(self):
        self.docs = {}
        self._seq = 0

    def _next_id(self):
        self._seq += 1
        return f"sc_{self._seq:012x}"

    async def find_one(self, query, projection=None):
        if "$or" in query:
            for sub in query["$or"]:
                doc = await self.find_one(sub, projection)
                if doc:
                    return dict(doc)
            return None
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    def find(self, query, projection=None):
        # Mirror real motor semantics: find() returns a cursor synchronously,
        # cursor supports .sort() (returns self) and async .to_list().
        results = []
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                results.append(dict(doc))
        return FakeCursor(results)

    async def count_documents(self, query):
        return sum(1 for d in self.docs.values() if all(d.get(k) == v for k, v in query.items()))

    async def insert_one(self, doc):
        _id = doc.get("_id") or self._next_id()
        doc["_id"] = _id
        self.docs[_id] = dict(doc)
        return MagicMock()

    async def insert_many(self, docs):
        for doc in docs:
            _id = doc.get("_id") or self._next_id()
            doc["_id"] = _id
            self.docs[_id] = dict(doc)
        return MagicMock()

    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        if doc is None:
            if upsert:
                new_doc = dict(query)
                for k, v in update.get("$set", {}).items():
                    new_doc[k] = v
                for k, v in update.get("$setOnInsert", {}).items():
                    new_doc[k] = v
                for k, v in update.get("$push", {}).items():
                    new_doc[k] = [v]
                self.docs[new_doc.get("_id", self._next_id())] = new_doc
                return MagicMock(upserted_id=new_doc.get("_id"))
            return MagicMock()
        for k, v in update.get("$set", {}).items():
            doc[k] = v
        for k, v in update.get("$setOnInsert", {}).items():
            doc.setdefault(k, v)
        for k, v in update.get("$push", {}).items():
            doc.setdefault(k, []).append(v)
        self.docs[doc["_id"]] = dict(doc)
        m = MagicMock()
        m.upserted_id = None
        return m

    def to_list(self, limit):
        return [dict(d) for d in self.docs.values()][:limit]


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        # Return self so .sort(...).to_list(...) chains work.
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    async def to_list(self, limit):
        return self._docs[:limit]


@pytest.fixture
def fake_db(monkeypatch):
    class FakeDB:
        pass

    db = FakeDB()
    db.state_compliance_profiles = FakeCollection()
    db.trusts = FakeCollection()
    db.trust_state_compliance = FakeCollection()
    db.minutes_templates = FakeCollection()
    db.vault_documents = FakeCollection()
    db.transactions = FakeCollection()
    db.trust_units_settings = FakeCollection()
    db.trust_unit_certificates = FakeCollection()
    db.class_beneficiaries = FakeCollection()
    db.schedule_a_items = FakeCollection()

    monkeypatch.setattr("database.db", db)
    monkeypatch.setattr(sc, "db", db)
    monkeypatch.setattr(beneficiary_reports, "db", db)
    monkeypatch.setattr(brs, "db", db)
    return db


async def _seed_state_profiles(db):
    profiles = [
        {"_id": "CA", "state_code": "CA", "state_name": "California", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "utc_adopted": "no", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    ]
    for p in profiles:
        await db.state_compliance_profiles.insert_one(p)


async def _seed_trust(db, trust_id, state_code, user_id="user_1"):
    await db.trusts.insert_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "state_code": state_code,
        "name": "Test Trust",
        "trust_type": "revocable",
        "created_at": "2025-01-01T00:00:00+00:00",
    })


async def _seed_compliance(db, trust_id, state_code):
    await db.trust_state_compliance.insert_one({
        "trust_id": trust_id,
        "state_code": state_code,
        "notice_last_sent": None,
        "notice_next_due": None,
        "accounting_last_sent": None,
        "accounting_next_due": None,
        "compliance_score": 100,
        "documents_log": [],
    })


class TestAccountingPrefillFromTransactions:
    """Phase C Part 1: accounting PDF prefills from real trust transaction data."""

    @pytest.mark.asyncio
    async def test_generate_report_uses_transaction_data(self, fake_db):
        """generate_beneficiary_report computes income/expense/distribution totals from transactions."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_txn", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_txn", "CA")

        # Seed transactions with known figures
        await fake_db.transactions.insert_one({
            "trust_id": "trust_txn",
            "user_id": "user_1",
            "date": "2026-06-01",
            "amount": 5000.0,
            "direction": "inflow",
            "governance_classification": "Capital Contribution",
            "source_account": "bank_account_1",
            "destination_account": "",
            "purpose_memo": "Initial funding",
        })
        await fake_db.transactions.insert_one({
            "trust_id": "trust_txn",
            "user_id": "user_1",
            "date": "2026-06-15",
            "amount": 2000.0,
            "direction": "outflow",
            "governance_classification": "Distribution",
            "source_account": "",
            "destination_account": "beneficiary_alice",
            "purpose_memo": "Quarterly distribution",
        })
        await fake_db.transactions.insert_one({
            "trust_id": "trust_txn",
            "user_id": "user_1",
            "date": "2026-07-01",
            "amount": 1500.0,
            "direction": "outflow",
            "governance_classification": "Operational Expense",
            "source_account": "bank_account_1",
            "destination_account": "",
            "purpose_memo": "Tax payment",
        })

        result = await brs.generate_beneficiary_report("trust_txn", "user_1")
        assert result is not None
        assert result["trust_name"] == "Test Trust"

        # Real figures from the seeded transactions must appear in the response
        fs = result["financial_summary"]
        assert fs["total_income"] == 5000.0       # Capital Contribution inflow
        assert fs["total_expenses"] == 1500.0     # Operational Expense outflow
        assert fs["total_distributions"] == 2000.0  # Distribution outflow
        # Period start falls back to trust created date
        assert fs["period_start"] == "2025-01-01"
        assert fs["period_end"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # The stored PDF must contain the rendered figures as text
        doc = await fake_db.vault_documents.find_one({"trust_id": "trust_txn", "user_id": "user_1"})
        assert doc is not None
        pdf_bytes = doc["file_content"]
        assert pdf_bytes[:5] == b"%PDF-"
        import base64
        import zlib
        text = ""
        for chunk in re.findall(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
            raw = chunk.rstrip(b"\r\n")
            try:
                raw = base64.a85decode(raw, adobe=True)
            except Exception:
                pass  # uncompressed stream
            try:
                text += zlib.decompress(raw).decode("latin-1", errors="ignore")
            except Exception:
                text += raw.decode("latin-1", errors="ignore")
        assert "Financial Summary" in text
        assert "5,000.00" in text          # income rendered
        assert "2,000.00" in text          # distributions rendered
        assert "1,500.00" in text          # expenses rendered

    @pytest.mark.asyncio
    async def test_generate_report_no_transactions_returns_zeroes(self, fake_db):
        """When no transactions exist, financial summary shows zero/None values."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_empty", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_empty", "CA")

        result = await brs.generate_beneficiary_report("trust_empty", "user_1")
        assert result is not None
        fs = result["financial_summary"]
        assert fs["total_income"] == 0.0
        assert fs["total_distributions"] == 0.0
        assert fs["remaining_balance"] is None  # corpus blank -> no remaining figure

    @pytest.mark.asyncio
    async def test_starting_corpus_from_schedule_a(self, fake_db):
        """Starting corpus comes from active Schedule A assets conveyed by period start."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_corpus", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_corpus", "CA")

        # Active asset conveyed before period start (trust created 2025-01-01)
        await fake_db.schedule_a_items.insert_one({
            "item_id": "asset_1", "trust_id": "trust_corpus", "user_id": "user_1",
            "description": "Primary Residence", "approximate_value": 650000.0,
            "date_conveyed": "2020-01-15", "status": "active",
        })
        # Disposed asset must be excluded
        await fake_db.schedule_a_items.insert_one({
            "item_id": "asset_2", "trust_id": "trust_corpus", "user_id": "user_1",
            "description": "Old car", "approximate_value": 38500.0,
            "date_conveyed": "2019-06-01", "status": "disposed",
        })
        # Active asset conveyed AFTER period start must be excluded
        await fake_db.schedule_a_items.insert_one({
            "item_id": "asset_3", "trust_id": "trust_corpus", "user_id": "user_1",
            "description": "New condo", "approximate_value": 425000.0,
            "date_conveyed": "2025-06-01", "status": "active",
        })

        result = await brs.generate_beneficiary_report("trust_corpus", "user_1")
        fs = result["financial_summary"]
        assert fs["starting_corpus"] == 650000.0
        assert fs["remaining_balance"] == 650000.0

    @pytest.mark.asyncio
    async def test_period_filters_transactions(self, fake_db):
        """Transactions dated before the period start are excluded from totals."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_period", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_period", "CA")
        # Set accounting_last_sent so period_start = 2026-01-01
        await fake_db.trust_state_compliance.update_one(
            {"trust_id": "trust_period", "state_code": "CA"},
            {"$set": {"accounting_last_sent": "2026-01-01T00:00:00+00:00"}},
        )

        await fake_db.transactions.insert_one({
            "trust_id": "trust_period", "user_id": "user_1",
            "date": "2025-06-01", "amount": 9999.0, "direction": "inflow",
            "governance_classification": "Capital Contribution",
        })
        await fake_db.transactions.insert_one({
            "trust_id": "trust_period", "user_id": "user_1",
            "date": "2026-02-01", "amount": 750.0, "direction": "inflow",
            "governance_classification": "Capital Contribution",
        })

        result = await brs.generate_beneficiary_report("trust_period", "user_1")
        fs = result["financial_summary"]
        assert fs["period_start"] == "2026-01-01"
        assert fs["total_income"] == 750.0  # only in-period txn counted


class TestDocumentsLogEndpoints:
    """Phase C Part 2: delivery log add/update endpoints."""

    @pytest.mark.asyncio
    async def test_upsert_document_log_entry(self, fake_db):
        """PATCH documents-log with action=upsert appends a new entry."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_doc", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_doc", "CA")

        now = datetime.now(timezone.utc).isoformat()
        result = await sc.update_documents_log(
            "trust_doc",
            {
                "doc_id": "doc_test123",
                "kind": "accounting",
                "generated_at": now,
                "method": "beneficiary-reports",
                "action": "upsert",
            },
            {"user_id": "user_1", "is_admin": False},
        )

        assert result is not None
        log = result.get("documents_log", [])
        assert len(log) == 1
        assert log[0]["doc_id"] == "doc_test123"
        assert log[0]["kind"] == "accounting"
        assert log[0]["method"] == "beneficiary-reports"

    @pytest.mark.asyncio
    async def test_mark_sent_updates_entry(self, fake_db):
        """PATCH documents-log with action=mark_sent sets sent_at."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_sent", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_sent", "CA")

        now = datetime.now(timezone.utc).isoformat()
        await sc.update_documents_log(
            "trust_sent",
            {"doc_id": "doc_sent1", "kind": "notice", "generated_at": now, "method": "minutes", "action": "upsert"},
            {"user_id": "user_1", "is_admin": False},
        )

        sent_time = datetime.now(timezone.utc).isoformat()
        result = await sc.update_documents_log(
            "trust_sent",
            {"doc_id": "doc_sent1", "action": "mark_sent", "sent_at": sent_time},
            {"user_id": "user_1", "is_admin": False},
        )

        log = result.get("documents_log", [])
        assert len(log) == 1
        assert log[0]["sent_at"] == sent_time

    @pytest.mark.asyncio
    async def test_mark_delivered_updates_entry(self, fake_db):
        """PATCH documents-log with action=mark_delivered sets delivered_at."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_del", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_del", "CA")

        now = datetime.now(timezone.utc).isoformat()
        await sc.update_documents_log(
            "trust_del",
            {"doc_id": "doc_del1", "kind": "notice", "generated_at": now, "method": "minutes", "action": "upsert"},
            {"user_id": "user_1", "is_admin": False},
        )

        delivered_time = datetime.now(timezone.utc).isoformat()
        result = await sc.update_documents_log(
            "trust_del",
            {"doc_id": "doc_del1", "action": "mark_delivered", "delivered_at": delivered_time},
            {"user_id": "user_1", "is_admin": False},
        )

        log = result.get("documents_log", [])
        assert len(log) == 1
        assert log[0]["delivered_at"] == delivered_time

    @pytest.mark.asyncio
    async def test_another_user_cannot_patch(self, fake_db):
        """PATCH documents-log for a trust owned by another user returns 404."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_other", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_other", "CA")

        now = datetime.now(timezone.utc).isoformat()
        with pytest.raises(Exception):  # HTTPException(404) raised for non-owned trust
            await sc.update_documents_log(
                "trust_other",
                {"doc_id": "doc_other1", "kind": "notice", "generated_at": now, "method": "minutes", "action": "upsert"},
                {"user_id": "user_2", "is_admin": False},
            )


class TestGetIncludesDocumentsLog:
    """Phase C Part 2c: GET per-trust state-compliance includes documents_log."""

    @pytest.mark.asyncio
    async def test_get_includes_documents_log(self, fake_db):
        """GET /trusts/{trust_id}/state-compliance returns documents_log field."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_get_log", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_get_log", "CA")

        # Seed a documents_log entry
        now = datetime.now(timezone.utc).isoformat()
        await fake_db.trust_state_compliance.update_one(
            {"trust_id": "trust_get_log", "state_code": "CA"},
            {"$set": {"documents_log": [
                {"doc_id": "doc_log1", "kind": "notice", "generated_at": now, "method": "minutes", "sent_at": now, "delivered_at": None, "tracking_ref": "", "notes": "", "updated_at": now}
            ]}},
        )

        result = await sc.get_trust_state_compliance("trust_get_log", {"user_id": "user_1"})

        assert result is not None
        assert "documents_log" in result["compliance"]
        assert len(result["compliance"]["documents_log"]) == 1
        assert result["compliance"]["documents_log"][0]["doc_id"] == "doc_log1"

    @pytest.mark.asyncio
    async def test_get_empty_documents_log(self, fake_db):
        """GET returns empty documents_log when none exist."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_empty_log", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_empty_log", "CA")

        result = await sc.get_trust_state_compliance("trust_empty_log", {"user_id": "user_1"})

        assert result is not None
        assert result["compliance"]["documents_log"] == []


class TestGenerationAutoLog:
    """Phase C Part 2: generating a notice/accounting auto-creates a delivery-log entry."""

    @pytest.mark.asyncio
    async def test_generate_report_appends_documents_log(self, fake_db):
        """Accounting generation pushes an accounting entry into documents_log."""
        import routers.beneficiary_reports as br_router

        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_autolog_acct", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_autolog_acct", "CA")

        class _User:  # require_write_access-shaped principal
            user_id = "user_1"

        result = await br_router.generate_report("trust_autolog_acct", {"user_id": "user_1"})
        assert result["doc_id"]

        compliance = await fake_db.trust_state_compliance.find_one(
            {"trust_id": "trust_autolog_acct", "state_code": "CA"}
        )
        log = compliance["documents_log"]
        assert len(log) == 1
        entry = log[0]
        assert entry["doc_id"] == result["doc_id"]
        assert entry["kind"] == "accounting"
        assert entry["generated_at"]
        assert entry["sent_at"] is None and entry["delivered_at"] is None

    @pytest.mark.asyncio
    async def test_notice_generation_appends_documents_log(self, fake_db):
        """Notice generation (minutes) pushes a notice entry into documents_log."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_autolog_notice", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_autolog_notice", "CA")

        entry = await sc.log_compliance_document(
            "trust_autolog_notice", "user_1", "min_notice1", "notice",
            method="minutes-templates", notes="Generated from Beneficiary Notice template",
        )
        assert entry is not None

        compliance = await fake_db.trust_state_compliance.find_one(
            {"trust_id": "trust_autolog_notice", "state_code": "CA"}
        )
        log = compliance["documents_log"]
        assert len(log) == 1
        assert log[0]["doc_id"] == "min_notice1"
        assert log[0]["kind"] == "notice"

    @pytest.mark.asyncio
    async def test_log_compliance_document_no_state_is_noop(self, fake_db):
        """Trust without state_code: auto-log is a no-op, no record created."""
        await _seed_trust(fake_db, "trust_nostate", None, "user_1")

        entry = await sc.log_compliance_document(
            "trust_nostate", "user_1", "doc_x", "accounting"
        )
        assert entry is None
        assert fake_db.trust_state_compliance.docs == {}

    @pytest.mark.asyncio
    async def test_then_mark_sent_then_delivered_full_flow(self, fake_db):
        """Generated -> Sent -> Delivered lifecycle through the PATCH endpoint."""
        await _seed_state_profiles(fake_db)
        await _seed_trust(fake_db, "trust_flow", "CA", "user_1")
        await _seed_compliance(fake_db, "trust_flow", "CA")

        await sc.log_compliance_document("trust_flow", "user_1", "doc_flow1", "notice")
        result = await sc.update_documents_log(
            "trust_flow",
            {"doc_id": "doc_flow1", "action": "mark_sent", "method": "mail"},
            {"user_id": "user_1", "is_admin": False},
        )
        result = await sc.update_documents_log(
            "trust_flow",
            {"doc_id": "doc_flow1", "action": "mark_delivered"},
            {"user_id": "user_1", "is_admin": False},
        )
        log = result["documents_log"]
        entry = next(e for e in log if e["doc_id"] == "doc_flow1")
        assert entry["sent_at"] and entry["delivered_at"]
