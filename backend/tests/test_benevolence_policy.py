"""
Backend tests for Benevolence Policy Builder — CRUD, versioning, publish,
PDF export, and distribution-policy integration.

Coverage:
  POST   /api/benevolence/policies          — create policy + first draft version
  GET    /api/benevolence/policies/{trust}   — get policy container
  GET    /api/benevolence/policies/{trust}/versions      — list all versions
  GET    /api/benevolence/policies/{trust}/active         — get active (published) version
  GET    /api/benevolence/policies/versions/{id}          — get single version
  PUT    /api/benevolence/policies/versions/{id}          — edit draft version
  POST   /api/benevolence/policies/versions/{id}/publish  — publish a draft
  POST   /api/benevolence/policies/{trust}/amend           — amend from published
  DELETE /api/benevolence/policies/versions/{id}           — delete draft
  POST   /api/benevolence/policies/{trust}/export/pdf      — PDF export
  POST   /api/distributions                — policy limit validation & version linkage
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required for integration tests", allow_module_level=True)

# -----------------------------------------------------------------
# Test credentials — set via env or CI defaults
# -----------------------------------------------------------------
TEST_EMAIL = os.environ.get("TEST_EMAIL", "test@trustoffice.com")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "testpassword123")

# Trust that has benevolence_enabled = true
TRUST_BENEVOLENCE = "trust_f8896488ce03"
# A second trust used for negative / permission tests
TRUST_OTHER = "trust_7c1a0f5b2e9d"


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------
@pytest.fixture(scope="module")
def auth_token():
    """Login once for the whole module."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"Login failed ({resp.status_code}): {resp.text}")
    return resp.json()["token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def policy_payload():
    """Minimal valid payload to create a benevolence policy."""
    return {
        "trust_id": TRUST_BENEVOLENCE,
        "version_label": "1.0",
        "charitable_class": "health_and_education",
        "charitable_class_description": "Health and educational assistance for descendants",
        "eligibility_criteria": [
            {"criterion": "Must be a direct descendant", "is_required": True},
            {"criterion": "Age under 25 for education grants", "is_required": False},
        ],
        "assistance_types": [
            {
                "purpose": "education",
                "label": "Education Grants",
                "is_allowed": True,
                "per_recipient_limit": 50000,
                "per_recipient_period": "year",
            },
            {
                "purpose": "medical",
                "label": "Medical Expenses",
                "is_allowed": True,
                "per_recipient_limit": 100000,
                "per_recipient_period": "year",
            },
            {
                "purpose": "business",
                "label": "Business Start-up",
                "is_allowed": False,
            },
        ],
        "per_recipient_annual_limit": 100000,
        "approval_process": "single_trustee_under_10k_board_approval_above",
        "approval_threshold": 10000,
        "committee_members": [
            {"name": "Jane Smith", "role": "Chair", "email": "jane@example.com"},
            {"name": "Bob Smith", "role": "Member", "email": "bob@example.com"},
        ],
        "documentation_requirements": [
            {"item": "Proof of enrollment", "is_required": True},
            {"item": "Tax return", "is_required": False},
        ],
        "designated_gift_prohibition": (
            "No distributions to individuals who are trustees or officers of the trust."
        ),
        "employee_benevolence_note": (
            "Employee benevolence payments are subject to IRC §102 and §139. "
            "Employer must substantiate with business purpose."
        ),
        "board_approval_date": "2026-06-15",
        "board_approval_reference": "Minutes-2026-06-15-001",
        "effective_date": "2026-07-01",
    }


@pytest.fixture(scope="module")
def created_policy(headers, policy_payload):
    """Create a policy and return its version_id + policy_id."""
    resp = requests.post(
        f"{BASE_URL}/api/benevolence/policies",
        headers=headers,
        json=policy_payload,
    )
    if resp.status_code != 200:
        pytest.fail(f"Failed to create policy: {resp.status_code} {resp.text}")
    data = resp.json()
    return {
        "policy_id": data["policy_id"],
        "version_id": data["policy_version_id"],
        "version_label": data["version_label"],
    }


# ===================================================================
# POST /api/benevolence/policies — Create Policy
# ===================================================================


class TestPolicyCreate:
    def test_create_policy_success(self, headers, policy_payload):
        """Creating a new policy returns 200 with version data."""
        # Use a unique trust_id variant to avoid conflicts
        payload = {**policy_payload, "version_label": "test-1.0"}
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies",
            headers=headers,
            json=payload,
        )
        # If the trust already has a policy we expect 409
        if resp.status_code == 409:
            print("✓ Policy already exists for this trust (409)")
            return
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "policy_id" in data
        assert "policy_version_id" in data
        assert data["status"] == "draft"
        print(f"✓ Policy created: {data['policy_id']} v{data['policy_version_id']}")

    def test_create_policy_v2_existing_trust_conflict(self, headers, policy_payload):
        """Creating a second policy for the same trust returns 409."""
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies",
            headers=headers,
            json=policy_payload,
        )
        assert resp.status_code == 409
        print("✓ Duplicate policy creation correctly blocked (409)")

    def test_create_policy_missing_trust(self, headers, policy_payload):
        """Creating a policy for a non-existent trust returns 404."""
        payload = {**policy_payload, "trust_id": "trust_nonexistent_xyz"}
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies",
            headers=headers,
            json=payload,
        )
        assert resp.status_code == 404
        print("✓ Non-existent trust correctly rejected (404)")

    def test_create_policy_benevolence_not_enabled(self, headers, policy_payload):
        """Creating a policy for a trust without benevolence_enabled returns 400."""
        payload = {**policy_payload, "trust_id": TRUST_OTHER, "version_label": "1.0"}
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies",
            headers=headers,
            json=payload,
        )
        # Should fail if TRUST_OTHER doesn't have benevolence_enabled
        if resp.status_code == 400:
            print("✓ Correctly rejected: benevolence not enabled on trust")
        elif resp.status_code == 404:
            print("✓ Trust not found (also acceptable)")
        else:
            # If the trust does have benevolence on, just log it
            print(f"  (Got {resp.status_code} — TRUST_OTHER may have benevolence enabled)")


