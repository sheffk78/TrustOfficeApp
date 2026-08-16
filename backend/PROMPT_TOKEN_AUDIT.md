# Trust Assistant — Prompt Engineering & Token Efficiency Audit

## Executive Summary

The system prompt is assembled dynamically per message from: split constitution files (core + actions + escalation), live trust context (MongoDB data), vault/trust-document analysis, trust-type guidance, knowledge base excerpts, conversation history, and response format instructions. Estimated total system prompt sizes:

| Intent | Estimated Chars | Estimated Tokens |
|---|---|---|
| `ask_knowledge` | ~14,900 | ~3,720 |
| `create_distribution` (action) | ~25,600 | ~6,400 |
| `general_chat` | ~11,000 | ~2,750 |

*Token estimates use ~4 chars/token (Gemini tokenizer approximation). Actual may vary ±10%.*

The largest prompt (`create_distribution`) is **6,400 tokens** of system prompt alone, before the user message. With `max_tokens=2000` for responses, the total per-turn cost is ~8,400 tokens. This is manageable for Gemini 2.5 Flash (1M context) but wasteful for latency and cost at scale.

---

## Recommendations (Ordered by Estimated Savings)

### 1. 🔴 Skip escalation prompt for `general_chat` — Save ~735 tokens

**Current**: `_ESCALATION_INTENTS = _ACTION_INTENTS | {"ask_knowledge", "emergency"}` — escalation is NOT loaded for `general_chat`, which is correct. However, `ask_knowledge` ALWAYS loads escalation (~735 tokens) even for simple questions like "What is a Schedule A?" that have no fiduciary dimension.

**Recommendation**: Only load escalation for `ask_knowledge` when the user message contains fiduciary trigger keywords (legal, tax, distribution, liability, etc.) — not unconditionally.

**Savings**: ~735 tokens for most `ask_knowledge` queries (currently ~3,720 → ~2,985 tokens).

### 2. 🔴 Reduce knowledge context limit from 4500 to 3000 chars — Save ~375 tokens

**Current**: `knowledge_context[:4500]` truncates at 4500 chars (~1,125 tokens).

**Analysis**: The per-topic excerpt limits already cap individual files at 900–3000 chars. For `ask_knowledge` (no pinned product files), the knowledge context typically reaches 2,000–3,000 chars. For action intents with 4 pinned product files, the context reaches the 4500 cap. However, the pinned product files are the ones most relevant to action intents, and their individual limits (3000/2500/2200/1400) already exceed what most queries need.

**Recommendation**: Lower the global truncation to **3000 chars** for `ask_knowledge`/`general_chat` and **3500 chars** for action intents. The per-topic excerpt limits are the real quality gate; the global cap just catches edge cases.

**Savings**: ~375 tokens on action intents (4500→3500), ~0 tokens on knowledge/chat (already under 3000).

### 3. 🟡 Deduplicate trust_type_guidance with knowledge context — Save ~86 tokens

**Current**: `_build_trust_type_guidance` extracts "Key Governance Requirements" + "Distribution Rules" sections from the trust-type file (~1,329 chars / ~332 tokens). When the user's message also triggers keyword matching for the same trust-type file (e.g., they mention "revocable"), the knowledge context loads the first 900 chars of that same file, which includes a partial copy of "Key Governance Requirements" (~346 chars / ~86 tokens).

**Analysis**: This is NOT full double-loading — the knowledge excerpt is truncated at 900 chars and only captures the beginning of the Key Governance section, while trust_type_guidance has the full sections. However, it is wasteful.

**Recommendation**: In `_format_knowledge_context`, when a trust-type file is already covered by `trust_type_guidance`, either:
- Skip it from the knowledge context entirely, OR
- Use the `relevant_excerpt` function to extract a DIFFERENT section (e.g., "What It Is" or "Common Pitfalls") instead of the default first-N-chars that overlaps with guidance.

**Savings**: ~86 tokens when the user mentions their trust type (partial overlap case).

### 4. 🟡 Compact the JSON response format instructions — Save ~150 tokens

**Current**: The non-streaming response format block is ~926 chars / ~231 tokens. It includes:
- A 3-line "What I'm basing this on" instruction (already in `chat_system_core.md` § Response Structure)
- Citation/article/section instructions (also in `chat_system_core.md`)
- A verbose JSON schema with field descriptions

**Analysis**: The "What I'm basing this on / What I don't know / Caveat language" instructions at lines 1383-1385 DUPLICATE the "Response Structure" section in `chat_system_core.md` (lines 12-22). The JSON schema with inline comments like `"type": "create_distribution_preview" if requires_write else null` adds unnecessary tokens.

