# Action Extractor — Trust Assistant

## Task
Extract structured data from a trust administration conversation. Given the user message and intent classification, extract any actionable data fields that could be used to create records in TrustOffice.

## When to Extract
Only extract when the user is clearly making a request that would create or modify data:
- A distribution request → extract amount, beneficiary, purpose, date
- A minutes request → extract meeting date, participants, decisions, trust name
- An asset request → extract asset type, value, description, date acquired
- A beneficiary request → extract name, contact info, allocation percentage

## Do Not Extract
- General questions (ask_knowledge, general_chat, emergency)
- Deadline checks (no data to create)
- Health checks (no data to create)
- Unclear statements where you can't confidently parse the data

## Extraction Rules
- Use null for missing fields — do not invent default values
- Normalize dates to ISO format (YYYY-MM-DD)
- Normalize currency to numeric (remove $ signs, commas)
- Extract beneficiary names as-is (no normalization)
- Use the exact field names from the API endpoint the intent maps to

## Output Format
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

The `missing_required` field lists fields that are needed but not provided by the user. The `suggested_clarification` is a natural language follow-up question to fill in the gap.