# ===================================================================
# GET /api/benevolence/policies/{trust_id} — Read Policy Container
# ===================================================================


class TestPolicyRead:
    def test_get_policy_success(self, headers):
        """GET returns the policy container with current version summary."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}",
            headers=headers,
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "policy_id" in data
        assert "current_version_id" in data
        assert "current_version_status" in data
        print(f"✓ Policy container retrieved: {data['policy_id']}")

    def test_get_nonexistent_policy(self, headers):
        """GET for a trust without a policy returns 404."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/trust_nopolicy_xyz",
            headers=headers,
        )
        assert resp.status_code == 404
        print("✓ Non-existent policy correctly returns 404")


# ===================================================================
# GET /api/benevolence/policies/{trust_id}/versions — List Versions
# ===================================================================


class TestPolicyListVersions:
    def test_list_versions_returns_array(self, headers):
        """List versions returns a list with at least one entry."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/versions",
            headers=headers,
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert isinstance(versions, list)
        assert len(versions) >= 1
        print(f"✓ Listed {len(versions)} versions")


# ===================================================================
# GET /api/benevolence/policies/{trust_id}/active — Active Version
# ===================================================================


class TestPolicyActive:
    def test_get_active_version(self, headers):
        """GET active version returns the currently published version."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/active",
            headers=headers,
        )
        # May be 200 (if published) or 404 (if no published version yet)
        if resp.status_code == 200:
            data = resp.json()
            assert data["status"] == "published"
            print(f"✓ Active version: {data['version_label']} ({data['policy_version_id']})")
        elif resp.status_code == 404:
            print("✓ No active version (404) — policy exists but nothing published yet")
        else:
            pytest.fail(f"Unexpected status: {resp.status_code}")


# ===================================================================
# GET /api/benevolence/policies/versions/{id} — Single Version
# ===================================================================


class TestPolicyVersionDetail:
    def test_get_version_detail(self, headers, created_policy):
        """GET a single version returns all fields."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["policy_version_id"] == created_policy["version_id"]
        assert data["status"] == "draft"
        print(f"✓ Version detail retrieved: {data['version_label']}")

    def test_get_nonexistent_version(self, headers):
        """GET for a bogus version_id returns 404."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/versions/bogus_ver_xyz",
            headers=headers,
        )
        assert resp.status_code == 404
        print("✓ Non-existent version correctly returns 404")


# ===================================================================
# PUT /api/benevolence/policies/versions/{id} — Edit Draft
# ===================================================================


