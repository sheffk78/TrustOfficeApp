# Feature: User-Opt-In Database Encryption

**Status:** Design Plan · August 25, 2026
**Author:** Kit
**Sponsor:** Kenneth Kohler

---

## Summary

A per-user toggle (like the existing admin access lock) that, when enabled, encrypts all sensitive trust data at the application layer before it reaches MongoDB. The database stores ciphertext; only the authenticated user's session can decrypt it. This is defense-in-depth on top of the existing admin lockout — even if the database is compromised or an admin bypasses the lock, the data is unreadable without the user's encryption key.

---

## 1. Encryption Approach

### Recommendation: Application-Layer Field-Level Encryption using Fernet (AES-128-CBC + HMAC-SHA256)

**Why not DB-level encryption (MongoDB CSFLE / mongocryptd):**
- We use motor (async) — mongocryptd requires a separate daemon process, adds operational complexity on Railway
- CSFLE enterprise requires MongoDB Atlas Enterprise/Pro tier — cost increase
- Our MongoDB is a managed Railway-hosted instance, not Atlas — no native field-level encryption support

**Why Fernet (from the `cryptography` library, already in requirements.txt):**
- Symmetric authenticated encryption: AES-128-CBC + HMAC-SHA256
- Built-in integrity verification — tampered ciphertext fails decryption
- Automatic IV/nonce generation and timestamp
- Already installed (`cryptography>=42.0.8`)
- Well-documented, battle-tested, Python-native

**What gets encrypted:**
- String fields containing PII or sensitive financial data
- Binary file content in vault_documents
- NOT encrypted: structural fields (doc_id, trust_id, user_id, timestamps, category labels) — these are needed for queries and are not sensitive

---

## 2. What Data Gets Encrypted

### Tier 1 — High Sensitivity (encrypted when feature is ON)

| Collection | Fields to encrypt |
|---|---|
| `trusts` | trust_name, trustee_names, beneficiary_names, trust_details, notes |
| `vault_documents` | file_content (BSON binary), title, description, file_name |
| `beneficiaries` | name, email, phone, address, relationship, notes |
| `transactions` | description, payee, memo, amount (searchable hash separately) |
| `bank_accounts` | account_number, routing_number, bank_name, account_nickname |
| `bank_statements` | bank_name, account_last_four |
| `investments` | description, institution, account_number |
| `client_notes` | note_content, contact_name |
| `successor_access` | successor_name, successor_email, successor_phone |
| `compensation_plans` | compensation_terms, notes |
| `compensation_payments` | amount, memo |
| `distribution_records` | recipient, amount, purpose, notes |
| `governance_tasks` | description, notes |
| `minutes_records` | content, attendees, notes |
| `expenses` | description, payee, amount |
| `communications` | content, recipient |
| `contacts` (via clients) | name, email, phone, address |
| `chat_conversations` | messages, context |
| `personal_vendors` | vendor_name, account_number, contact_info |

### Tier 2 — Structural fields (NOT encrypted — needed for queries)

- `_id`, `doc_id`, `trust_id`, `user_id`, `created_at`, `updated_at`
- `category`, `category_label`, `storage_provider`, `needs_renewal`
- `tags` (used for filtering)
- `status`, `type` enums

### Design: Encrypted Wrapper

Each encrypted field is stored as a Fernet token (base64 string) in the same field position. A metadata flag on the document (`_encrypted: true`) indicates encryption state.

```python
# Before: {"trust_name": "Smith Family Trust", "trustee_names": ["John Smith"]}
# After:  {"trust_name": "gAAAAAB...", "trustee_names": ["gAAAAAB...", "gAAAAAB..."], "_encrypted": true}
```

---

## 3. Toggle Mechanism (Following Existing Pattern)

### Backend: `backend/routers/preferences.py`

Add `data_encryption_enabled` to the preferences model, following the exact same pattern as `admin_access_locked`:

