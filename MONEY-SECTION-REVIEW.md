# TrustOffice Money Section Review
**Date:** 2026-08-25 · **Scope:** Distributions, Expenses, Compensation, Benevolence, Investments, and the Transaction Ledger — frontend pages, backend routers, DB models.
**Verdict up front:** The five money sections are **silos**. Nothing writes to the transaction ledger automatically; every ledger entry is created manually or via CSV import. There is no reconciliation between sections and the ledger.

---

## Answers to the six questions

| # | Question | Answer |
|---|----------|--------|
| 1 | Does creating a distribution show on the ledger? | **No.** `POST /distributions` inserts only into `db.distribution_records`. Zero references to `db.transactions` in `routers/distributions.py`. |
| 2 | Does creating an expense show on the ledger? | **No.** `POST /expenses` inserts only into `db.expenses`. No transaction write, no entity_id, no linkage field at all. |
| 3 | Appropriate category options across all sections? | **Partially / inconsistent.** Distribution & ledger use different enums; expense categories are effectively **broken** (see below); compensation is free-text. |
| 4 | Do expenses have proper options/categories? | **No — bug.** `ExpensesPage.js:64` reads `data.expense_categories` from `GET /api/categories`, but `routers/categories.py` never returns that key (it returns only purpose_classifications/task_types/minutes_types/entity_types/relationship_types). The dropdown renders **empty**, and the form requires a category (`if (!formData.category)`), so users likely cannot create an expense through the UI. |
| 5 | Can investments upload statements/PDFs? | **Not directly.** Investments are CRUD-only (asset_name, cost_basis, current_value…). The model has a `documents: []` field ("list of vault document IDs") but there is **no endpoint or UI** to attach/upload a statement PDF to an investment. Statement upload only exists via the Vault (`category=bank_statement`). |
| 6 | Can AI pull expenses from uploaded statements? | **No.** `analyze_bank_statement()` (trust_doc_analyzer.py) extracts only **summary fields**: bank_name, last-four, period, beginning/ending balance, total_deposits, total_withdrawals. It does **not** extract line-item transactions and does not create expenses or transactions. Only manual CSV import (`POST /transactions/import`) populates the ledger in bulk. |

---

## Current state by section

### Distributions (`DistributionsPage.js`, 1306 lines; `routers/distributions.py`)
- Full workflow: create → approve → status → attach minutes → send notice. Stored in `db.distribution_records`; category saved as `purpose_classification`.
- Categories come from `/categories` → `purpose_classifications` = `["distribution", "compensation", "expense", "other"]` — these are **generic record-type labels, not distribution purposes** (e.g., no "education", "health", "maintenance"). Misfit for the dropdown labeled "Category".
- Ledger linkage: none on create. The `TransactionCreate` model *does* support `linked_distribution_id`, but nothing ever sets it automatically.

### Expenses (`ExpensesPage.js`, 474 lines; `routers/expenses.py`, 145 lines)
- Simple CRUD: date, amount, payee, category, notes, status (review/approved/rejected/pending). Stored in `db.expenses`.
- **Broken category dropdown** (details above). No subcategories, no tax/deductible flag, no receipt attachment, no recurring flag, no entity/account, no payment method.
- Not connected to ledger, entities, or bank accounts in any way.

### Compensation (`CompensationPage.js`, 913 lines; `routers/compensation.py`)
- Compensation **plans** (structured, with YTD calc) + compensation **payments** (amount, date, `classification_text` free text, trustee_name).
- Payments are free-form — no structured classification matching the ledger's `Compensation` enum, no pay-rate basis (hourly/salary/percentage), no payroll-tax fields.
- No ledger write. `linked_compensation_payment_id` exists on `TransactionCreate` but is never populated.

### Benevolence (`BenevolencePage.js`, 1026 lines; `routers/benevolence.py`)
- Records with purpose/category, attach-minutes, summary, PDF export; separate policy engine. Reasonably mature as a module.
- But disbursements do **not** hit the ledger either (inserts only into `db.benevolence_records`). Note: `GovernanceClassification` has no "Benevolence" option — it would fall under "Other".

### Investments (`InvestmentsPage.js`, `InvestmentsTabbed.js` → PerformanceDashboard; `routers/investments.py`, 110 lines)
- Holdings CRUD + per-type allocation summary + performance dashboard tab. Fields: asset_type (stock/bond/reit/crypto/real_estate/other), custodian, qty/unit, cost_basis, current_value, performance_snapshot.
- **Missing:** statement/PDF upload, document attach endpoints, buy/sell activity feed, income (dividends/interest) capture, valuation history timeline (only one current_value per holding).

### Transaction Ledger (`TransactionLedgerPage.js` + `transaction-ledger/*`; `routers/transactions.py`)
- Solid standalone module: manual entry (`POST /transactions`), CSV import with column mapping (`POST /transactions/import`), bulk classify, delete w/ audit log (`db.transaction_audit_log`), summaries, separation dashboard, LinkMinutesDialog.
- Classification enum: Distribution | Compensation | Inter-Entity Transfer | Operational Expense | Capital Contribution | Tax Payment | Other (+ required note for Other). Directions: inflow/outflow.
- Requires `entity_id` per transaction. This is the *only* place money movement gets recorded unless someone re-enters it manually.

---

## Root cause

`backend/models.py` defines the integration points (`TransactionCreate.linked_distribution_id`, `.linked_compensation_payment_id`, `GovernanceClassification`) but **no router other than `transactions.py` itself (and demo seed data) ever calls `db.transactions.insert_*`**. Verified via grep across all backend routers. The ledger was built as a separate governance feature, never wired into the operational money modules.

## Recommendations (priority order)

1. **Fix the expense-categories bug now**: add `"expense_categories": [...]` to `GET /api/categories` (e.g., Administration, Professional Fees, Accounting/Legal, Insurance, Property, Taxes, Travel, Marketing, Technology, Utilities, Bank Fees, Other). One-line-ish backend fix that unblocks expense creation.
2. **Auto-write transactions** on create/approve:
   - Approved/paid distribution → outflow txn, classification `Distribution`, set `linked_distribution_id`.
   - Compensation payment → outflow txn, `Compensation`, set `linked_compensation_payment_id`.
   - Approved expense → outflow txn, `Operational Expense` (map category→sub-memo); benevolence payout → add a `Benevolence` value to `GovernanceClassification` (or map to Other + memo).
   - Make this idempotent (upsert by linked id) and consider a backfill script for existing records.
3. **Unify category enums**: give distributions real purpose categories (HEMS-style: education, health, maintenance, support, emergency, grant-making), align them with `PurposeClassification`, and stop reusing `purpose_classifications` as the distribution dropdown source.
4. **AI statement line-item extraction**: extend `analyze_bank_statement()` prompt/schema to return individual transactions (date, description, amount, direction), store them as `pending`/unclassified ledger rows (or a review queue) so users confirm before they post. This pairs naturally with the existing bulk-classify UI.
5. **Investment documents**: add `POST /investments/{id}/documents` (reuse Vault upload) + UI button; surface custodian statements per holding.
6. **Structure expenses**: add entity_id/account/payment-method/receipt fields so expenses can become complete ledger rows without re-entry.
7. **Reconciliation view**: per account, compare ledger totals vs extracted statement ending balances (banking.py already stores beginning/ending balances — data is there).

---
*Read-only review; no files modified.*
