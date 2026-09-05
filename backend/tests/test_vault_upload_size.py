"""
Unit tests for the vault upload size-limit path (Kenneth's 39MB bug, 2026-09-04).

Verifies the backend rejects oversized files with HTTP 413 + an actionable
error message — BEFORE the fix, a 39MB PDF passed the Content-Length
pre-check (chunked/streamed requests omit Content-Length), then failed the
16MB BSON check with a vague 400. The frontend also showed errors only as a
transient toast, so the failure was silent end-to-end.

Run: pytest backend/tests/test_vault_upload_size.py -v
(safe on localhost — conftest.py blocks prod hosts; this file targets the
in-process TestClient only)
"""

import io
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# database.py / dependencies.py read these at import time — set dummies first.
# (Test never exercises real Mongo or JWT.)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-unit-tests")


def _make_pdf_bytes(size_bytes: int) -> bytes:
    """Build a real (minimal) PDF padded to the requested size."""
    header = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    trailer = b"\ntrailer<</Root 1 0 R>>\n%%EOF"
    pad = size_bytes - len(header) - len(trailer)
    assert pad > 0, "size too small for a minimal PDF"
    return header + b"0" * pad + trailer


class FakeCollection:
    def __init__(self, find_one_result=None):
        self._find_one_result = find_one_result
        self.last_record = None

    async def find_one(self, *a, **k):
        return self._find_one_result

    async def insert_one(self, record):
        self.last_record = record
        return None

    async def update_one(self, *a, **k):
        return None


class FakeDB:
    """Any-collection-access Mongo stub — the upload flow touches several."""

    def __init__(self):
        # Trust lookup must succeed so the request reaches the size gate.
        self.trusts = FakeCollection(find_one_result={"trust_id": "t1", "user_id": "test_user_1"})
        self.vault_documents = FakeCollection()
        self.trust_document_analysis = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col


@pytest.fixture
def fake_db(monkeypatch):
    import database
    import routers.vault as vault
    import utils.audit as audit
    import trust_doc_analyzer

    db = FakeDB()
    # vault.py does `from database import db` — patch the name the router bound.
    monkeypatch.setattr(vault, "db", db)

    # Audit + AI-analysis touch the real Motor client, whose event loop dies
    # between tests (Event loop is closed). Both are out of scope here.
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(audit, "log_audit_event", _noop)
    monkeypatch.setattr(vault, "log_audit_event", _noop)
    monkeypatch.setattr(trust_doc_analyzer, "analyze_trust_document", _noop)
    return db


@pytest.fixture
def client(fake_db, monkeypatch):
    """FastAPI TestClient with auth + database stubbed out."""
    import dependencies

    fake_user = {"user_id": "test_user_1", "email": "qa@trustoffice.app"}

    async def fake_get_current_user():
        return fake_user

    async def fake_require_write_access():
        return fake_user

    import routers.vault as vault

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.include_router(vault.router, prefix="/api")
    # Router captured the real Depends at decoration time — override at app level.
    test_app.dependency_overrides[dependencies.get_current_user] = fake_get_current_user
    test_app.dependency_overrides[dependencies.require_write_access] = fake_require_write_access
    return TestClient(test_app)