**Recommendation**: 
- Remove the duplicated response structure instructions (already in core constitution).
- Compact the JSON schema to:
```json
{"message":"...","action_card":{"type":"...","data":{},"requires_confirmation":true}|null,"citation_note":"...","unknown_note":"...","caveat":"..."}
```
- For `general_chat`, skip the JSON schema entirely (action_card is always null, response can be plain text).

**Savings**: ~150 tokens per response (926 → ~550 chars).

### 5. 🟡 Load actions constitution only for write intents — Save ~2,000 tokens (read-only action intents)

**Current**: `CHAT_SYSTEM_ACTIONS` (~8,000 chars / ~2,000 tokens) is loaded for ALL intents in `_ACTION_INTENTS`, including read-only intents like `check_deadlines`, `health_check`, `recommend_action`, `review_document`, `dismiss_alert`.

**Analysis**: The actions file contains detailed rules for beneficiary actions, asset valuation, minutes creation, distribution governance rails, and proactive nudges. These are only relevant when the AI is actually proposing or executing a write action. Read-only intents don't need the "Proactive Offers After Beneficiary Actions" or "Governance Rails for Chat Actions" sections.

**Recommendation**: Split `_ACTION_INTENTS` into `_WRITE_INTENTS` (load actions) and `_READ_ACTION_INTENTS` (skip actions, load only the relevant subset or skip entirely). Or create a lightweight `chat_system_actions_read.md` with just the "Guiding Users Who Don't Know What to Do" section.

**Savings**: ~2,000 tokens for `check_deadlines`, `health_check`, `recommend_action`, `review_document`, `dismiss_alert` intents.

### 6. 🟢 Reduce per-topic excerpt limits for product files — Save ~200–500 tokens

**Current**: 
- `15-trustoffice-scenarios`: 3000 chars
- `14-trustoffice-page-playbooks`: 2500 chars  
- `13-trustoffice-workflows`: 2200 chars
- `12-trustoffice-features`: 1400 chars

**Analysis**: The `relevant_excerpt` function tries to find the matching section heading first, then falls back to the first N chars. When it finds the right section, 3000 chars is generous — most individual scenario sections are 500–1000 chars. When it falls back to the first N chars, the content is often the file header/intro, not the relevant section.

**Recommendation**: Lower limits to 2000/1800/1500/1000 respectively. The section-hint matching already targets the right content; the limit is just a ceiling, and lowering it forces more precise extraction. For the fallback (no section match), the first 1000–2000 chars of these files are intro material of varying relevance.

**Savings**: ~200–500 tokens on action intents (where pinned product files are loaded).

### 7. 🟢 FTS5 fallback — reduce snippet limit from 600 to 400 chars — Save ~100 tokens

**Current**: When keyword matching finds <3 files, FTS5 adds 2 snippets of up to 600 chars each = ~1,200 chars / ~300 tokens.

**Analysis**: FTS snippets are search-result excerpts, not full sections. 400 chars is sufficient for the AI to determine if the content is relevant and reference it. The FTS5 fallback triggers primarily for `general_chat` and vague `ask_knowledge` queries.

**Recommendation**: Lower `item_snippet[:600]` to `item_snippet[:400]`. Also, consider lowering the threshold from `<3` to `<2` — if keyword matching already found 2 relevant files, FTS5 is unlikely to add value.

**Savings**: ~100 tokens when FTS triggers.

### 8. 🟢 Conversation history: increase from 5 messages × 200 chars to 8 messages × 300 chars — Cost: +175 tokens

**Current**: `_fmt_history` takes the last 5 messages, truncating each to 200 chars. Total: ~1,000 chars / ~250 tokens.

**Analysis**: 200 chars per message is too aggressive for multi-turn trust conversations. A trustee asking "Can I distribute $5,000 to my daughter for tuition?" followed by the AI's response about HEMS standards, and then "What about $10,000 for her graduate program?" — the 200-char truncation cuts off the AI's prior HEMS analysis, losing critical context.

**Recommendation**: Increase to **8 messages × 300 chars** (2,400 chars / ~600 tokens). This is a modest cost increase (+350 tokens) but significantly improves multi-turn coherence for complex trust decisions. The 300-char limit preserves the key reasoning from prior turns while still preventing runaway context growth.

**Net cost**: +175 tokens (but quality improvement justifies it).

### 9. 🟢 Remove legacy `chat_system.md` from module load — Save 0 tokens (memory only)

**Current**: Lines 56-57 load the legacy 19,184-char `chat_system.md` at import time. It's never used in the prompt (comment says "unused in split mode").

