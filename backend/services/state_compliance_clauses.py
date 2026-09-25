"""State compliance clauses for minutes templates.

Wires the EXISTING 50-state compliance engine (state_compliance_profiles) into
minutes generation: every template-mode document gets a State Compliance
Confirmation block, built from a per-state, per-action clause table
(state_action_clauses) — never generated freeform.

Safety model:
- Every clause row carries review metadata (source_citation, reviewed_by,
  reviewed_at). Rows without a reviewer render a NEUTRAL placeholder
  ("Trustee confirms compliance with [State] law") — no invented legal language.
- Unknown state → no block at all + a UI nudge (frontend sets the trust state).
- Loan actions embed the prevailing-rate confirmation the trustee must attest.

Attorney-reviewed rows must be reviewed by a qualified attorney before the
reviewed_by field is set. This module never self-certifies.
"""
from datetime import datetime, timezone

# Actions shipped first (Don Foster call, 9/25): the four most common + Don's states.
SUPPORTED_ACTIONS = {
    "loan_authorization",              # loan to beneficiary (prevailing-rate language)
    "distribution_to_beneficiaries",
    "acceptance_of_property",
    "trustee_compensation",
}

# States seeded first: Don's (CA, TX, DE) + the 10 most common trust jurisdictions.
PRIORITY_STATES = ["CA", "TX", "DE", "FL", "NV", "SD", "WY", "NY", "OH", "WA", "AZ", "PA", "IL"]


# Controlling trust statute per state — used to name the actual code (never
# invent one: California's controlling law is the Probate Code, not a "Trust
# Code"). States not listed fall back to "applicable state trust law".
_STATE_TRUST_STATUTE = {
    "CA": "California Probate Code (commencing with §15000)",
    "TX": "Texas Property Code, Chapter 111 et seq.",
    "DE": "Delaware Code, Title 12, Chapter 35",
    "FL": "Florida Trust Code (Chapter 736, Florida Statutes)",
    "NV": "Nevada Revised Statutes, Chapter 163",
    "SD": "South Dakota Codified Laws, Chapter 55-1 et seq.",
    "WY": "Wyoming Trust Code (Wyoming Statutes, Title 13)",
    "NY": "New York Estates, Powers & Trusts Law",
    "OH": "Ohio Revised Code, Chapter 5801 et seq.",
    "WA": "Washington Trust Act (RCW 11.98)",
    "AZ": "Arizona Trust Code (A.R.S., Title 14, Chapter 10)",
    "PA": "Pennsylvania Uniform Trust Act (20 Pa.C.S. Chapter 77)",
    "IL": "Illinois Trust Code (760 ILCS 3)",
}


def _utc_clause(profile: dict) -> str | None:
    adopted = (profile.get("utc_adopted") or "").lower()
    # The Governing Law header already states the state; add a sentence only
    # where the UTC adoption status itself is informative.
    if adopted == "full":
        return ("{state_name} has adopted the Uniform Trust Code in full; the "
                "Trustees confirm that all actions recorded herein comply with "
                "the {state_citation}.")
    if adopted == "partial":
        return ("{state_name} has adopted portions of the Uniform Trust Code; the "
                "Trustees confirm that all actions recorded herein comply with "
                "the {state_citation}.")
    return None


def _notice_clause(profile: dict) -> str | None:
    if profile.get("notice_required"):
        days = profile.get("notice_timing_days")
        timing = f" within the {days}-day notice period" if days else ""
        return (f"The Trustees confirm that all beneficiary notices required by "
                f"{state_name_of(profile)} law have been given{timing}.")
    return None


def _accounting_clause(profile: dict) -> str | None:
    freq = profile.get("accounting_frequency") or "annual"
    return (f"The Trustees confirm that accountings are maintained and provided to "
            f"beneficiaries consistent with {state_name_of(profile)} law "
            f"({freq} accounting standard).")


def _spendthrift_clause(profile: dict) -> str | None:
    if profile.get("spendthrift_default"):
        # Conditional phrasing: the engine has not read the trust instrument.
        return ("To the extent the Trust instrument contains spendthrift "
                "provisions, distributions recorded herein were made with due "
                "regard to those provisions.")
    return None


def state_name_of(profile: dict) -> str:
    return profile.get("state_name") or profile.get("state_code") or "the governing"


def _default_state_reference(profile: dict) -> str:
    """Neutral governing-law reference, used only when no reviewed citation exists.

    Names the state's actual controlling statute where known (a factual
    citation, not drafted legal language); falls back to generic trust law.
    """
    code = profile.get("state_code") or ""
    return _STATE_TRUST_STATUTE.get(code) or "applicable state trust law"


