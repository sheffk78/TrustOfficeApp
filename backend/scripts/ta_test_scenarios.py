# TA Evaluation Test Scenarios
# Each scenario: user query → expected intent + expected extracted fields
# Used by ta_eval.py to measure intent classification and extraction accuracy

SCENARIOS = [
    # ── DISTRIBUTIONS ──
    {
        "id": "dist-01",
        "query": "Record a $5,000 distribution to my daughter Sarah for college tuition",
        "expected_intent": "create_distribution",
        "expected_fields": {
            "beneficiary_name": "Sarah",
            "amount": 5000.0,
            "purpose": "education",
        },
        "required_fields_present": ["beneficiary_name", "amount", "purpose"],
    },
    {
        "id": "dist-02",
        "query": "I need to give $2,500 to my brother Tom for medical expenses",
        "expected_intent": "create_distribution",
        "expected_fields": {
            "beneficiary_name": "Tom",
            "amount": 2500.0,
            "purpose": "medical_expenses",
        },
        "required_fields_present": ["beneficiary_name", "amount", "purpose"],
    },
    {
        "id": "dist-03",
        "query": "Pay $1,200 to Mary for housing assistance this month",
        "expected_intent": "create_distribution",
        "expected_fields": {
            "beneficiary_name": "Mary",
            "amount": 1200.0,
            "purpose": "housing",
        },
        "required_fields_present": ["beneficiary_name", "amount", "purpose"],
    },
    {
        "id": "dist-04",
        "query": "Cancel the $5,000 distribution I just made to Sarah",
        "expected_intent": "cancel_distribution",
        "expected_fields": {
            "beneficiary_name": "Sarah",
            "amount": 5000.0,
        },
        "required_fields_present": ["beneficiary_name", "amount"],
    },

    # ── MINUTES ──
    {
        "id": "mins-01",
        "query": "I had a trustee meeting last Tuesday and we decided to approve the annual budget",
        "expected_intent": "log_minutes",
        "expected_fields": {
            "meeting_date": None,  # relative date — just check intent
            "minutes_type": "annual",
        },
        "required_fields_present": ["meeting_date", "minutes_type"],
    },
    {
        "id": "mins-02",
        "query": "Draft minutes for a meeting on June 15, 2026 where we discussed distributions",
        "expected_intent": "log_minutes",
        "expected_fields": {
            "meeting_date": "2026-06-15",
            "minutes_type": "distribution",
        },
        "required_fields_present": ["meeting_date", "minutes_type"],
    },
    {
        "id": "mins-03",
        "query": "I need to document a decision to hire a new CPA for the trust",
        "expected_intent": "log_minutes",
        "expected_fields": {
            "minutes_type": None,  # just check intent
        },
        "required_fields_present": ["minutes_type"],
    },

    # ── BENEFICIARIES ──
    {
        "id": "ben-01",
        "query": "Add a new beneficiary named John Smith with email john@example.com",
        "expected_intent": "create_beneficiary",
        "expected_fields": {
            "name": "John Smith",
            "email": "john@example.com",
        },
        "required_fields_present": ["name"],
    },
    {
        "id": "ben-02",
        "query": "Update Jane's email to jane.new@email.com",
        "expected_intent": "update_beneficiary",
        "expected_fields": {
            "beneficiary_name": "Jane",
            "email": "jane.new@email.com",
        },
        "required_fields_present": ["beneficiary_name", "email"],
    },
    {
        "id": "ben-03",
        "query": "Remove Bob from the trust beneficiaries",
        "expected_intent": "remove_beneficiary",
        "expected_fields": {
            "beneficiary_name": "Bob",
        },
        "required_fields_present": ["beneficiary_name"],
    },

    # ── ASSETS ──
    {
        "id": "asset-01",
        "query": "I bought a rental property at 123 Main St for $350,000 on June 1st",
        "expected_intent": "add_asset",
        "expected_fields": {
            "asset_type": "real_property",
            "description": None,  # check intent + value only
            "value": 350000.0,
        },
        "required_fields_present": ["asset_type", "value"],
    },
    {
        "id": "asset-02",
        "query": "Add a new bank account with $25,000 to the trust assets",
        "expected_intent": "add_asset",
        "expected_fields": {
            "asset_type": "financial_accounts",
            "value": 25000.0,
        },
        "required_fields_present": ["asset_type", "value"],
    },

    # ── COMPENSATION ──
    {
        "id": "comp-01",
        "query": "Set up trustee compensation of $500 per month for myself starting July 1st",
        "expected_intent": "setup_compensation",
        "expected_fields": {
            "amount": 500.0,
            "frequency": "monthly",
        },
        "required_fields_present": ["amount", "frequency"],
    },

    # ── TASKS ──
    {
        "id": "task-01",
        "query": "Remind me to file the 1041 by October 15th",
        "expected_intent": "schedule_task",
        "expected_fields": {
            "task_type": "tax_filing",
            "due_date": None,
        },
        "required_fields_present": ["task_type", "due_date"],
    },

    # ── TRANSACTIONS ──
    {
        "id": "txn-01",
        "query": "Record a $750 payment for trust insurance premium",
        "expected_intent": "add_transaction",
        "expected_fields": {
            "type": "expense",
            "amount": 750.0,
            "category": "insurance",
        },
        "required_fields_present": ["type", "amount", "category"],
    },

    # ── DOCUMENTS ──
    {
        "id": "doc-01",
        "query": "Upload the EIN letter to the vault under tax documents",
        "expected_intent": "upload_document",
        "expected_fields": {
            "title": "EIN letter",
            "category": "tax",
        },
        "required_fields_present": ["title", "category"],
    },
    {
        "id": "doc-02",
        "query": "Find the trust deed in the vault",
        "expected_intent": "review_document",
        "expected_fields": {},
        "required_fields_present": [],
    },

    # ── KNOWLEDGE / READ-ONLY ──
    {
        "id": "know-01",
        "query": "What is the HEMS standard for distributions?",
        "expected_intent": "ask_knowledge",
        "expected_fields": {},
        "required_fields_present": [],
    },
    {
        "id": "know-02",
        "query": "What's my defensibility score?",
        "expected_intent": "health_check",
        "expected_fields": {},
        "required_fields_present": [],
    },
    {
        "id": "know-03",
        "query": "What deadlines are coming up this month?",
        "expected_intent": "check_deadlines",
        "expected_fields": {},
        "required_fields_present": [],
    },
    {
        "id": "know-04",
        "query": "What should I do first as a new trustee?",
        "expected_intent": "recommend_action",
        "expected_fields": {},
        "required_fields_present": [],
    },
    {
        "id": "know-05",
        "query": "I think I missed a deadline and I'm worried",
        "expected_intent": "emergency",
        "expected_fields": {},
        "required_fields_present": [],
    },

    # ── EDGE CASES ──
    {
        "id": "edge-01",
        "query": "Hello, what can you help me with?",
        "expected_intent": "general_chat",
        "expected_fields": {},
        "required_fields_present": [],
    },
    {
        "id": "edge-02",
        "query": "Dismiss the alert about quarterly minutes",
        "expected_intent": "dismiss_alert",
        "expected_fields": {
            "criterion_name": "quarterly minutes",
        },
        "required_fields_present": ["criterion_name"],
    },
    {
        "id": "edge-03",
        "query": "Change the trust name to Smith Family Trust",
        "expected_intent": "change_settings",
        "expected_fields": {
            "field": "trust_name",
            "value": "Smith Family Trust",
        },
        "required_fields_present": ["field", "value"],
    },
]