```python
# backend/models.py — extend UserPreferences
class UserPreferences(BaseModel):
    hide_watermark: bool = False
    admin_access_locked: bool = False
    data_encryption_enabled: bool = False          # NEW

class UserPreferencesUpdate(BaseModel):
    hide_watermark: Optional[bool] = None
    admin_access_locked: Optional[bool] = None
    data_encryption_enabled: Optional[bool] = None  # NEW
```

```python
# backend/routers/preferences.py — update get_user_preferences defaults
return {
    "user_id": user["user_id"],
    "hide_watermark": hide_watermark,
    "admin_access_locked": False,
    "data_encryption_enabled": False   # NEW
}
```

The PUT endpoint already handles arbitrary fields via `prefs.dict()` → `$set`, so no change needed there.

### Frontend: `frontend/src/pages/SettingsPage.js`

Add a new toggle switch below the admin access lock toggle (line ~2480), using the same pattern:

```javascript
// State
const [userPrefs, setUserPrefs] = useState({ 
    hide_watermark: false, 
    admin_access_locked: false,
    data_encryption_enabled: false  // NEW
});

// Toggle handler
const toggleDataEncryption = async () => {
    const newValue = !userPrefs.data_encryption_enabled;
    // Show confirmation modal: "Enabling encryption will encrypt all your existing data. 
    //   This may take a few minutes. You cannot search encrypted fields while enabled.
    //   Disabling encryption will decrypt all data back to plaintext."
    const response = await fetch('/api/user/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ data_encryption_enabled: newValue })
    });
    if (response.ok) {
        setUserPrefs({ ...userPrefs, data_encryption_enabled: newValue });
    }
};
```

---

## 4. Key Derivation and Storage Strategy

### The Core Problem

