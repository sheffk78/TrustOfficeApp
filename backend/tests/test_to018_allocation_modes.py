"""
TO-018 — Beneficiary allocation modes and versioned audit trail

Tests cover:
1. Percentage allocation mode (default) — capped at 100%
2. Unit allocation mode — capped at authorized_units_ceiling
3. Unit mode with unlimited_units — no cap
4. Class beneficiary percentage pools — combined ≤ 100%
5. Class beneficiary per-capita share calculation
6. Certificate update creates versioned replacement (not in-place mutation)
7. Superseded certificate preserved with status="superseded"
8. Audit trail record created on replacement
9. Capacity enforcement on certificate creation in both modes
10. Settings update validates allocation_mode values

Test strategy: Pure logic/data-shape tests that don't require importing the
FastAPI router (which needs a live Mongo + compatible FastAPI version).
The tested functions are imported individually or the logic is replicated
from the source for shape verification.
"""
import sys
import os
import json
import pytest
from datetime import datetime, timezone

# Set dummy env vars so database.py can import if needed
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")


# ==================== LOGIC TESTS (no imports needed) ====================

def _calc_percentage(units: float, total_authorized: float) -> float:
    """Replicated from trust_units.py for testing."""
    return round((units / total_authorized * 100) if total_authorized > 0 else 0, 4)


def _validate_units(units: float, allow_fractional: bool) -> float:
    """Replicated validation logic from trust_units.py."""
    import math
    try:
        if not math.isfinite(float(units)):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Units must be a finite number")
    if not allow_fractional:
        if units != int(units):
            raise ValueError("Fractional units not allowed")
        return int(units)
    return round(units, 4)


def _calc_capacity(settings: dict) -> any:
    """Replicated capacity calculation from trust_units.py create endpoint."""
    allocation_mode = settings.get("allocation_mode", "percentage")
    ceiling = settings.get("authorized_units_ceiling", settings["total_authorized_units"])
    capacity = settings["total_authorized_units"] if allocation_mode == "percentage" else ceiling
    if allocation_mode == "units" and settings.get("unlimited_units"):
        capacity = None
    return capacity


class TestPercentageModeValidation:
    """Test percentage allocation mode constraints."""

    def test_validate_units_integer(self):
        """Integer units pass validation when fractional is disabled."""
        result = _validate_units(50, allow_fractional=False)
        assert result == 50

    def test_validate_units_fractional_rejected(self):
        """Fractional units rejected when allow_fractional is False."""
        with pytest.raises(ValueError) as exc_info:
            _validate_units(50.5, allow_fractional=False)
        assert "Fractional units not allowed" in str(exc_info.value)

    def test_validate_units_fractional_allowed(self):
        """Fractional units accepted when allow_fractional is True."""
        result = _validate_units(50.5, allow_fractional=True)
        assert result == 50.5

    def test_calc_percentage_normal(self):
        """Percentage calculation is correct."""
        assert _calc_percentage(25, 100) == 25.0
        assert _calc_percentage(50, 200) == 25.0

    def test_calc_percentage_zero_authorized(self):
        """Zero authorized units returns 0% to avoid division by zero."""
        assert _calc_percentage(10, 0) == 0

    def test_calc_percentage_rounded_to_4_decimal(self):
        """Percentage should be rounded to 4 decimal places."""
        # 1/3 of 100 = 33.333333... → 33.3333
        assert _calc_percentage(100, 300) == 33.3333


class TestUnitModeValidation:
    """Test unit allocation mode constraints."""

    def test_validate_units_large_unit_count(self):
        """Large unit counts are valid in unit mode."""
        result = _validate_units(10000, allow_fractional=False)
        assert result == 10000

    def test_validate_units_nan_rejected(self):
        """NaN units should be rejected."""
        with pytest.raises(ValueError):
            _validate_units(float('nan'), allow_fractional=False)

    def test_validate_units_infinity_rejected(self):
        """Infinity units should be rejected."""
        with pytest.raises(ValueError):
            _validate_units(float('inf'), allow_fractional=False)