**Recommendation**: Remove the file load. No token savings (it's not in the prompt), but saves ~19KB of memory and removes confusion.

---

## Detailed Analysis by Question

### 1. Token Budget by Intent Type

| Component | ask_knowledge | create_distribution | general_chat |
|---|---|---|---|
| Constitution (core+actions+escalation) | 8,174 / 2,043 | 16,970 / 4,242 | 5,237 / 1,309 |
| Trust context sections | 769 / 192 | 929 / 232 | 769 / 192 |
| Vault section | 0 / 0 | 381 / 95 | 0 / 0 |
| Trust type guidance | 1,389 / 347 | 1,389 / 347 | 1,389 / 347 |
| Knowledge base (4500 cap) | 3,088 / 772 | 4,500 / 1,125 | 2,166 / 541 |
| Conversation history | 342 / 85 | 336 / 84 | 320 / 80 |
| Response format | 922 / 231 | 926 / 231 | 921 / 231 |
| **TOTAL** | **14,884 / 3,721** | **25,631 / 6,407** | **11,002 / 2,750** |

*(chars / ~tokens)*

**Key finding**: `create_distribution` at 6,400 tokens is 2.3× the `general_chat` prompt. The constitution base (core + actions + escalation + distribution protocol) accounts for 66% of the total. The knowledge base adds another 18%.

### 2. Redundancy: Constitution vs Knowledge Files

The constitution files (core + actions + escalation) and the knowledge files share conceptual territory but are NOT heavily duplicated:

- **HEMS standard**: Mentioned in core constitution AND 19 knowledge files. The core says "cite HEMS standard" while knowledge files explain HEMS in detail. This is **complementary, not redundant**.
- **Fiduciary duty**: In escalation constitution AND 6 knowledge files. The escalation file covers referral language; knowledge files cover duty definitions. **Complementary**.
- **Professional escalation templates** (CPA, attorney, financial advisor): In escalation constitution AND partially in 3-8 knowledge files. The escalation file has the exact referral templates; knowledge files mention professionals in passing. **Low redundancy**.
- **"Trust document analysis"**: In core constitution AND 1 knowledge file. **Minimal overlap**.

**Conclusion**: No significant content duplication between constitution and knowledge files. The constitution provides behavioral rules; the knowledge files provide domain content. They reference the same concepts but serve different purposes.

### 3. trust_type_guidance Redundancy with Knowledge Context

**Not full double-loading.** Partial overlap in one specific case:

- `_build_trust_type_guidance` extracts "Key Governance Requirements" + "Distribution Rules" (~1,329 chars avg across trust types)
- `_format_knowledge_context` keyword-matches the same trust-type file when the user mentions the trust type (e.g., "revocable")
- When keyword-matched, the knowledge excerpt is capped at 900 chars (default limit for non-pinned files), which includes the beginning of "Key Governance Requirements" (~346 chars of partial overlap)
- The full "Distribution Rules" section (starting at ~pos 2090 in the file) is NEVER in the 900-char knowledge excerpt
- For action intents, the trust-type file is usually pushed out by the `selected[:5]` cap (4 pinned product files + 1 keyword match = 5 slots used)

**Verdict**: ~86 tokens of partial overlap when the user explicitly mentions their trust type. Not a major issue, but fixable by excluding the governance/dist-rules sections from the knowledge excerpt when the same file is in trust_type_guidance.

### 4. FTS5 Fallback Analysis

**When it triggers**: Keyword matching finds <3 files (primarily `general_chat` and vague `ask_knowledge`).

**What it adds**: 2 FTS snippets, each capped at 600 chars = ~1,200 chars / ~300 tokens.

**Redundancy risk**: The FTS5 snippets are from the SQLite FTS5 index, which indexes the same knowledge files. If keyword matching already found 1-2 files, FTS5 may surface the same files' content from a different section. The dedup check (`item_title not in "\n".join(sections)`) only checks the title, not content — so a different section of the same file could be added.

**Cost**: ~300 tokens. Low impact, but the dedup check should be strengthened to skip FTS results from files already in the knowledge context.

### 5. Prompt Structure / Section Ordering

**Current order** in `_build_system_prompt`:
1. Constitution (core → actions → escalation → dist protocol)
2. Current Trust Context (profile, health score)
3. Vault section
4. Trust Type Guidance
5. Context sections (deadlines, pending, activity, beneficiaries, entities, tax, money, structure)
6. Knowledge Base
7. Conversation History
8. Current Intent
9. Response format instructions

**Analysis**: 
- Trust Type Guidance (section 4) appears BEFORE Knowledge Base (section 6). This is **suboptimal** — the trust type guidance is a brief extract from the same knowledge file that may appear in the knowledge base. Placing it before the knowledge base means the AI sees the governance/dist-rules extract first, then potentially the same file's intro/other sections in the knowledge base. This creates a fragmented view of the same source.
- **Recommendation**: Move Trust Type Guidance AFTER the Knowledge Base section, or merge it into the Knowledge Base as a pinned first entry. This gives the AI a coherent view: "Here's the specific guidance for your trust type, followed by the broader knowledge base context."
- The Current Intent section (section 8) is good placement — it's near the end where the AI's attention is focused before generating the response.
- The Response Format instructions (section 9) are correctly placed last.

### 6. Per-Topic Excerpt Limits

| Topic | Current Limit | Recommended | Rationale |
|---|---|---|---|
| 15-trustoffice-scenarios | 3000 | 2000 | Individual scenarios are 500–1000 chars; section-hint matching finds the right one |
| 14-trustoffice-page-playbooks | 2500 | 1800 | Page playbooks are structured per-page; matching extracts the right page |
| 13-trustoffice-workflows | 2200 | 1500 | Workflow sections are concise step lists |
| 12-trustoffice-features | 1400 | 1000 | Feature descriptions are brief |
| Default (all other topics) | 900 | 700 | Trust-type/conceptual files: 700 chars covers "What It Is" + start of governance |

**Quality impact**: Low. The `relevant_excerpt` function's section-hint matching is the real quality driver. The limits are just ceilings. Lowering them forces more precise extraction and reduces the chance of including irrelevant trailing content.

### 7. Conversation History (5 messages × 200 chars)

**Insufficient for complex trust decisions.**

**Problem**: 200 chars per message truncates the AI's reasoning. Example:
- User: "Can I distribute $5,000 to my daughter for tuition?" (51 chars — OK)
- AI: "Under the HEMS standard in your trust, you can distribute for Health, Education, Maintenance, and Support. Tuition falls under Education. Based on your trust's $50,000 checking account balance and the HEMS standard in Article 4, Section 4.2..." → **truncated at 200 chars**, losing the citation and nuance.
- User: "What about $10,000 for her graduate program?" → The AI can't see its prior HEMS analysis.

**Recommendation**: 8 messages × 300 chars. The cost increase (+175 tokens) is justified by improved multi-turn coherence.

### 8. Response Format Instructions

**Partially redundant and verbose.**

**Redundancy**: The response format block re-instructs "What I'm basing this on / What I don't know / Caveat language" — already defined in `chat_system_core.md` § Response Structure (lines 12-22). These ~200 chars of duplicate instructions appear in every prompt.

**JSON schema verbosity**: The schema includes inline conditional logic (`"type": "create_distribution_preview" if requires_write else null`) which is not valid JSON and adds confusion. The schema could be a compact one-liner.

**Recommendation**: 
- Remove the duplicated response structure instructions (reference the core constitution instead).
- Compact the JSON schema to a single line with field names only.
- For `general_chat`, return plain text (no JSON needed — action_card is always null).
- For streaming mode, the instructions are already compact (~400 chars) — no change needed.

---

## Summary: Token Savings Ranking

| # | Recommendation | Estimated Savings | Priority |
|---|---|---|---|
| 1 | Load actions constitution only for write intents (skip for read-only action intents) | ~2,000 tokens (read-only intents) | 🔴 High |
| 2 | Conditional escalation for `ask_knowledge` (keyword-triggered, not unconditional) | ~735 tokens (most ask_knowledge) | 🔴 High |
| 3 | Compact JSON response format + remove duplicated instructions | ~150 tokens (all non-streaming) | 🟡 Medium |
| 4 | Reduce knowledge context cap to 3000/3500 chars | ~375 tokens (action intents) | 🟡 Medium |
| 5 | Reduce per-topic excerpt limits | ~200–500 tokens (action intents) | 🟡 Medium |
| 6 | Deduplicate trust_type_guidance with knowledge context | ~86 tokens (when overlap occurs) | 🟢 Low |
| 7 | FTS5: reduce snippet limit + strengthen dedup | ~100 tokens (when FTS triggers) | 🟢 Low |
| 8 | Remove legacy chat_system.md load | 0 tokens (memory only) | 🟢 Low |
| 9 | Increase conversation history to 8×300 chars | **+175 tokens** (cost, quality improvement) | 🟢 Low (invest) |

**Total potential savings**: ~3,000–4,000 tokens on action intents, ~900 tokens on `ask_knowledge`, ~0 on `general_chat`.

**After all optimizations**:
- `ask_knowledge`: ~2,985 tokens (from ~3,721)
- `create_distribution`: ~3,400 tokens (from ~6,407)  
- `general_chat`: ~2,750 tokens (unchanged, +175 for better history = ~2,925)

---

*Audit performed on commit at: 2026-08-13*
*Files analyzed: chat_service.py (1,677 lines), 5 prompt files, 49 knowledge files (347KB total)*