The encryption key must:
1. Be unique per user (compromise of one key doesn't compromise all users)
2. Be available when the user is authenticated
3. NOT be stored in plaintext in the database (defeats the purpose)
4. Survive server restarts

### Recommended Approach: Master Key + Per-User Derived Keys

```
┌─────────────────────────────────────────────────────────┐
│  ENVIRONMENT VARIABLE (Railway secret)                  │
│  ENCRYPTION_MASTER_KEY = <32-byte random key>            │
│  (set once, never changes, never in DB)                 │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  PER-USER KEY DERIVATION                                 │
│  key = HKDF(master_key, salt=user_id, info="TrustOffice")│
│  - Deterministic: same user → same key                  │
│  - No key storage needed — derived on demand            │
│  - If master key rotates, all data needs re-encryption  │
└─────────────────────────────────────────────────────────┘
```

```python
# backend/encryption.py (NEW FILE)

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
import base64
import os
import logging

logger = logging.getLogger(__name__)

MASTER_KEY = os.environ.get("ENCRYPTION_MASTER_KEY")
if not MASTER_KEY:
    raise RuntimeError("ENCRYPTION_MASTER_KEY environment variable is required for encryption feature")

_master_key_bytes = base64.urlsafe_b64decode(MASTER_KEY)

def get_user_fernet(user_id: str) -> Fernet:
    """Derive a per-user Fernet key from the master key + user_id."""
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=user_id.encode(),
        info=b"TrustOffice-field-encryption-v1",
    )
    derived = kdf.derive(_master_key_bytes)
    return Fernet(base64.urlsafe_b64encode(derived))

def encrypt_field(value, fernet: Fernet):
    """Encrypt a single field value. Handles str, bytes, and lists."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return fernet.encrypt(value)
    if isinstance(value, list):
        return [encrypt_field(item, fernet) for item in value]
    return fernet.encrypt(str(value).encode())

def decrypt_field(value, fernet: Fernet, original_type=str):
    """Decrypt a single field value back to its original type."""
    if value is None:
        return None
    if isinstance(value, list):
        return [decrypt_field(item, fernet, original_type) for item in value]
    if isinstance(value, bytes) and not value.startswith(b'gAAAA'):
        # Already raw bytes (not a Fernet token) — return as-is
        return value
    try:
        plaintext = fernet.decrypt(value)
        if original_type == bytes:
            return plaintext
        if original_type == float:
            return float(plaintext.decode())
        if original_type == int:
            return int(plaintext.decode())
        return plaintext.decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return None
```

### Why This Approach (vs. Alternatives)

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **Master key + HKDF per user** (recommended) | No key storage, deterministic, simple | Master key compromise = all data exposed | ✅ Best balance |
| Per-user random keys stored encrypted in DB | Master key compromise doesn't expose all keys | More complex, key management overhead | Overkill for our stage |
| User password-derived keys | Even admin can't decrypt without password | Password change = re-encrypt all data; session can't persist keys | Too brittle for trust software |

### Key Rotation

If the master key ever needs rotation:
1. Set `ENCRYPTION_MASTER_KEY_V2` as the new key
2. Background job re-encrypts all documents using the new key
3. `ENCRYPTION_MASTER_KEY` updated; old key retired
4. This is a rare, planned operation — document as runbook

---

## 5. Enabling Encryption (Migration of Existing Data)

### When user turns ON encryption:

```python
# backend/routers/preferences.py — in update_user_preferences, after $set:
if "data_encryption_enabled" in update_fields and update_fields["data_encryption_enabled"]:
    # Trigger background migration
    import asyncio
    asyncio.create_task(migrate_user_data_to_encrypted(user["user_id"]))
```

```python
# backend/encryption_migration.py (NEW FILE)

from database import db
from encryption import get_user_fernet, encrypt_field
import logging

logger = logging.getLogger(__name__)

# Collections and fields to encrypt
ENCRYPTED_COLLECTIONS = {
    "trusts": ["trust_name", "trustee_names", "beneficiary_names", "trust_details", "notes"],
    "vault_documents": ["file_content", "title", "description", "file_name"],
    "beneficiaries": ["name", "email", "phone", "address", "relationship", "notes"],
    "transactions": ["description", "payee", "memo"],
    "bank_accounts": ["account_number", "routing_number", "bank_name", "account_nickname"],
    "investments": ["description", "institution", "account_number"],
    "client_notes": ["note_content", "contact_name"],
    "successor_access": ["successor_name", "successor_email", "successor_phone"],
    "compensation_plans": ["compensation_terms", "notes"],
    "compensation_payments": ["amount", "memo"],
    "distribution_records": ["recipient", "amount", "purpose", "notes"],
    "governance_tasks": ["description", "notes"],
    "minutes_records": ["content", "attendees", "notes"],
    "expenses": ["description", "payee", "amount"],
    "communications": ["content", "recipient"],
    "chat_conversations": ["messages", "context"],
    "personal_vendors": ["vendor_name", "account_number", "contact_info"],
    "bank_statements": ["bank_name", "account_last_four"],
}

async def migrate_user_data_to_encrypted(user_id: str):
    """Background task: encrypt all of a user's existing data."""
    fernet = get_user_fernet(user_id)
    
    for collection_name, fields in ENCRYPTED_COLLECTIONS.items():
        collection = db[collection_name]
        cursor = collection.find({"user_id": user_id, "_encrypted": {"$ne": True}})
        
        async for doc in cursor:
            updates = {}
            for field in fields:
                if field in doc and doc[field] is not None:
                    encrypted_value = encrypt_field(doc[field], fernet)
                    updates[field] = encrypted_value
            
            if updates:
                updates["_encrypted"] = True
                await collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": updates}
                )
        
        logger.info(f"Encrypted {collection_name} for user {user_id}")
    
    # Mark migration complete in preferences
    await db.user_preferences.update_one(
        {"user_id": user_id},
        {"$set": {"encryption_migration_complete": True}}
    )
    logger.info(f"Encryption migration complete for user {user_id}")
```

### UX During Migration

- Frontend shows "Encrypting your data..." spinner with progress
- Migration runs as background task — user can continue using the app
- New writes are encrypted immediately (the encryption layer checks the preference flag)
- Read operations during migration: if `_encrypted: true` → decrypt; if not → return as-is (plaintext)
- This dual-mode read is the key design — it handles the transition gracefully

---

## 6. Disabling Encryption (Decryption Back to Plaintext)

### When user turns OFF encryption:

```python
async def migrate_user_data_to_plaintext(user_id: str):
    """Background task: decrypt all of a user's data back to plaintext."""
    fernet = get_user_fernet(user_id)
    
    for collection_name, fields in ENCRYPTED_COLLECTIONS.items():
        collection = db[collection_name]
        cursor = collection.find({"user_id": user_id, "_encrypted": True})
        
        async for doc in cursor:
            updates = {}
            for field in fields:
                if field in doc and doc[field] is not None:
                    decrypted_value = decrypt_field(doc[field], fernet)
                    updates[field] = decrypted_value
            
            if updates:
                updates["_encrypted"] = False
                await collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": updates}
                )
    
    await db.user_preferences.update_one(
        {"user_id": user_id},
        {"$set": {"encryption_migration_complete": False, "_encrypted": False}}
    )
```

---

## 7. The Encryption/Decryption Layer (Where It Lives in the Code)

### Design: Middleware-Lite Approach

Rather than modifying every router, create a helper that each router calls for read/write operations. This is the least invasive approach that doesn't require restructuring the entire codebase.

```python
# backend/encryption.py (cont.)

async def is_encryption_enabled(user_id: str) -> bool:
    """Check if the user has encryption enabled."""
    pref = await db.user_preferences.find_one(
        {"user_id": user_id},
        {"data_encryption_enabled": 1, "_id": 0}
    )
    return pref and pref.get("data_encryption_enabled") is True

async def encrypt_doc(doc: dict, user_id: str, collection_name: str) -> dict:
    """Encrypt sensitive fields in a document before DB insert."""
    if not await is_encryption_enabled(user_id):
        return doc
    
    fernet = get_user_fernet(user_id)
    fields = ENCRYPTED_COLLECTIONS.get(collection_name, [])
    
    encrypted = dict(doc)
    for field in fields:
        if field in encrypted and encrypted[field] is not None:
            encrypted[field] = encrypt_field(encrypted[field], fernet)
    encrypted["_encrypted"] = True
    return encrypted

async def decrypt_doc(doc: dict, user_id: str, collection_name: str) -> dict:
    """Decrypt sensitive fields in a document after DB read."""
    if not doc.get("_encrypted"):
        return doc  # Plaintext — no action needed (dual-mode read)
    
    fernet = get_user_fernet(user_id)
    fields = ENCRYPTED_COLLECTIONS.get(collection_name, [])
    
    decrypted = dict(doc)
    for field in fields:
        if field in decrypted and decrypted[field] is not None:
            decrypted[field] = decrypt_field(decrypted[field], fernet)
    return decrypted
```

### Router Integration Pattern

Each router that handles sensitive data calls `encrypt_doc` before insert and `decrypt_doc` after find:

```python
# Example: backend/routers/vault.py — upload_document
# BEFORE:
await db.vault_documents.insert_one(record)

# AFTER:
from encryption import encrypt_doc, decrypt_doc
record = await encrypt_doc(record, user["user_id"], "vault_documents")
await db.vault_documents.insert_one(record)

# Example: download_document
# BEFORE:
doc = await db.vault_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]})

# AFTER:
doc = await db.vault_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]})
doc = await decrypt_doc(doc, user["user_id"], "vault_documents")
```

### Files Requiring This Integration

| File | Collections touched |
|---|---|
| `backend/routers/vault.py` | vault_documents |
| `backend/routers/trusts.py` (if exists) or `backend/server.py` | trusts |
| `backend/routers/beneficiaries.py` | beneficiaries |
| `backend/routers/transactions.py` | transactions |
| `backend/routers/banking.py` | bank_accounts, bank_statements |
| `backend/routers/investments.py` | investments |
| `backend/routers/client_notes.py` | client_notes |
| `backend/routers/successor.py` | successor_access |
| `backend/routers/compensation.py` | compensation_plans, compensation_payments |
| `backend/routers/distributions.py` | distribution_records |
| `backend/routers/governance.py` | governance_tasks |
| `backend/routers/minutes.py` | minutes_records |
| `backend/routers/expenses.py` | expenses |
| `backend/routers/communications.py` | communications |
| `backend/routers/chat.py` | chat_conversations |
| `backend/routers/exports.py`, `exports_enhanced.py`, `full_export.py` | multiple (decrypt before export) |
| `backend/routers/admin_api.py` | decrypt when viewing user data (respect admin lock) |

---

## 8. Search/Query Impact and Mitigations

### The Problem

Encrypted fields cannot be queried with MongoDB's native query operators (`$regex`, `$eq`, `$gt`, etc.). Searching for "Smith" in an encrypted `trust_name` field is impossible without decryption.

### Mitigation: Searchable Hash Indexes

For fields that need search capability, store a deterministic HMAC hash alongside the encrypted value:

```python
import hmac
import hashlib

def create_search_hash(value: str, user_id: str) -> str:
    """Create a deterministic HMAC hash for exact-match search."""
    return hmac.new(
        user_id.encode(),
        str(value).encode(),
        hashlib.sha256
    ).hexdigest()
```

```python
# Document stored as:
{
    "trust_name": "gAAAAAB...",  # encrypted
    "trust_name_search": "a1b2c3...",  # HMAC hash for exact match
    "_encrypted": true
}

# Query: db.trusts.find({"trust_name_search": create_search_hash("Smith Family Trust", user_id)})
```

### What This Means in Practice

| Query Type | Supported? | How |
|---|---|---|
| Exact match (e.g., "find trust named X") | ✅ | HMAC hash lookup |
| Partial/regex search (e.g., "find trusts containing 'Smith'") | ❌ | Not possible on encrypted fields — decrypt in Python and filter |
| Range queries (e.g., "amount > 1000") | ❌ | Not possible — decrypt in Python |
| Sort by encrypted field | ❌ | Decrypt in Python and sort |
| Filter by non-encrypted field (trust_id, category, tags) | ✅ | Works normally |

### Recommendation

For trust administration software, most queries filter by `trust_id`, `user_id`, `category`, `tags`, or `doc_id` — all of which remain unencrypted. Free-text search on encrypted content is rare. When needed, decrypt the result set and filter in Python.

**Impact: Minimal for normal usage. Document the search limitation in the UI when encryption is enabled.**

---

## 9. Security Considerations and Threat Model

### Threats Addressed

| Threat | Mitigation |
|---|---|
| Database compromise (attacker gets DB dump) | ✅ Data is ciphertext without the master key |
| Admin bypass (admin accesses user data despite lock) | ✅ Admin lock already blocks this; encryption is defense-in-depth |
| Insider threat (developer with DB access) | ✅ Master key is in Railway env var, not in code or DB |
| Network interception | ✅ TLS already in place; encryption adds application-layer protection |
| Backup leakage | ✅ DB backups contain ciphertext |

### Threats NOT Addressed (Honest Limitations)

| Threat | Why Not |
|---|---|
| Server compromise (attacker gets app server + env vars) | Master key is in env — if server is compromised, key is exposed |
| Active session hijacking | Authenticated user's session can decrypt — hijacked session has access |
| Side-channel attacks | Fernet is constant-time for HMAC verification, but timing attacks are theoretically possible |

### Key Management Rules

1. `ENCRYPTION_MASTER_KEY` is set as a Railway environment variable (secret)
2. Never logged, never returned in API responses, never written to DB
3. Generated once using `Fernet.generate_key()` — stored in Railway
4. Backed up offline (password manager, not in the codebase)
5. If compromised: rotate key + re-encrypt all data (documented runbook)

---

## 10. Implementation File List

### New Files

| File | Purpose |
|---|---|
| `backend/encryption.py` | Core encryption/decryption module (Fernet, HKDF, encrypt_doc, decrypt_doc) |
| `backend/encryption_migration.py` | Background migration tasks (encrypt all, decrypt all) |
| `backend/tests/test_encryption.py` | Unit + integration tests |
| `frontend/src/components/settings/EncryptionToggle.js` | Reusable encryption toggle component with confirmation modal |

### Modified Files

| File | Change |
|---|---|
| `backend/models.py` | Add `data_encryption_enabled` to UserPreferences + UserPreferencesUpdate |
| `backend/routers/preferences.py` | Add `data_encryption_enabled: False` to defaults; trigger migration on toggle |
| `backend/routers/vault.py` | Call encrypt_doc/decrypt_doc on insert/read |
| `backend/routers/trusts.py` (or server.py trusts endpoints) | Same |
| `backend/routers/beneficiaries.py` | Same |
| `backend/routers/transactions.py` | Same |
| `backend/routers/banking.py` | Same |
| `backend/routers/investments.py` | Same |
| `backend/routers/client_notes.py` | Same |
| `backend/routers/successor.py` | Same |
| `backend/routers/compensation.py` | Same |
| `backend/routers/distributions.py` | Same |
| `backend/routers/governance.py` | Same |
| `backend/routers/minutes.py` | Same |
| `backend/routers/expenses.py` | Same |
| `backend/routers/exports*.py` | Decrypt before export |
| `backend/routers/admin_api.py` | Decrypt when viewing user data (respects admin lock) |
| `backend/routers/chat.py` | Encrypt/decrypt chat messages |
| `backend/server.py` | Ensure `ENCRYPTION_MASTER_KEY` env var check at startup |
| `frontend/src/pages/SettingsPage.js` | Add encryption toggle UI (below admin lock, ~line 2480) |
| `frontend/src/components/vault/vaultOperations.js` | Handle encrypted search limitation indicator |

### Railway Environment Variables

| Variable | Value |
|---|---|
| `ENCRYPTION_MASTER_KEY` | `Fernet.generate_key()` output (base64-encoded 32 bytes) |

---

## 11. Testing Strategy

### Unit Tests (`backend/tests/test_encryption.py`)

```python
def test_encrypt_decrypt_roundtrip():
    """Encrypt then decrypt returns original value."""
    
def test_encrypt_different_users_different_keys():
    """Same value encrypted by different users produces different ciphertext."""
    
def test_decrypt_wrong_key_fails():
    """Decrypting with wrong key raises InvalidToken."""
    
def test_encrypt_none_returns_none():
    """None values pass through unchanged."""
    
def test_encrypt_list_encrypts_each_item():
    """List fields are encrypted element-by-element."""
    
def test_search_hash_deterministic():
    """Same value + user_id produces same hash."""
    
def test_search_hash_different_users():
    """Same value + different user_id produces different hashes."""
```

### Integration Tests

```python
async def test_toggle_on_encrypts_new_data():
    """Turn on encryption → insert document → verify stored as ciphertext."""
    
async def test_toggle_on_migrates_existing_data():
    """Turn on encryption → wait for migration → verify all existing docs encrypted."""
    
async def test_toggle_off_decrypts_all_data():
    """Turn off encryption → verify all data returns to plaintext."""
    
async def test_dual_mode_read_during_migration():
    """During migration, encrypted and plaintext docs both readable."""
    
async def test_admin_cannot_read_encrypted_data():
    """Admin endpoint respects encryption — returns ciphertext or requires user context."""
    
async def test_vault_download_works_encrypted():
    """Upload file with encryption ON → download → verify file integrity."""
    
async def test_search_exact_match_with_hash():
    """Exact match search using HMAC hash works on encrypted fields."""
```

### Frontend Tests

```javascript
test('encryption toggle shows confirmation modal');
test('encryption toggle calls PUT /api/user/preferences');
test('encryption enabled shows search limitation notice');
test('vault upload works with encryption enabled');
test('vault download works with encryption enabled');
```

---

## 12. Implementation Sequence

1. **Phase 1 (Backend Core):** `encryption.py` + `encryption_migration.py` + models update + env var setup
2. **Phase 2 (Backend Integration):** Update vault.py first (most sensitive), then other routers one-by-one
3. **Phase 3 (Frontend):** Settings toggle + confirmation modal + search limitation indicator
4. **Phase 4 (Testing):** Unit tests → integration tests → manual E2E
5. **Phase 5 (Deploy):** Set `ENCRYPTION_MASTER_KEY` in Railway → deploy → test on staging

**Estimated effort:** 2-3 days of focused implementation. The dual-mode read design means it can be rolled out incrementally — encrypt one collection at a time without breaking anything.