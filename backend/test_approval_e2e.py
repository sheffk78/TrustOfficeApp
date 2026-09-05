"""
E2E test of text-approval flow with a mocked MongoDB.
Simulates Kenneth's exact scenario: 'Add TRUE JOY BIRTHING LLC with EIN'
→ entity card pending → user types 'yes' → card executes.
Run with project venv: MONGO_URL=... JWT_SECRET=... .venv/bin/python test_approval_e2e.py
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Mock the database module BEFORE importing approval_handler ---
class FakeCollection:
    def __init__(self, store):
        self.store = store  # dict: conversation docs

    async def find_one(self, query, projection=None):
        conv = self.store.get(query.get("conversation_id"))
        if not conv or query.get("user_id") != conv.get("user_id"):
            return None
        if projection and "_id: 0" not in str(projection):
            pass
        return dict(conv)

    async def update_one(self, query, update):
        conv = self.store.get(query.get("conversation_id"))
        if not conv:
            return
        # support $set on messages.N.action_card.X and top-level
        set_ops = update.get("$set", {})
        for key, val in set_ops.items():
            if key.startswith("messages."):
                parts = key.split(".")
                idx = int(parts[1])
                if len(parts) == 4:  # messages.N.action_card.field
                    conv["messages"][idx]["action_card"][parts[3]] = val
                elif len(parts) == 3:  # messages.N.action_card (whole dict)
                    conv["messages"][idx]["action_card"] = val
            else:
                conv[key] = val
        if "$push" in update:
            conv.setdefault("messages", []).extend(update["$push"]["messages"]["$each"])

    def count_documents(self, query):
        return 0

class FakeDB:
    def __init__(self):
        self.chat_conversations = FakeCollection({
            "conv_test123": {
                "conversation_id": "conv_test123",
                "user_id": "user_1",
                "trust_id": "trust_abc",
                "messages": [
                    {"role": "user", "content": "add TRUE JOY BIRTHING LLC with EIN 42-4457651 as an entity"},
                    {"role": "assistant", "content": "I'll prepare that entity for you.",
                     "action_card": {
                         "type": "entity_preview",
                         "data": {
                             "name": "TRUE JOY BIRTHING LLC",
                             "entity_type": "Holding LLC",
                             "legal_name": "TRUE JOY BIRTHING LLC",
                             "ein": "42-4457651",
                         },
                         "confirmation_status": "pending",
                     }},
                ],
            }
        })

import database
database.db = FakeDB()

# Patch _execute_approved_action on routers.chat (the lazy import inside
# handle_text_approval resolves the attribute from routers.chat at call time)
import routers.chat as _rc
EXEC_CALLED = {}
async def fake_execute(action_card, user_id, trust_id):
    EXEC_CALLED["args"] = (action_card.get("type"), user_id, trust_id, action_card.get("data", {}).get("ein"))
    return {"success": True, "record_id": "ent_999", "endpoint": "entities", "action": "created"}
_rc._execute_approved_action = fake_execute

async def main():
    from approval_handler import is_approval_message, get_latest_pending_action, handle_text_approval

    # 1. Latest pending card is found
    idx, card = await get_latest_pending_action("conv_test123", "user_1")
    assert idx == 1, f"expected index 1, got {idx}"
    assert card["type"] == "entity_preview"
    assert card["data"]["ein"] == "42-4457651"
    print("PASS 1: pending entity card found at message index 1 with EIN intact")

    # 2. 'yes' is approval-shaped
    assert is_approval_message("yes")
    print("PASS 2: 'yes' recognized as approval")

    # 3. handle_text_approval executes and returns confirmation
    result = await handle_text_approval(
        conversation_id="conv_test123",
        message_index=idx,
        action_card=card,
        user_id="user_1",
    )
    assert result["success"] is True
    assert "entity" in result["message"].lower()
    assert "TRUE JOY BIRTHING LLC" in result["message"]
    print(f"PASS 3: execution result -> {result['message']}")

    # 4. Executor got the right args
    etype, uid, tid, ein = EXEC_CALLED["args"]
    assert etype == "entity_preview" and tid == "trust_abc"
    assert ein == "42-4457651"
    print("PASS 4: executor received entity card with EIN 42-4457651 for trust_abc")

    # 5. Card status flipped to approved in DB
    conv = await database.db.chat_conversations.find_one({"conversation_id": "conv_test123", "user_id": "user_1"}, {})
    assert conv["messages"][1]["action_card"]["confirmation_status"] == "approved"
    assert conv["messages"][1]["action_card"]["execution_result"]["record_id"] == "ent_999"
    print("PASS 5: card status flipped to approved + execution_result stored")

    # 6. Failed execution rolls back to pending
    async def failing_execute(action_card, user_id, trust_id):
        return {"success": False, "error": "Duplicate entity name"}
    _rc._execute_approved_action = failing_execute
    card2 = dict(card)
    result2 = await handle_text_approval("conv_test123", idx, card2, "user_1")
    assert result2["success"] is False
    assert "couldn't complete" in result2["message"]
    conv = await database.db.chat_conversations.find_one({"conversation_id": "conv_test123", "user_id": "user_1"}, {})
    assert conv["messages"][1]["action_card"]["confirmation_status"] == "pending"
    print("PASS 6: failed execution rolls card back to pending with clear error message")

    print("\nALL E2E CHECKS PASSED")

asyncio.run(main())