"""Tests: state compliance clauses wired into minutes generation (2026-09-25).

Root cause being guarded: the 50-state compliance engine existed with ZERO
integration into minutes — documents rendered no state-specific confirmation.
This suite pins the wiring: block presence/absence rules, neutral placeholder
for unreviewed actions (no freeform legal language), reviewed-clause rendering,
and the loan prevailing-rate attestation.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.state_compliance_clauses import (  # noqa: E402
    build_state_compliance_block,
    build_loan_rate_clause,
    PRIORITY_STATES,
    SUPPORTED_ACTIONS,
)

CA_PROFILE = {
    "state_code": "CA",
    "state_name": "California",
    "utc_adopted": "no",
    "notice_required": True,
    "notice_timing_days": 60,
    "accounting_frequency": "annual",
    "trustee_removal_standard": "breach of trust",
    "spendthrift_default": True,
}

TX_PROFILE = {
    "state_code": "TX",
    "state_name": "Texas",
    "utc_adopted": "no",
    "notice_required": True,
    "notice_timing_days": 60,
    "accounting_frequency": "annual",
    "trustee_removal_standard": "breach of trust",
    "spendthrift_default": True,
}


def _clause(state="CA", reviewed=False, action="trustee_compensation"):
    row = {"state_code": state, "action": action, "clause_text": None,
           "source_citation": None, "reviewed_by": None, "reviewed_at": None}
    if reviewed:
        row["clause_text"] = "The Trustees confirm this action complies with Prob C §16000 et seq."
        row["source_citation"] = "Cal. Prob. Code §16000 et seq."
        row["reviewed_by"] = "Attorney Review Pending"
        row["reviewed_at"] = "2026-09-25"
    return row


# ── Presence / absence rules ──────────────────────────────────────────────────

def test_no_state_means_no_block():
    assert build_state_compliance_block(None, "trustee_compensation", CA_PROFILE, None) is None
    assert build_state_compliance_block("", "trustee_compensation", CA_PROFILE, None) is None
    assert build_state_compliance_block(None, "trustee_compensation", None, None) is None


def test_unknown_state_means_no_block():
    assert build_state_compliance_block("ZZ", "trustee_compensation", None, None) is None


def test_block_contains_state_name_and_header():
    text = build_state_compliance_block("CA", "trustee_compensation", CA_PROFILE, None)
    assert text is not None
    assert "STATE COMPLIANCE CONFIRMATION" in text
    assert "California" in text


def test_notice_state_includes_notice_language():
    text = build_state_compliance_block("CA", "trustee_compensation", CA_PROFILE, None)
    assert "notices" in text
    assert "60-day" in text


def test_no_notice_state_omits_notice_language():
    profile = {**TX_PROFILE, "notice_required": False, "notice_timing_days": None}
    text = build_state_compliance_block("TX", "trustee_compensation", profile, None)
    assert "notices" not in text


def test_spendthrift_state_includes_spendthrift_language():
    text = build_state_compliance_block("CA", "trustee_compensation", CA_PROFILE, None)
    assert "spendthrift" in text


# ── Unreviewed vs reviewed clause rows ────────────────────────────────────────

def test_unreviewed_action_renders_neutral_placeholder():
    text = build_state_compliance_block("CA", "trustee_compensation", CA_PROFILE, _clause(reviewed=False))
    assert "pending attorney review" in text
    # No invented legal citation may render from an unreviewed row.
    assert "§16000" not in text


def test_reviewed_action_renders_clause_text_and_citation():
    text = build_state_compliance_block("CA", "trustee_compensation", CA_PROFILE,
                                        _clause(reviewed=True))
    assert "Prob C" in text
    assert "Cal. Prob. Code" in text
    assert "pending attorney review" not in text


def test_unreviewed_placeholder_mentions_state_reference():
    text = build_state_compliance_block("TX", "trustee_compensation", TX_PROFILE, _clause(state="TX"))
    assert "Texas" in text


# ── Loan rate attestation ─────────────────────────────────────────────────────

def test_loan_rate_clause_present_with_rate():
    clause = build_loan_rate_clause({"interest_rate": "4.5%"})
    assert clause is not None
    assert "4.5%" in clause
    assert "IRC 7872" in clause


def test_loan_rate_clause_absent_without_rate():
    assert build_loan_rate_clause({}) is None


# ── Seed coverage invariants ──────────────────────────────────────────────────

def test_priority_states_include_don_foster_states():
    assert {"CA", "TX", "DE"}.issubset(set(PRIORITY_STATES))


def test_supported_actions_match_launch_set():
    assert SUPPORTED_ACTIONS == {
        "loan_authorization",
        "distribution_to_beneficiaries",
        "acceptance_of_property",
        "trustee_compensation",
    }