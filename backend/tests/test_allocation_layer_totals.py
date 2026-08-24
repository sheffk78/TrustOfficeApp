"""
Regression test for 2026-08-24 Codex QA finding F1:
"Visible percentages sum to 110%" on the beneficiary Overview tab.

Root cause: the dashboard endpoint summed certificate percentages (issued
ownership, capped at 100%) with class-beneficiary pool percentages (reserved
pools that may overlap certificate holders) into a single
total_allocated_percentage, producing >100% totals and an "Over-allocated"
warning for legitimate data (demo trust: certs=100%, classes=60+40%).

Fix semantics tested here:
1. total_allocated_percentage = max(cert_total, class_total), not the sum.
2. Layer totals are reported separately for the UI.
3. A genuine over-issue (certs > 100%) is still detectable.
4. Demo seed data is coherent under these semantics.

Strategy: replicates the exact aggregation block from
backend/routers/beneficiaries.py dashboard endpoint and validates shapes,
plus asserts demo.py seed numbers satisfy the semantics.
"""
import os
import re

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")


def compute_totals(beneficiaries, class_beneficiaries):
    """Replicated from beneficiaries.py dashboard endpoint (post-fix)."""
    certificate_percentage_total = round(
        sum(b["percentage"] for b in beneficiaries), 4
    )
    class_beneficiary_percentage_total = round(
        sum(cb.get("percentage", 0) for cb in class_beneficiaries), 4
    )
    total_allocated_percentage = round(
        max(certificate_percentage_total, class_beneficiary_percentage_total), 4
    )
    return {
        "total_allocated_percentage": total_allocated_percentage,
        "certificate_percentage_total": certificate_percentage_total,
        "class_beneficiary_percentage_total": class_beneficiary_percentage_total,
    }


def _demo_seed_numbers():
    """Parse demo.py seed data so this test fails if seeds drift."""
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "..", "routers", "demo.py")).read()
    # trust1 certificates: units values in the CERT-00x block
    cert_block = src.split("TRUST UNIT CERTIFICATES")[1].split("TRUST UNIT TRANSFERS")[0]
    cert_units = [float(u) for u in re.findall(r'"units": ([\d.]+)', cert_block)]
    # trust1 class pools: first insert_many block after CLASS BENEFICIARIES
    class_block = src.split("CLASS BENEFICIARIES")[1].split("VAULT DOCUMENTS")[0]
    class_pcts = [float(p) for p in re.findall(r'"percentage": ([\d.]+)', class_block)]
    return cert_units, class_pcts[:2]  # trust1 has two classes


def test_demo_trust_no_false_overallocation():
    """The exact scenario from the Codex QA report must total ≤ 100."""
    cert_units, class_pcts = _demo_seed_numbers()
    assert sum(cert_units) == 100, "demo certs should fully allocate 100 units"
    authorized = 100.0
    bens = [{"percentage": u / authorized * 100} for u in cert_units]
    cbs = [{"percentage": p} for p in class_pcts]

    totals = compute_totals(bens, cbs)
    assert totals["certificate_percentage_total"] == 100.0
    assert totals["class_beneficiary_percentage_total"] == 100.0
    # OLD behavior: 200.0 → false "Over-allocated". NEW: capped layer max.
    assert totals["total_allocated_percentage"] == 100.0


def test_overlapping_layers_do_not_sum():
    """Descendant holds 15% cert AND sits in a 40% contingent class."""
    bens = [{"percentage": 60.0}, {"percentage": 15.0}]
    cbs = [{"percentage": 40.0}]
    totals = compute_totals(bens, cbs)
    # max(issued=75, reserved=40) — the largest committed layer, not the sum
    assert totals["total_allocated_percentage"] == 75.0
    assert totals["certificate_percentage_total"] == 75.0
    assert totals["class_beneficiary_percentage_total"] == 40.0


def test_genuine_certificate_overissue_flagged():
    """Real over-issue (>100% issued) still surfaces via cert layer total."""
    bens = [{"percentage": 70.0}, {"percentage": 50.0}]
    totals = compute_totals(bens, [])
    assert totals["certificate_percentage_total"] == 120.0
    assert totals["total_allocated_percentage"] == 120.0  # UI flags this layer


def test_empty_state():
    totals = compute_totals([], [])
    assert totals["total_allocated_percentage"] == 0
