"""Adversarial tests for the Trust Brief builder (trust_brief.py).

Council mandate (2026-09-14): the Brief builder is the new critical path —
silent truncation of distribution language or a dropped beneficiary is as
dangerous as a stale Brief. These tests assert field presence, cap-overflow
shedding order, and staleness logic.

Pure functions — no Mongo, no network. Runs in CI.
"""
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-tests")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(BACKEND_DIR))

import pytest  # noqa: E402

import trust_brief as tb  # noqa: E402


# ---------------------------------------------------------------- fixtures ---

def make_ctx(**overrides):
    """Realistic baseline context; tests override individual sections."""
    ctx = {
        "trust": {
            "name": "Family Trust", "type": "Revocable Living",
            "jurisdiction": "Utah", "state_code": "UT",
            "start_date": "2024-01-15", "beneficiary_standard": "HEMS",
            "trustees": "Jane Smith",
        },
        "trust_document": {
            "grantor": "John Doe",
            "distribution_standard": "health, education, maintenance and support as defined in Section 4.1",
            "distribution_standard_type": "HEMS",
            "distribution_article": "Article IV, Section 4.1",
            "distribution_rules": {"tuition_cap": "unlimited", "annual_limit": "none"},
            "trustee_powers": [
                {"power": "sell real estate", "article_reference": "Art VI §6.2"},
                {"power": "borrow against assets", "article_reference": "Art VI §6.3"},
            ],
            "trustee_powers_detail": {"summary": "Powers conferred on sitting trustee"},
            "removal_provisions": {"summary": "Grantor may remove trustee"},
            "termination_rules": {"summary": "Terminates at age 40"},
            "beneficiary_names": ["Bob Doe", "Sue Doe"],
        },
        "health_score": {"total": 82, "max_score": 100, "color": "green"},
        "beneficiaries": [{"name": "Bob Doe", "units": 40}, {"name": "Sue Doe", "units": 60}],
        "class_beneficiaries": [{"class_type": "descendants", "label": "Descendants", "percentage": 100, "description": ""}],
        "upcoming_deadlines": [{"task_type": "annual_review", "due_date": "2026-10-01", "description": "Annual trust review", "priority": "high"}],
        "tax_deadlines": [{"filing": "Form 1041", "due_date": "2027-04-15", "status": "pending"}],
        "pending_items": [{"type": "pending_distribution", "summary": "$2,500.00 to Bob Doe", "date": "2026-09-10"}],
        "money_summary": {"distributions_total": 3, "distributions_ytd_amount": 5000,
                          "compensation_active_plans": 1, "compensation_ytd_paid": 1200,
                          "investments_count": 2, "investments_total_value": 150000,
                          "recent_transactions_30d": 4},
        "structure_summary": {"entity_count": 1, "entity_type_counts": {"llc": 1},
                              "beneficiary_count": 2, "schedule_a_asset_count": 4,
                              "schedule_a_total_value": 900000,
                              "communications_total": 12, "communications_pending_action": 1},
        "vault_documents": [
            {"doc_id": "d1", "title": "EIN Letter", "category": "irs", "category_label": "IRS",
             "date": "2026-03-14", "description": "CP 575 EIN confirmation", "tags": ["ein"]},
        ],
        "recent_activity": [
            {"type": "minutes", "label": "Quarterly minutes recorded", "date": "2026-09-01"},
            {"type": "distribution", "label": "$1,000.00 to Bob Doe (approved)", "date": "2026-08-20"},
        ],
        "entities": [{"name": "Holdings LLC", "entity_type": "LLC"}],
    }
    ctx.update(overrides)
    return ctx


# ---------------------------------------------------------------- core tests ---

def test_typical_trust_under_budget():
    r = trust_brief_result(make_ctx())
    assert r["stats"]["total_tokens"] <= tb.CORE_BUDGET_TOKENS + tb.OVERFLOW_BUDGET_TOKENS
    assert not r["stats"]["shed_sections"]


def test_distribution_standard_exact_language_never_dropped():
    std = "extraordinarily long distribution standard language " * 30
    r = trust_brief_result(make_ctx(trust_document={
        "grantor": "J", "distribution_standard": std,
        "distribution_standard_type": "HEMS", "distribution_article": "Art IV §4.1",
    }))
    assert std.strip() in r["text"], "exact distribution language must survive core shedding"


def test_distribution_standard_survives_extreme_core_pressure():
    """Even when everything else sheds, the standard stays."""
    std = "sole and absolute discretion of the trustee"
    r = trust_brief_result(make_ctx(
        trust_document={"distribution_standard": std, "distribution_article": "Art IV §4.1",
                        "trustee_powers": [{"power": f"power number {i}", "article_reference": f"Art X §10.{i}"} for i in range(40)]},
        beneficiaries=[{"name": f"Beneficiary Number {i}", "units": 1} for i in range(30)],
        upcoming_deadlines=[{"task_type": "t", "due_date": "2026-12-01", "description": f"task {i} with a very long description" * 3, "priority": "high"} for i in range(20)],
        tax_deadlines=[{"filing": f"Schedule {i}", "due_date": "2027-01-01"} for i in range(20)],
    ))
    assert std in r["text"]
    assert "Art IV §4.1" in r["text"]