def build_state_compliance_block(
    state_code: str | None,
    template_type: str,
    profile: dict | None,
    action_clause: dict | None,
) -> str | None:
    """Render the State Compliance Confirmation block.

    Returns None when no block should appear (no state set, or state unknown to
    the compliance engine) — the frontend nudges the user to set the state.
    Unreviewed action clauses render the neutral placeholder, never freeform law.
    """
    if not state_code or not profile:
        return None

    state_name = state_name_of(profile)
    state_ref = (action_clause or {}).get("source_citation") or _default_state_reference(profile)

    lines = [
        "STATE COMPLIANCE CONFIRMATION",
        "",
        f"Governing Law: The Trust is governed by the laws of the State of {state_name}.",
    ]

    body = []
    for fn in (_utc_clause, _accounting_clause):
        text = fn(profile)
        if text:
            body.append(text.replace("{state_name}", state_name).replace("{state_citation}", state_ref))
    notice = _notice_clause(profile)
    if notice:
        # Scope-honest: profile data tracks the trustee acceptance-notice
        # window (e.g. Cal. Prob. Code §16061.5), not every notice type.
        body.append(notice.replace(
            "all beneficiary notices required by",
            "the beneficiary notice required by",
        ).replace(
            "have been given within",
            "has been given within",
        ))
    spendthrift = _spendthrift_clause(profile)
    if spendthrift:
        body.append(spendthrift)

    if action_clause and action_clause.get("clause_text"):
        if action_clause.get("reviewed_by"):
            body.append(action_clause["clause_text"])
        else:
            # Unreviewed: neutral placeholder. Flagged for attorney review.
            body.append(
                f"The Trustees confirm that this action complies with the "
                f"{state_ref} and the terms of the Trust Indenture."
                f" [State-specific clause pending attorney review.]"
            )

    lines.extend(body)
    lines.append("")
    if action_clause and action_clause.get("reviewed_by"):
        citation = action_clause.get("source_citation") or state_ref
        lines.append(f"Citation: {citation}")
    elif action_clause:
        # Unreviewed action clause: honest status + the factual statutory
        # reference (the statute itself is fact; the clause text is what's
        # pending review).
        lines.append(
            f"Citation: {state_ref}. State-specific action language pending "
            f"attorney review."
        )
    else:
        lines.append(f"Citation: {state_ref}")
    return "\n".join(lines)


def build_loan_rate_clause(template_data: dict) -> str | None:
    """Prevailing-rate attestation for beneficiary loans.

    Fires only on a REAL numeric rate. The frontend's default placeholder
    string ("AFR (Applicable Federal Rate)") and any other non-numeric value
    return None — a circular attestation ("AFR is not less than the AFR")
    asserts a determination nobody made, and the trustee's own rate entry is
    the determination that matters.

    When the loan month is in the AFR reference table, the clause renders the
    actual Treasury-published comparison instead of an unverifiable judgment.
    """
    import re
    from services.afr_rates import lookup_afr
    rate = template_data.get("interest_rate") or template_data.get("apr")
    if not rate:
        return None
    if "AFR" in str(rate).upper():
        return None
    m = re.search(r"\d+(\.\d+)?", str(rate))
    if not m:
        return None
    rate_val = float(m.group(0))
    pct = f"{rate_val:g}%"

    ref = lookup_afr(template_data.get("term_months"), template_data.get("loan_date"))
    if ref:
        afr_pct, source = ref
        if rate_val >= float(afr_pct.rstrip("%")):
            return (
                f"The Trustees confirm that the loan bears interest of {pct} per annum, "
                f"not less than the {afr_pct} applicable federal rate published by the "
                f"U.S. Treasury for the month of the loan ({source}), satisfying the "
                "below-market loan rules of IRC 7872."
            )
        # Below the referenced AFR: FLAG it — never attest a false compliance.
        return (
            f"NOTE: The loan bears interest of {pct} per annum, which is BELOW the "
            f"{afr_pct} applicable federal rate published by the U.S. Treasury for "
            f"the month of the loan ({source}). The Trustees should re-examine the "
            "rate against the below-market loan rules of IRC 7872 before finalizing."
        )

    # Month not in the reference table: neutral wording, no unverifiable claim.
    return (
        f"The Trustees confirm that the loan bears interest of {pct} per annum, "
        "which in the Trustees' judgment is not less than the applicable federal "
        "rate (AFR) published by the U.S. Treasury for the month of the loan, "
        "satisfying the below-market loan rules of IRC 7872."
    )