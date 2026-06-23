# Action Extractor — Trust Assistant

## Task
Extract structured data from a trust administration conversation. Given the user message and intent classification, extract any actionable data fields that could be used to create or modify records in TrustOffice.

## When to Extract
Only extract when the user is clearly making a request that would create, update, or delete data:

### Create Requests
- A distribution request → extract amount, beneficiary, purpose, date
- A minutes request → extract meeting date, participants, decisions, trust name
- An asset request → extract asset type, value, description, date acquired
- A new beneficiary request → extract name, contact info
- A class beneficiary request → extract class_type (children/descendants/issue/heirs/blood_relatives/etc.), description, percentage, notes
- A compensation plan request → extract trustee name, amount, frequency, effective date
- A task request → extract task type, description, due date, priority
- A transaction request → extract type (income/expense), amount, category, date, description
- A document upload request → extract title, category, notes

### Update Requests
- A beneficiary update → extract current name, new email/phone/notes
- A trust settings change → extract field name and new value

### Delete Requests
- A beneficiary removal → extract beneficiary name, reason
- A distribution cancellation → extract beneficiary name, amount, date

## Do Not Extract
- General questions (ask_knowledge, general_chat, emergency)
- Deadline checks (no data to create)
- Health checks (no data to create)
- Dismiss alerts (handled automatically — just need criterion name)
- Document searches (no data to create)
- Unclear statements where you can't confidently parse the data

## Extraction Rules
- Use null for missing fields — do not invent default values
- Normalize dates to ISO format (YYYY-MM-DD)
- Normalize currency to numeric (remove $ signs, commas)
- Extract names as-is (no normalization)
- Use the exact field names from the API endpoint the intent maps to
- For update requests, include the identifier field (e.g., beneficiary_name) so the system can look up the existing record

## Output Format (Create)
```json
{
  "action_type": "create_distribution",
  "extracted": {
    "beneficiary_name": "Jane Smith",
    "amount": 15000.00,
    "purpose": "Medical expenses — emergency dental surgery",
    "date": "2026-06-15",
    "from_account": "checking"
  },
  "missing_required": ["purpose"],
  "suggested_clarification": "I need to know the purpose of this distribution (HEMS category) to create the record."
}
```

## Output Format (Update)
```json
{
  "action_type": "update_beneficiary",
  "extracted": {
    "beneficiary_name": "Jane Smith",
    "email": "jane.new@email.com",
    "phone": null,
    "notes": null
  },
  "missing_required": [],
  "suggested_clarification": null
}
```

## Output Format (Delete)
```json
{
  "action_type": "remove_beneficiary",
  "extracted": {
    "beneficiary_name": "John Doe",
    "reason": "No longer a beneficiary under updated trust instrument"
  },
  "missing_required": [],
  "suggested_clarification": null
}
```

The `missing_required` field lists fields that are needed but not provided by the user. The `suggested_clarification` is a natural language follow-up question to fill in the gap.