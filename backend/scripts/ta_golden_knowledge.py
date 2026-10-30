"""TA Knowledge Golden Set — 40 deterministic knowledge-accuracy questions.

Each golden: query, audience grant, expected source file(s) (top-2 hit),
key fact phrases (verbatim, case-insensitive, union of top-4 passages),
and optional behavior flags.

Rules of the set (see scripts/GOLDEN-SET-NOTES.md):
- expected_sources are CALIBRATED against the current re-ranker (any-of lists
  cover legitimate corpus overlap), never aspirational.
- key_facts are mined verbatim from the corpus — a failure means retrieval
  missed the source, not that the wording drifted.
- wingpoint-tier questions double as isolation checks (fail-closed, Phase A-1).

Categories: utc_doctrine, state_law, trustee101, product, trust_types, tax, wp_tax101,
wp_defend, wp_inner_work.
"""

GOLDEN_SET = [
    # ── UTC DOCTRINE (8) ─────────────────────────────────────────────
    {
        "id": "utc-01",
        "category": "utc_doctrine",
        "audience": "universal",
        # Calibration 2026-10-30: the corpus (24-utc-01 s.402 checklist) never
        # uses the word "valid" — corpus-grounded phrasing is member-real.
        "query": "What must exist for a settlor to create a trust under the Uniform Trust Code?",
        "expected_sources": ["24-utc-01-definitions-scope.md"],
        "key_facts": [
            "settlor has capacity",
            "intent to create a trust",
            "not both sole trustee and sole beneficiary",
        ],
    },
    {
        "id": "utc-02",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "What does the duty of loyalty mean for a trustee?",
        "expected_sources": ["24-utc-02-trustee-duties.md"],
        "key_facts": [
            "duty of loyalty in practice: self-dealing avoidance",
            "reasonable care, skill, and caution",
        ],
    },
    {
        "id": "utc-03",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "How much discretion does a trustee have over distributions?",
        "expected_sources": ["24-utc-03-distributions.md"],
        "key_facts": [
            "good faith and in accordance with the trust's terms and purposes and the beneficiaries' interests",
            "ascertainable standard",
        ],
    },
    {
        "id": "utc-04",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "What reports must a trustee send to beneficiaries?",
        "expected_sources": ["24-utc-04-accounting-reports.md"],
        "key_facts": [
            "At least annually and at termination",
            "duty to inform, the duty to account",
        ],
    },
    {
        "id": "utc-05",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "Does irrevocable mean the trust can never be changed or amended?",
        "expected_sources": ["24-utc-05-amendments-revocation.md"],
        "key_facts": [
            "\"irrevocable\" is not the same as \"unchangeable\"",
            "attorney question",
        ],
    },
    {
        "id": "utc-06",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "Who becomes the successor trustee when the current trustee resigns?",
        "expected_sources": ["24-utc-06-successor-trustees-vacancy.md"],
        "key_facts": [
            "person designated in the trust's terms as successor trustee",
            "unanimous agreement of the qualified beneficiaries",
        ],
    },
    {
        "id": "utc-07",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "Can a creditor reach trust assets when the trust has a spendthrift clause?",
        "expected_sources": ["24-utc-07-creditors-protection.md"],
        "key_facts": [
            "restrains both voluntary and involuntary transfer",
            "exception-laden",
            "judgment creditor",
        ],
    },
    {
        "id": "utc-08",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "How do I properly close a trust and distribute the remaining property?",
        "expected_sources": ["24-utc-08-termination.md"],
        "key_facts": [
            "final report, expeditious delivery of the property, and a claim window",
            "reasonable reserve",
        ],
    },
    # ── NOTICE REGISTER + STATE LAW (3) ─────────────────────────────
    {
        "id": "utc-09",
        "category": "utc_doctrine",
        "audience": "universal",
        "query": "What notices am I required to send as trustee, and by when?",
        "expected_sources": ["24-utc-09-notification-register.md"],
        "key_facts": [
            "60 days",
            "In advance",
        ],
    },
    {
        "id": "law-01",
        "category": "state_law",
        "audience": "universal",
        "query": "Is trust law federal or state — what governs my trust?",
        "expected_sources": ["06-state-compliance.md"],
        "key_facts": [
            "governed primarily by state law, not federal law",
        ],
    },
    {
        "id": "law-02",
        "category": "state_law",
        "audience": "universal",
        "query": "What does Utah law require for trust administration?",
        "expected_sources": ["18-state-compliance-utah.md"],
        "key_facts": [
            "Utah Uniform Trust Code",
        ],
    },
    # ── TRUSTEE 101 (4) ─────────────────────────────────────────────
    {
        "id": "t101-01",
        "category": "trustee101",
        "audience": "universal",
        "query": "What is the 4-question HEMS test before making a distribution?",
        "expected_sources": ["27-trustee-101-hems-decision-framework.md"],
        "key_facts": [
            "The 4-Question Test",
            "H — Health: Medical diagnosis, treatment, prescriptions, therapy by licensed practitioners",
        ],
    },
    {
        "id": "t101-02",
        "category": "trustee101",
        "audience": "universal",
        "query": "What is the commingling problem and how do I keep accounts separate?",
        "expected_sources": ["28-trustee-101-separation-checklist.md"],
        "key_facts": [
            "Commingling",
            "Separate",
        ],
    },
    {
        "id": "t101-03",
        "category": "trustee101",
        "audience": "universal",
        "query": "What minute templates are available for trust meetings?",
        "expected_sources": ["26-trustee-101-minute-templates.md", "16-minutes-types-and-templates.md"],
        "key_facts": [
            "ratification",
        ],
    },
    {
        "id": "t101-04",
        "category": "trustee101",
        "audience": "universal",
        "query": "What is the prudent investor rule for trust investments?",
        "expected_sources": ["30-trustee-101-investment-policy-statement.md"],
        "key_facts": [
            "Prudent Investor Rule",
        ],
    },
    # ── PRODUCT / HOW-TO (6) ────────────────────────────────────────
    {
        "id": "prod-01",
        "category": "product",
        "audience": "universal",
        "query": "Why do trust meeting minutes matter — what do they prove?",
        "expected_sources": ["05-trust-minutes.md"],
        "key_facts": [
            "proof that you, as trustee, are actively managing the trust",
        ],
    },
    {
        "id": "prod-02",
        "category": "product",
        "audience": "universal",
        "query": "How does Guided Minutes work?",
        "expected_sources": ["09-guided-minutes.md"],
        "key_facts": [
            "Guided Minutes",
            "walks you through",
        ],
    },
    {
        "id": "prod-03",
        "category": "product",
        "audience": "universal",
        "query": "What is the Defensibility Score?",
        "expected_sources": ["08-defensibility-score.md"],
        "key_facts": [
            "proprietary measure of record-keeping completeness",
            "contemporaneous paper trail",
        ],
    },
    {
        "id": "prod-04",
        "category": "product",
        "audience": "universal",
        "query": "What is a quarterly review and what does it cover?",
        "expected_sources": ["22-quarterly-review-guide.md"],
        "key_facts": [
            "every three months to review the trust's financial status, beneficiary circumstances, and administrative compliance",
        ],
    },
    {
        "id": "prod-05",
        "category": "product",
        "audience": "universal",
        "query": "What beneficiary types and allocation modes does TrustOffice support?",
        "expected_sources": ["23-beneficiary-types-and-allocations.md"],
        "key_facts": [
            "individual, organization, and class",
            "percentage and units",
        ],
    },
    {
        "id": "prod-06",
        "category": "product",
        "audience": "universal",
        # Calibration 2026-10-30: 13-trustoffice-workflows carries the actual
        # "Workflow: Prepare and Document a Distribution" member how-to — it
        # is a legitimate canonical source for this in-app question alongside
        # 07-distributions (doctrine) and 12-features (routing).
        "query": "How do I record a distribution in the app for education expenses?",
        "expected_sources": [
            "07-distributions.md",
            "12-trustoffice-features.md",
            "13-trustoffice-workflows.md",
        ],
        "key_facts": [
            "distribution",
        ],
    },
    # ── TRUST TYPES (4) ─────────────────────────────────────────────
    {
        "id": "type-01",
        "category": "trust_types",
        "audience": "universal",
        "query": "What is a spendthrift trust?",
        "expected_sources": ["17-spendthrift-trust.md", "24-utc-07-creditors-protection.md"],
        "key_facts": [
            "spendthrift clause",
            "before those assets are actually distributed",
        ],
    },
    {
        "id": "type-02",
        "category": "trust_types",
        "audience": "universal",
        "query": "What is a special needs trust and how does it protect government benefits?",
        "expected_sources": ["17-special-needs-trust.md"],
        "key_facts": [
            "without disqualifying them from means-tested government benefits like Supplemental Security Income (SSI) and Medicaid",
        ],
    },
    {
        "id": "type-03",
        "category": "trust_types",
        "audience": "universal",
        "query": "Can I amend or revoke a revocable living trust?",
        "expected_sources": ["17-revocable-living-trust.md", "16-trust-amendments.md"],
        "key_facts": [
            "amend, restate, or revoke entirely at any point while they are alive",
        ],
    },
    {
        "id": "type-04",
        "category": "trust_types",
        "audience": "universal",
        "query": "How do beneficiary-to-trustee changes work when someone becomes their own trustee?",
        "expected_sources": ["16-trust-amendments.md"],
        "key_facts": [
            "beneficiary-to-trustee",
        ],
    },
    # ── TAX (2) ─────────────────────────────────────────────────────
    {
        "id": "tax-01",
        "category": "tax",
        "audience": "universal",
        "query": "What is Form 1041 and when is the trust tax return due?",
        "expected_sources": ["02-1041-tax-returns.md", "29-trustee-101-trust-tax-calendar.md"],
        "key_facts": [
            "Form 1041 is the IRS tax return filed for estates and trusts",
        ],
    },
    {
        "id": "tax-02",
        "category": "tax",
        "audience": "universal",
        "query": "What tax deadlines should a trustee track during the year?",
        "expected_sources": ["29-trustee-101-trust-tax-calendar.md", "02-1041-tax-returns.md"],
        "key_facts": [
            "April 15",
        ],
    },
    # ── WP TAX-101 (5, wingpoint tier + isolation check) ────────────
    {
        "id": "wp-tax-01",
        "category": "wp_tax101",
        "audience": "wingpoint",
        "query": "What does §3401(a) actually define as wages?",
        "expected_sources": [
            "40-wingpoint-wp-tax-101-lesson-01-what-you-were-never-told.md",
            "54-wingpoint-wp-tax-101-companion-01-Statutory-Definitions-Quick-Reference.md",
        ],
        "key_facts": [
            "3401(a) defines wages as remuneration paid by an employer to an employee for services",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-tax-02",
        "category": "wp_tax101",
        "audience": "wingpoint",
        "query": "W-4 exempt claiming rules for federal income tax withholding",
        "expected_sources": [
            "43-wingpoint-wp-tax-101-companion-03-supplement-w4-response-kit.md",
            "55-wingpoint-wp-tax-101-companion-02-W4-Decision-Guide.md",
        ],
        "key_facts": [
            "Exempt",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-tax-03",
        "category": "wp_tax101",
        "audience": "wingpoint",
        "query": "How do I correct the record on a W-2 or 1099 that was filed with the wrong characterization?",
        "expected_sources": ["45-wingpoint-wp-tax-101-lesson-05-correcting-the-record.md"],
        "key_facts": [
            "Correcting the Record — W-2s, 1099s, K-1s, and Your Return",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-tax-04",
        "category": "wp_tax101",
        "audience": "wingpoint",
        # Calibration 2026-10-30: question grounded in the 50-file's own
        # purpose line ("Why did the IRS provide this exemption?").
        "query": "Why did the IRS provide the 508(c)(1)(a) exemption — why does the door exist?",
        "expected_sources": ["50-wingpoint-wp-tax-101-research-research-508c1a-why-the-door-exists.md"],
        "key_facts": [
            "Why 508(c)(1)(a) Exists — The Constitutional and Legal Foundation",
        ],
        "forbidden_for_no_grant": True,
    },
    {
        "id": "wp-tax-05",
        "category": "wp_tax101",
        "audience": "wingpoint",
        "query": "What does the Tax Question course cover?",
        "expected_sources": ["52-wingpoint-wp-tax-101-outline-TAX-TRUTH-COURSE-OUTLINE.md"],
        "key_facts": [
            "Course Outline — The Tax Question",
        ],
        "forbidden_for_no_grant": True,
    },
    # ── WP DEFEND (4, wingpoint tier + isolation check) ─────────────
    {
        "id": "wp-def-01",
        "category": "wp_defend",
        "audience": "wingpoint",
        "query": "Why do challenges to my position come, and what do they really mean?",
        "expected_sources": ["59-wingpoint-wp-defend-lesson-01-why-challenges-come.md"],
        "key_facts": [
            "Why Challenges Come and What They Really Mean",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-def-02",
        "category": "wp_defend",
        "audience": "wingpoint",
        "query": "What is a CP2000 notice and how do I respond to it?",
        "expected_sources": ["61-wingpoint-wp-defend-lesson-03-irs-notices-what-to-expect.md"],
        "key_facts": [
            "CP2000 — Notice of Proposed Adjustment",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-def-03",
        "category": "wp_defend",
        "audience": "wingpoint",
        "query": "What should I do when my employer pushes back on my status change?",
        "expected_sources": ["63-wingpoint-wp-defend-lesson-05-when-the-world-pushes-back.md", "62-wingpoint-wp-defend-lesson-04-when-they-push-back.md"],
        "key_facts": [
            "employer",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-def-04",
        "category": "wp_defend",
        "audience": "wingpoint",
        "query": "When do I actually need an attorney or counsel?",
        "expected_sources": ["66-wingpoint-wp-defend-lesson-08-finding-the-right-counsel.md"],
        "key_facts": [
            "Finding the Right Counsel",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    # ── WP INNER WORK (4, wingpoint tier + isolation check) ─────────
    {
        "id": "wp-inw-01",
        "category": "wp_inner_work",
        "audience": "wingpoint",
        "query": "What is the enemy construct and why did I build one?",
        "expected_sources": ["70-wingpoint-wp-inner-work-lesson-01-the-construct-itself.md"],
        "key_facts": [
            "enemy construct is internal",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-inw-02",
        "category": "wp_inner_work",
        "audience": "wingpoint",
        "query": "Can victimhood and sovereignty coexist?",
        "expected_sources": ["72-wingpoint-wp-inner-work-lesson-03-victimhood-sovereignty.md"],
        "key_facts": [
            "Victimhood and Sovereignty Cannot Coexist",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-inw-03",
        "category": "wp_inner_work",
        "audience": "wingpoint",
        "query": "What does standing mean when no one is watching?",
        "expected_sources": ["76-wingpoint-wp-inner-work-lesson-07-standing.md"],
        "key_facts": [
            "watching and there is nothing to prove",
        ],
        "forbidden_for_no_grant": True,
        "education_not_advice": True,
    },
    {
        "id": "wp-inw-04",
        "category": "wp_inner_work",
        "audience": "wingpoint",
        "query": "What courses are in the Inner Work series?",
        "expected_sources": ["78-wingpoint-wp-inner-work-outline-outline-inner-work-enemy-construct.md"],
        "key_facts": [
            "Inner Work – The Enemy Construct",
        ],
        "forbidden_for_no_grant": True,
    },
]