class TestOversizedUploadRejected:
    def test_39mb_pdf_rejected_413_with_actionable_message(self, client):
        """A 39MB text-only PDF (nothing to recompress) gets 413 + actionable message."""
        big_pdf = _make_pdf_bytes(39 * 1024 * 1024)
        resp = client.post(
            "/api/trusts/t1/vault/upload",
            files={"file": ("trust-declaration.pdf", io.BytesIO(big_pdf), "application/pdf")},
            data={"title": "Trust Declaration", "category": "trust_instrument"},
        )
        assert resp.status_code == 413, f"got {resp.status_code}: {resp.text[:300]}"
        detail = resp.json()["detail"]
        assert "39" in detail and "16MB" in detail
        assert "compress" in detail.lower()
        assert "Link External" in detail

    def test_39mb_pdf_not_saved_to_vault(self, client, fake_db):
        """No partial write: the oversized document must not reach the database."""
        big_pdf = _make_pdf_bytes(39 * 1024 * 1024)
        resp = client.post(
            "/api/trusts/t1/vault/upload",
            files={"file": ("trust-declaration.pdf", io.BytesIO(big_pdf), "application/pdf")},
            data={"title": "Trust Declaration", "category": "trust_instrument"},
        )
        assert resp.status_code == 413
        assert getattr(fake_db.vault_documents, "last_record", None) is None

    def test_oversized_non_pdf_rejected_413(self, client):
        blob = b"x" * (17 * 1024 * 1024)  # non-PDF over 16MB
        resp = client.post(
            "/api/trusts/t1/vault/upload",
            files={"file": ("notes.txt", io.BytesIO(blob), "text/plain")},
            data={"title": "Notes"},
        )
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert "17.0MB" in detail
        assert "Link External" in detail

    def test_error_message_numbers_match_file(self, client):
        size = 22 * 1024 * 1024
        big_pdf = _make_pdf_bytes(size)
        resp = client.post(
            "/api/trusts/t1/vault/upload",
            files={"file": ("big.pdf", io.BytesIO(big_pdf), "application/pdf")},
            data={"title": "Big"},
        )
        assert resp.status_code == 413
        assert f"{size / (1024*1024):.1f}MB" in resp.json()["detail"]


class TestDeepCompressionLadder:
    def test_39mb_image_pdf_compressed_and_stored(self, client, fake_db):
        """A 39MB scanned-style PDF (big embedded image) is auto-compressed under 16MB and stored."""
        import pymupdf

        # Build an image-heavy PDF: 20 pages, each with a large noisy JPEG
        # (JPEG-encoded so insert_image accepts it; noise so deflate can't shrink it).
        import random
        from io import BytesIO
        from PIL import Image
        rng = random.Random(42)
        doc = pymupdf.open()
        for _ in range(20):
            page = doc.new_page(width=612, height=792)
            # 1500x1900 noise RGB image ≈ 1.8MB raw, incompressible by deflate
            img = Image.new("RGB", (1500, 1900))
            img.putdata([(rng.getrandbits(8), rng.getrandbits(8), rng.getrandbits(8)) for _ in range(1500 * 1900)])
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=95)  # high q → big, still lossy-compressible by rewriter
            page.insert_image(page.rect, stream=buf.getvalue())
        pdf_bytes = doc.tobytes(deflate=False)
        doc.close()
        assert len(pdf_bytes) > 25 * 1024 * 1024, f"test fixture too small: {len(pdf_bytes)}"

        resp = client.post(
            "/api/trusts/t1/vault/upload",
            files={"file": ("scanned-trust.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            # category 'other' → skips the AI-analysis background task (which would
            # outlive this test's event loop and break the next test); the
            # compression ladder under test runs regardless of category.
            data={"title": "Scanned Trust", "category": "other"},
        )
        assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:300]}"
        saved = getattr(fake_db.vault_documents, "last_record", None)
        assert saved is not None
        assert len(saved["file_content"]) <= 16 * 1024 * 1024
        assert saved["file_content"][:4] == b"%PDF"  # still a valid PDF

    def test_101mb_pdf_rejected_at_hard_gate(self, client, fake_db):
        """Over the 100MB accept limit → 413 with the 100MB message, no compression attempt."""
        big_pdf = _make_pdf_bytes(101 * 1024 * 1024)
        resp = client.post(
            "/api/trusts/t1/vault/upload",
            files={"file": ("huge.pdf", io.BytesIO(big_pdf), "application/pdf")},
            data={"title": "Huge", "category": "trust_instrument"},
        )
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert "100MB" in detail
        assert getattr(fake_db.vault_documents, "last_record", None) is None


class TestNormalUploadStillWorks:
    def test_small_pdf_accepted(self, client, fake_db):
        small_pdf = _make_pdf_bytes(200 * 1024)
        resp = client.post(
            "/api/trusts/t1/vault/upload",
            files={"file": ("trust.pdf", io.BytesIO(small_pdf), "application/pdf")},
            data={"title": "Trust", "category": "trust_instrument"},
        )
        assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:300]}"
        body = resp.json()
        assert body.get("doc_id", "").startswith("doc_")

        saved = getattr(fake_db.vault_documents, "last_record", None)
        assert saved is not None
        assert saved["file_content"] == small_pdf
        assert saved["title"] == "Trust"