"""
State deep-knowledge router tests (2026-09-16).

Verifies the endpoint that surfaces the 10 per-state deep guides
(backend/KNOWLEDGE/18-state-compliance-<state>.md):

1. GET /api/state-compliance/deep-knowledge returns one entry per guide
   (10 states), sorted by state_name, with id/state_code/state_name/title/summary.
2. GET /api/state-compliance/deep-knowledge/{state_code} returns the full
   markdown (title 'Trust Compliance: <State>', body contains 'Trust Compliance:').
3. Detail for a state without a guide -> 404.
4. Unauthenticated requests are rejected (401/403).

Pure in-process: a minimal FastAPI app mounts only this router; auth is
exercised via the real dependency (no override) for the 401 case and via
app.dependency_overrides for the authenticated cases (mirrors
test_tenant_isolation.py).
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-state-deep-knowledge-tests")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import dependencies  # noqa: E402
import routers.state_deep_knowledge as sdk  # noqa: E402

USER = {"user_id": "user_1", "email": "test@trustoffice.app", "is_admin": False}


@pytest.fixture(scope="module")
def app():
    a = FastAPI()
    a.include_router(sdk.router, prefix="/api")
    return a


@pytest.fixture(scope="module")
def authed_client(app):
    def fake_current():
        return USER

    app.dependency_overrides[dependencies.get_current_user] = fake_current
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def unauthed_client(app):
    c = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(dependencies.get_current_user, None)
    return c


class TestListDeepKnowledge:
    def test_returns_50_entries_sorted_by_state_name(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 50

        names = [i["state_name"] for i in items]
        assert names == sorted(names)

        expected_codes = {
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        }
        assert {i["state_code"] for i in items} == expected_codes

        for item in items:
            assert item["id"].startswith("18-state-compliance-")
            assert item["title"].startswith("Trust Compliance:")
            assert len(item["summary"]) <= 300 and item["summary"]

    def test_every_state_has_trust_compliance_title(self, authed_client):
        items = authed_client.get("/api/state-compliance/deep-knowledge").json()
        by_code = {i["state_code"]: i for i in items}
        assert by_code["CA"]["title"] == "Trust Compliance: California"
        assert by_code["NY"]["title"] == "Trust Compliance: New York"
        assert by_code["SD"]["state_name"] == "South Dakota"


class TestDeepKnowledgeDetail:
    def test_detail_returns_full_markdown(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge/CA")
        assert r.status_code == 200
        body = r.json()
        assert body["state_code"] == "CA"
        assert body["state_name"] == "California"
        assert body["title"] == "Trust Compliance: California"
        assert "Trust Compliance:" in body["markdown"]
        assert "## State Income Tax on Trusts" in body["markdown"]

    def test_detail_is_case_insensitive(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge/ny")
        assert r.status_code == 200
        assert r.json()["state_code"] == "NY"

    def test_detail_404_for_uncovered_state(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge/XX")
        assert r.status_code == 404


class TestAuthRequired:
    def test_unauthenticated_list_rejected(self, app, unauthed_client):
        r = unauthed_client.get("/api/state-compliance/deep-knowledge")
        assert r.status_code in (401, 403)

    def test_unauthenticated_detail_rejected(self, unauthed_client):
        r = unauthed_client.get("/api/state-compliance/deep-knowledge/CA")
        assert r.status_code in (401, 403)

class TestCaseTolerantKnowledgeDir:
    """Regression: prod container checks out lowercase `knowledge/` (git index
    spelling) while macOS working copies may have `KNOWLEDGE/` on disk. The
    router must resolve the directory regardless of on-disk casing.

    macOS FS is case-insensitive, so 'KNOWLEDGE' and 'knowledge' are the same
    physical directory there; the ordering assertions below only hold on
    case-sensitive filesystems (like the Linux build container). We detect
    the FS at runtime and assert the meaningful contract in each case."""

    @staticmethod
    def _fs_case_insensitive(tmp_path):
        """True when a path can be reached under different casing (macOS)."""
        import os
        probe = tmp_path / "caseprobe_xyz"
        probe.mkdir()
        return os.path.exists(str(tmp_path / "CASEPROBE_XYZ"))

    def _copy_guides(self, dest):
        import shutil
        dest.mkdir(parents=True, exist_ok=True)
        for f in sdk.KNOWLEDGE_DIR.glob("18-state-compliance-*.md"):
            shutil.copy(f, dest / f.name)

    def test_resolver_finds_lowercase_dir(self, tmp_path):
        lower = tmp_path / "knowledge"
        self._copy_guides(lower)
        resolved = sdk._knowledge_dir(tmp_path)
        assert resolved.is_dir()
        assert len(list(resolved.glob("18-state-compliance-*.md"))) >= 10
        if not self._fs_case_insensitive(tmp_path):
            # Linux prod condition: only lowercase exists, must be chosen
            assert resolved.name == "knowledge"

    def test_resolver_prefers_uppercase_when_both(self, tmp_path):
        for name in ("KNOWLEDGE", "knowledge"):
            self._copy_guides(tmp_path / name)
        resolved = sdk._knowledge_dir(tmp_path)
        assert resolved.is_dir()
        if not self._fs_case_insensitive(tmp_path):
            assert resolved.name == "KNOWLEDGE"

    def test_resolver_falls_back_to_lowercase_when_missing(self, tmp_path):
        resolved = sdk._knowledge_dir(tmp_path)
        assert resolved.name == "knowledge"
        assert not resolved.exists()
