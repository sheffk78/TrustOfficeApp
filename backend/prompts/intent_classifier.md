# Intent Classifier — Trust Assistant

## Task
Given a user message in a trust administration context, classify it into exactly one intent category. Return JSON: `{"intent": "...", "confidence": 0.0-1.0, "entities": {...}}`

## Intents

| Intent | Trigger Examples | What the user wants |
|--------|-----------------|-------------------|
| `ask_knowledge` | "What is HEMS?", "How does a 1041 work?", "What's a Schedule A?" | General trust admin information |
| `check_deadlines` | "What's due this month?", "When is my next filing?", "What do I need to do?" | Upcoming deadlines and tasks |
| `health_check` | "How is my trust doing?", "What's my score?", "Am I on track?" | Defensibility score and health status |
| `recommend_action` | "What should I do next?", "What's the most important thing?", "Where do I start?" | Prioritized next steps |
| `log_minutes` | "I had a meeting yesterday", "I need to record a decision", "Draft minutes for..." | Create or draft meeting minutes |
| `add_asset` | "I bought a property", "I need to add a car to the trust", "New asset to log" | Log an asset on Schedule A |
| `create_distribution` | "I need to give money to John", "Distribution to my daughter", "Pay for medical expenses" | Create a distribution record |
| `add_beneficiary` | "I have a new beneficiary", "Add someone to the trust" | Add or update beneficiary info |
| `review_document` | "Find the trust document", "Where's the EIN letter?", "Show me the deed" | Locate a document in the vault |
| `general_chat` | "Hello", "Thanks", "What can you do?", "Tell me a joke" | Greeting, casual, off-topic |
| `emergency` | "I'm worried I messed up", "I think I missed a deadline", "I need help urgently" | Distress, concern, anxiety about trust duties |

## Rules
- If the message contains multiple intents, choose the PRIMARY intent (the action the user most needs)
- Return `confidence` as a float between 0.0 and 1.0
- Extract any `entities` from the message (names, dates, amounts, document types)
- `entities` can be empty `{}` if nothing specific is mentioned
- If multiple intents seem equally strong, prefer the intent that requires action (output) over knowledge (input)

## Output Format
```json
{
  "intent": "check_deadlines",
  "confidence": 0.92,
  "entities": {
    "timeframe": "this month",
    "beneficiary_name": null,
    "amount": null,
    "asset_type": null,
    "date": null
  }
}
```