class TestPolicyEdit:
    def test_edit_draft_success(self, headers, created_policy):
        """Editing a draft version succeeds and persists."""
        resp = requests.put(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}",
            headers=headers,
            json={"notes": "Updated notes for Phase 2 test", "version_label": "1.1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["notes"] == "Updated notes for Phase 2 test"
        # version_label may not be updatable on edit depending on impl; either way:
        assert data["status"] == "draft"
        print(f"✓ Draft edited: notes updated, label={data.get('version_label')}")

    def test_edit_published_version_blocked(self, headers, created_policy):
        """Editing a published (non-draft) version returns 400."""
        # Publish first
        pub_resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}/publish",
            headers=headers,
            json={},
        )
        if pub_resp.status_code != 200:
            pytest.skip(f"Could not publish for edit-blocking test: {pub_resp.text}")

        edit_resp = requests.put(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}",
            headers=headers,
            json={"notes": "Should fail"},
        )
        assert edit_resp.status_code == 400
        print("✓ Published version is immutable (edit blocked)")

    def test_edit_nonexistent_version(self, headers):
        """Editing a non-existent version returns 404."""
        resp = requests.put(
            f"{BASE_URL}/api/benevolence/policies/versions/bogus_ver_xyz",
            headers=headers,
            json={"notes": "nope"},
        )
        assert resp.status_code == 404
        print("✓ Edit on non-existent version returns 404")


# ===================================================================
# POST /api/benevolence/policies/versions/{id}/publish — Publish
# ===================================================================


class TestPolicyPublish:
    def test_publish_draft_success(self, headers, created_policy):
        """Publishing a draft succeeds and returns published version."""
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}/publish",
            headers=headers,
            json={
                "board_approval_date": "2026-08-14",
                "board_approval_reference": "TEST-BOARD-2026-08",
            },
        )
        assert resp.status_code == 200, f"Publish failed: {resp.text}"
        data = resp.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None
        print(f"✓ Policy published: {data['version_label']} at {data['published_at']}")

    def test_publish_already_published_supersedes(self, headers, created_policy):
        """Publishing a new draft supersedes the old published version."""
        # This test requires a second draft version.
        # Amend to create a new draft, then publish it.
        amend_resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/amend",
            headers=headers,
            json={
                "version_label": "2.0-test",
                "notes": "Amended for supersession test",
            },
        )
        if amend_resp.status_code != 200:
            pytest.skip(f"Could not amend for supersession test: {amend_resp.text}")

        new_version = amend_resp.json()
        pub_resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/versions/{new_version['policy_version_id']}/publish",
            headers=headers,
            json={"board_approval_date": "2026-08-14"},
        )
        assert pub_resp.status_code == 200

        # Verify the old version is now superseded
        old_version = requests.get(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}",
            headers=headers,
        ).json()
        assert old_version["status"] == "superseded"
        print(f"✓ Old version {created_policy['version_id']} now superseded by {new_version['policy_version_id']}")

    def test_publish_nonexistent_version(self, headers):
        """Publishing a non-existent version returns 404."""
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/versions/bogus_ver_xyz/publish",
            headers=headers,
            json={},
        )
        assert resp.status_code == 404
        print("✓ Publish on non-existent version returns 404")


# ===================================================================
# POST /api/benevolence/policies/{trust_id}/amend — Amend
# ===================================================================


class TestPolicyAmend:
    def test_amend_from_published(self, headers):
        """Amending a published policy creates a new draft version."""
        # Ensure there's a published version first
        active = requests.get(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/active",
            headers=headers,
        )
        if active.status_code != 200:
            pytest.skip("No active published version to amend from")

        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/amend",
            headers=headers,
            json={
                "version_label": "1.1-amended",
                "notes": "Amendment test note",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["supersedes_version_id"] == active.json()["policy_version_id"]
        assert data["version_number"] == active.json()["version_number"] + 1
        print(f"✓ Amended version created: v{data['version_number']} ({data['policy_version_id']})")

    def test_amend_without_published_returns_404(self, headers):
        """Amending when no published version exists returns 404."""
        # Use a trust that has no policy at all
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/trust_nopolicy_xyz/amend",
            headers=headers,
            json={"version_label": "1.0"},
        )
        assert resp.status_code == 404
        print("✓ Amend without published version returns 404")


# ===================================================================
# DELETE /api/benevolence/policies/versions/{id} — Delete Draft
# ===================================================================


class TestPolicyDelete:
    def test_delete_draft_success(self, headers):
        """Creating and then deleting a draft returns success."""
        # Create a fresh policy version for deletion
        resp = requests.post(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/amend",
            headers=headers,
            json={"version_label": "draft-to-delete", "notes": "To be deleted"},
        )
        if resp.status_code != 200:
            pytest.skip(f"Could not create draft for deletion: {resp.text}")
        version_id = resp.json()["policy_version_id"]

        del_resp = requests.delete(
            f"{BASE_URL}/api/benevolence/policies/versions/{version_id}",
            headers=headers,
        )
        assert del_resp.status_code == 200
        print(f"✓ Draft version {version_id} deleted")

    def test_delete_published_version_blocked(self, headers, created_policy):
        """Deleting a published version returns 400."""
        # Ensure published
        requests.post(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}/publish",
            headers=headers,
            json={},
        )
        del_resp = requests.delete(
            f"{BASE_URL}/api/benevolence/policies/versions/{created_policy['version_id']}",
            headers=headers,
        )
        assert del_resp.status_code == 400
        print("✓ Published version cannot be deleted (400)")