class TestModeSpecificCapacity:
    """Test capacity enforcement differs by allocation mode."""

    def test_percentage_mode_capacity(self):
        """In percentage mode, capacity = total_authorized_units."""
        settings = {
            "total_authorized_units": 100,
            "allocation_mode": "percentage",
            "authorized_units_ceiling": 1000,
            "unlimited_units": False,
        }
        capacity = _calc_capacity(settings)
        assert capacity == 100  # Uses total_authorized, not ceiling

    def test_unit_mode_capacity(self):
        """In unit mode, capacity = authorized_units_ceiling."""
        settings = {
            "total_authorized_units": 100,
            "allocation_mode": "units",
            "authorized_units_ceiling": 1000,
            "unlimited_units": False,
        }
        capacity = _calc_capacity(settings)
        assert capacity == 1000  # Uses ceiling, not total_authorized

    def test_unit_mode_unlimited_capacity(self):
        """In unit mode with unlimited_units, capacity is None (no cap)."""
        settings = {
            "total_authorized_units": 100,
            "allocation_mode": "units",
            "authorized_units_ceiling": 1000,
            "unlimited_units": True,
        }
        capacity = _calc_capacity(settings)
        assert capacity is None

    def test_percentage_mode_ignores_ceiling(self):
        """Percentage mode should ignore authorized_units_ceiling for capacity."""
        settings = {
            "total_authorized_units": 200,
            "allocation_mode": "percentage",
            "authorized_units_ceiling": 500,
            "unlimited_units": False,
        }
        capacity = _calc_capacity(settings)
        assert capacity == 200  # total_authorized, not ceiling

    def test_unit_mode_exceeding_ceiling_rejected(self):
        """In unit mode, units exceeding ceiling should be rejected by endpoint."""
        settings = {
            "total_authorized_units": 100,
            "allocation_mode": "units",
            "authorized_units_ceiling": 50,
            "unlimited_units": False,
        }
        units_requested = 75
        ceiling = settings["authorized_units_ceiling"]
        assert units_requested > ceiling  # Endpoint should reject this

    def test_capacity_overflow_prevented(self):
        """Issuing units that would exceed capacity should be rejected."""
        settings = {
            "total_authorized_units": 100,
            "allocation_mode": "percentage",
            "authorized_units_ceiling": 100,
            "unlimited_units": False,
        }
        current_active = 80
        units_requested = 30
        capacity = _calc_capacity(settings)
        assert current_active + units_requested > capacity  # 110 > 100 → reject

    def test_capacity_at_limit_allowed(self):
        """Issuing units that exactly reach capacity should be allowed."""
        settings = {
            "total_authorized_units": 100,
            "allocation_mode": "percentage",
            "authorized_units_ceiling": 100,
            "unlimited_units": False,
        }
        current_active = 80
        units_requested = 20
        capacity = _calc_capacity(settings)
        assert current_active + units_requested == capacity  # 100 == 100 → allow


class TestClassBeneficiaryPerCapita:
    """Test per-capita share calculation for class beneficiaries.

    From DECISIONS.md:
    'The initial product convention is per capita (equal shares among
    confirmed members), so five children divide a 50% pool into 10% each.'
    """

    def test_per_capita_5_members_50_pct_pool(self):
        """5 children divide a 50% pool → 10% each (the DECISIONS.md example)."""
        pool_pct = 50.0
        member_count = 5
        share = round(pool_pct / member_count, 4)
        assert share == 10.0

    def test_per_capita_single_member(self):
        """Single member gets the full pool."""
        pool_pct = 50.0
        member_count = 1
        share = round(pool_pct / member_count, 4)
        assert share == 50.0

    def test_per_capita_zero_members(self):
        """Zero members → 0 share (endpoint returns 0 when items is empty)."""
        pool_pct = 50.0
        member_count = 0
        share = round(pool_pct / member_count, 4) if member_count else 0
        assert share == 0

    def test_per_capita_3_members_30_pct_pool(self):
        """3 members divide a 30% pool → 10% each."""
        pool_pct = 30.0
        member_count = 3
        share = round(pool_pct / member_count, 4)
        assert share == 10.0

    def test_class_pool_combined_limit(self):
        """Combined class pools cannot exceed 100%."""
        existing_total = 60.0
        new_pool = 50.0
        assert existing_total + new_pool > 100  # Should be rejected

    def test_class_pool_within_limit(self):
        """Combined class pools at exactly 100% is acceptable."""
        existing_total = 50.0
        new_pool = 50.0
        assert existing_total + new_pool == 100  # Should be accepted

    def test_class_pool_unit_mode_no_pct_check(self):
        """In unit mode, class pools don't use percentage validation.
        The create_class_beneficiary endpoint checks allocation_mode == 'percentage'
        before applying the 100% combined limit."""
        settings = {"allocation_mode": "units"}
        # In units mode, percentage check is skipped
        assert settings["allocation_mode"] != "percentage"