def test_beneficiary_not_silently_dropped_small_roster():
    names = [f"Beneficiary {i}" for i in range(10)]
    r = trust_brief_result(make_ctx(beneficiaries=[{"name": n, "units": 1} for n in names]))
    for n in names:
        assert n in r["text"]
    assert not r["stats"]["roster_truncated"]


def test_beneficiary_roster_truncation_is_marked_not_silent():
    names = [f"Beneficiary Number {i}" for i in range(40)]
    r = trust_brief_result(make_ctx(beneficiaries=[{"name": n, "units": 1} for n in names]))
    shown = 0
    for n in names:
        if n in r["text"]:
            shown += 1
    assert shown == tb.MAX_BENEFICIARIES_FULL, "exactly MAX_BENEFICIARIES_FULL should render"
    assert "more" in r["text"] and "full roster" in r["text"], "truncation must be marked inline"
    assert r["stats"]["roster_truncated"] is True


def test_cap_overflow_sheds_overflow_first_not_core():
    """100 vault docs + minutes + entities: core sections all survive; the
    vault list caps at MAX_VAULT_DOC_LINES; cap-overflow shedding is recorded."""
    vault = [{"doc_id": f"d{i}", "title": f"Document Title {i}", "category": "other",
              "category_label": "Other", "date": "2026-01-01", "description": "some description text"} for i in range(100)]
    r = trust_brief_result(make_ctx(vault_documents=vault))
    s = r["stats"]
    # Core intact
    assert "Trust & Instrument" in s["sections_rendered"]
    assert "Beneficiaries" in s["sections_rendered"]
    assert "Upcoming Deadlines" in s["sections_rendered"]
    assert "Snapshots" in s["sections_rendered"]
    assert s["total_tokens"] <= s["budget_tokens"] + 5
    assert s["vault_docs_in_brief"] == tb.MAX_VAULT_DOC_LINES, "vault list caps at its ceiling"
    # titles beyond the ceiling must not appear
    assert "Document Title 99" not in r["text"]


def test_overflow_shed_order_vault_before_minutes():
    """When both must shed, vault doc lines shed before the minutes recap."""
    vault = [{"doc_id": f"d{i}", "title": f"Long Document Title {i}", "category": "other",
              "category_label": "Other", "date": "2026-01-01",
              "description": "description text that takes up space in the overflow budget"} for i in range(200)]
    activity = [{"type": "minutes", "label": f"Minutes {i} recorded with long label text", "date": "2026-09-01"} for i in range(10)]
    r = trust_brief_result(make_ctx(vault_documents=vault, recent_activity=activity))
    text = r["text"]
    # minutes recap survived while vault docs were cut
    assert "Minutes 0 recorded" in text
    # at least one vault doc title is missing
    missing = [i for i in range(200) if f"Long Document Title {i}" not in text]
    assert len(missing) > 0


def test_no_minutes_no_activity_renders_clean():
    r = trust_brief_result(make_ctx(recent_activity=[]))
    assert "Recent Minutes" not in r["text"]
    assert r["stats"]["total_tokens"] > 0


def test_empty_context_renders_gracefully():
    r = trust_brief_result({})
    assert r["text"].startswith("# TRUST BRIEF")
    assert "None recorded" in r["text"]
    assert r["stats"]["total_tokens"] > 0


def test_multiline_values_never_break_layout():
    """Adversarial: a description with newlines must not inject fake headings."""
    evil = "line one\n## FAKE HEADING\nline three"
    r = trust_brief_result(make_ctx(vault_documents=[
        {"doc_id": "d", "title": "Evil Doc", "category": "other", "date": "2026-01-01", "description": evil},
    ]))
    assert "## FAKE HEADING" not in r["text"]
    assert "line one FAKE HEADING line three" in r["text"]  # flattened + heading marker stripped


def test_staleness_needs_rebuild():
    # no stored brief → rebuild
    assert tb.needs_rebuild(None, {"vault_documents": "2026-09-14"}, {}) is True
    assert tb.needs_rebuild("", {"vault_documents": "2026-09-14"}, {}) is True
    # stored brief, nothing newer → fresh
    assert tb.needs_rebuild("2026-09-14T00:00:00Z",
                            {"vault_documents": "2026-09-14", "minutes_records": "2026-09-13"},
                            {"vault_documents": "2026-09-14", "minutes_records": "2026-09-13"}) is False
    # minutes updated after build → rebuild
    assert tb.needs_rebuild("2026-09-14T00:00:00Z",
                            {"vault_documents": "2026-09-14", "minutes_records": "2026-09-15"},
                            {"vault_documents": "2026-09-14", "minutes_records": "2026-09-13"}) is True
    # new collection appears in current versions → rebuild
    assert tb.needs_rebuild("2026-09-14T00:00:00Z",
                            {"new_collection": "2026-09-16"},
                            {"vault_documents": "2026-09-14"}) is True


def test_token_estimator_sane():
    assert tb.estimate_tokens("") == 0
    assert tb.estimate_tokens("x" * 400) == 100
    assert tb.estimate_tokens("hello") == 2  # ceil(5/4)


# ---------------------------------------------------------------- helpers ---

def trust_brief_result(ctx):
    import trust_brief as tb
    return tb.build_trust_brief(ctx)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))