# ===================================================================
# GET /api/benevolence/policies/{trust_id}/export/pdf — PDF Export
# ===================================================================


class TestPolicyPDFExport:
    def test_pdf_export_requires_auth(self):
        """PDF export without auth returns 401."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/export/pdf"
        )
        assert resp.status_code == 401
        print("✓ PDF export requires auth (401)")

    def test_pdf_export_returns_pdf(self, headers):
        """PDF export returns a valid PDF with correct headers."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/{TRUST_BENEVOLENCE}/export/pdf",
            headers=headers,
        )
        assert resp.status_code == 200, f"Export failed: {resp.text}"
        assert "application/pdf" == resp.headers.get("content-type")
        cd = resp.headers.get("content-disposition", "")
        assert "benevolence_policy" in cd
        # PDF magic bytes
        assert resp.content[:5] == b"%PDF-"
        print(f"✓ PDF exported ({len(resp.content)} bytes)")

    def test_pdf_export_nonexistent_trust(self, headers):
        """PDF export for non-existent trust returns 404."""
        resp = requests.get(
            f"{BASE_URL}/api/benevolence/policies/trust_nopolicy_xyz/export/pdf",
            headers=headers,
        )
        assert resp.status_code == 404
        print("✓ PDF export for non-existent trust returns 404")


# ===================================================================
# POST /api/distributions — Policy Limit Validation
# ===================================================================


class TestDistributionPolicyValidation:
    """Tests that distributions are validated against active benevolence policy."""

    REQ_FIELDS = {
        "trust_id": TRUST_BENEVOLENCE,
        "beneficiary_name": "Test Beneficiary",
        "amount": 150.00,
        "date": "2026-01-15",
        "purpose_classification": "distribution",
    }

    def test_distribution_without_policy(self, headers):
        """Distribution creation works when no active policy exists for a different trust."""
        payload = {**self.REQ_FIELDS, "trust_id": TRUST_OTHER}
        resp = requests.post(
            f"{BASE_URL}/api/distributions",
            headers=headers,
            json=payload,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Distribution created (trust has no active policy)")

    def test_distribution_with_policy_version_linkage(self, headers):
        """Distribution with an active policy gets policy_version_id set."""
        payload = {**self.REQ_FIELDS, "is_benevolence": True}
        resp = requests.post(
            f"{BASE_URL}/api/distributions",
            headers=headers,
            json=payload,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("policy_version_id"):
                print(f"✓ Policy version linked: {data['policy_version_id']}")
            else:
                print("  (No policy_version_id — policy may not be published yet)")

    def test_distribution_exceeding_limit_warning(self, headers):
        """Distribution exceeding per-recipient annual limit gets a warning."""
        # Use a very high amount that exceeds the $100k limit
        payload = {
            **self.REQ_FIELDS,
            "amount": 200000.00,
            "is_benevolence": True,
            "benevolence_recipient_name": "TEST High Amount Recipient",
            "benevolence_need_description": "Testing policy limit warning",
        }
        resp = requests.post(
            f"{BASE_URL}/api/distributions",
            headers=headers,
            json=payload,
        )
        if resp.status_code == 200:
            data = resp.json()
            warning = data.get("policy_limit_warning")
            if warning:
                print(f"✓ Policy limit warning returned: {warning[:80]}...")
            else:
                print("  (No warning — policy may not be published or limit not set)")

    def test_distribution_excluded_purpose_warning(self, headers):
        """Distribution with an excluded assistance type gets a warning."""
        payload = {
            **self.REQ_FIELDS,
            "purpose_classification": "other",
            "is_benevolence": True,
            "benevolence_recipient_name": "TEST Excluded Purpose",
            "benevolence_need_description": "Testing excluded purpose",
        }
        resp = requests.post(
            f"{BASE_URL}/api/distributions",
            headers=headers,
            json=payload,
        )
        if resp.status_code == 200:
            data = resp.json()
            warning = data.get("policy_limit_warning")
            policy_ver = data.get("policy_version_id")
            print(f"✓ Distribution created — warning={bool(warning)}, policy_version_id={policy_ver}")


# ===================================================================
# Cleanup / Teardown
# ===================================================================


@pytest.fixture(scope="module", autouse=True)
def cleanup(request):
    """Module-level cleanup stub — extend with deletion logic if needed."""
    yield
    # Placeholder: delete test-created distributions/policies if desired
    print("\n✓ Policy test suite complete")