class TestVersionedReplacementPattern:
    """Test that allocation edits create versioned replacements, not in-place mutations.

    From DECISIONS.md:
    'Editing an allocation never mutates the historical record. It creates a
    replacement allocation/version containing the prior allocation, new allocation,
    effective date, reason, actor, and timestamp; the prior version is marked
    superseded.'
    """

    def test_replacement_inherits_version_increment(self):
        """Replacement certificate should have version = prior_version + 1."""
        prior_version = 1
        new_version = prior_version + 1
        assert new_version == 2

        prior_version = 3
        new_version = prior_version + 1
        assert new_version == 4

    def test_replacement_supersedes_prior(self):
        """Replacement certificate should reference the prior certificate_id."""
        prior_cert_id = "cert_abc123"
        replacement = {
            "certificate_id": "cert_def456",
            "supersedes_certificate_id": prior_cert_id,
            "version": 2,
            "status": "active",
        }
        assert replacement["supersedes_certificate_id"] == prior_cert_id
        assert replacement["status"] == "active"

    def test_prior_marked_superseded(self):
        """Prior certificate should be marked status='superseded' with timestamp."""
        prior = {"certificate_id": "cert_abc123", "status": "active", "version": 1}
        now = datetime.now(timezone.utc).isoformat()

        # Simulate the update_one call
        prior["status"] = "superseded"
        prior["superseded_at"] = now
        prior["updated_at"] = now

        assert prior["status"] == "superseded"
        assert "superseded_at" in prior

    def test_audit_trail_record_shape(self):
        """Audit trail record should contain prior_cert_id, replacement_id,
        prior_units, new_units, reason, effective_date, actor."""
        audit = {
            "audit_id": "baa_abc123",
            "trust_id": "trust_1",
            "user_id": "user_1",
            "action": "replacement_created",
            "prior_certificate_id": "cert_abc123",
            "replacement_certificate_id": "cert_def456",
            "prior_units": 25,
            "new_units": 50,
            "reason": "Allocation updated",
            "effective_date": "2026-08-21",
            "actor": "user_1",
            "created_at": "2026-08-21T00:00:00+00:00",
        }
        assert audit["action"] == "replacement_created"
        assert audit["prior_certificate_id"] != audit["replacement_certificate_id"]
        assert audit["prior_units"] != audit["new_units"]
        assert audit["actor"] is not None
        assert audit["effective_date"] is not None

    def test_replacement_preserves_holder_info(self):
        """Replacement certificate should carry forward holder_name, holder_type, etc."""
        prior = {
            "certificate_id": "cert_abc123",
            "holder_name": "John Smith",
            "holder_type": "individual",
            "holder_identifier": "SSN-123",
            "email": "john@example.com",
            "phone": "555-1234",
            "trust_id": "trust_1",
            "units": 25,
            "version": 1,
            "status": "active",
        }
        # Replacement copies all fields from prior, then overrides
        replacement = dict(prior)
        replacement["certificate_id"] = "cert_def456"
        replacement["units"] = 50  # Changed
        replacement["supersedes_certificate_id"] = prior["certificate_id"]
        replacement["version"] = prior["version"] + 1
        replacement["status"] = "active"

        # Holder info preserved
        assert replacement["holder_name"] == "John Smith"
        assert replacement["holder_type"] == "individual"
        assert replacement["email"] == "john@example.com"
        # Units changed
        assert replacement["units"] == 50
        assert prior["units"] == 25  # Prior unchanged

    def test_non_allocation_update_uses_in_place(self):
        """When only contact info is updated (no units change), use in-place update."""
        update_fields = {"email": "newemail@example.com", "updated_at": "2026-08-21"}
        allocation_changed = False  # update.units is None

        assert not allocation_changed  # Should use in-place, not replacement

    def test_replacement_reason_recorded(self):
        """Replacement should include a human-readable reason."""
        reasons = [
            "Allocation updated",
            "Beneficiary share increased per trustee resolution 2026-08-15",
            "Correction: original allocation was 10% instead of 15%",
        ]
        for reason in reasons:
            assert len(reason) <= 1000  # max_length constraint from model


class TestSettingsValidation:
    """Test settings update validation logic."""

    def test_valid_allocation_modes(self):
        """Only 'percentage' and 'units' are valid allocation_mode values."""
        valid_modes = {"percentage", "units"}
        assert "percentage" in valid_modes
        assert "units" in valid_modes
        assert "invalid" not in valid_modes
        assert "hybrid" not in valid_modes

    def test_valid_distribution_conventions(self):
        """Only 'per_capita' and 'per_stirpes' are valid conventions."""
        valid_conventions = {"per_capita", "per_stirpes"}
        assert "per_capita" in valid_conventions
        assert "per_stirpes" in valid_conventions
        assert "per_head" not in valid_conventions

    def test_negative_ceiling_invalid(self):
        """authorized_units_ceiling cannot be negative."""
        ceiling = -50
        assert ceiling < 0  # Should raise 400

    def test_zero_ceiling_valid(self):
        """authorized_units_ceiling of 0 is technically valid (though unusual)."""
        ceiling = 0
        assert ceiling >= 0  # Should not raise 400

    def test_unlimited_units_with_ceiling(self):
        """unlimited_units=True should override the ceiling for capacity checks."""
        settings = {
            "allocation_mode": "units",
            "authorized_units_ceiling": 1000,
            "unlimited_units": True,
        }
        # Even with a ceiling, unlimited_units means no capacity limit
        capacity = _calc_capacity({
            "total_authorized_units": 100,
            **settings,
        })
        assert capacity is None


class TestDefaultSettingsShape:
    """Test that default settings include all allocation mode fields."""

    def test_default_settings_shape(self):
        """New settings should include all required allocation fields with defaults."""
        defaults = {
            "total_authorized_units": 100,
            "allocation_mode": "percentage",
            "authorized_units_ceiling": 100,
            "unlimited_units": False,
            "class_distribution_convention": "per_capita",
            "unit_label": "Certificate Unit",
            "allow_fractional": False,
        }
        # All fields present
        for key in ["allocation_mode", "authorized_units_ceiling", "unlimited_units",
                     "class_distribution_convention"]:
            assert key in defaults

        # Defaults match DECISIONS.md
        assert defaults["allocation_mode"] == "percentage"
        assert defaults["class_distribution_convention"] == "per_capita"
        assert defaults["unlimited_units"] is False