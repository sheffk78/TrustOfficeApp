# Minutes Types & Templates — Complete Reference

## Overview

TrustOffice supports 43 minutes template types across 9 categories. When a user asks the Trust Assistant to "create minutes," "draft minutes," or "document a meeting," the assistant should identify the appropriate template type and guide the user to it.

## How to Create Minutes in TrustOffice

Users create minutes via **Minutes → Create Minutes** (`/minutes/create`), which shows the template gallery. Each template has a structured form that generates a properly formatted minutes document.

The Trust Assistant can reference specific template types and direct users to the correct one. When a user says "create my initial trust minutes" or "document my first trustee meeting," that maps to the `initial_trustee_meeting` template.

## All 43 Template Types

### First Meeting (1 template)

| Template ID | Name | When to Use |
|---|---|---|
| `initial_trustee_meeting` | Initial Trustee Meeting | **First organizational meeting** — accept trusteeship, open bank accounts, confirm EIN, set fiscal year, adopt governance standards. This is the most common "first minutes" request. Every new trust should have this. |

### Quick Minutes (3 templates)

| Template ID | Name | When to Use |
|---|---|---|
| `annual_review` | Annual Review Meeting | Year-end financial and governance review with comprehensive report |
| `quarterly_review` | Quarterly Review Meeting | Routine quarterly trustee meeting and financial review |
| `general_meeting` | General Meeting | Record a general trustee meeting with multiple resolutions |

### Trustee Changes (5 templates)

| Template ID | Name | When to Use |
|---|---|---|
| `appointment_additional_trustee` | Appoint Additional Trustee | Appoint a new trustee to serve alongside existing trustees |
| `appointment_successor_trustee` | Appoint Successor Trustee | Appoint a replacement trustee due to resignation, death, or removal |
| `trustee_resignation` | Trustee Resignation/Removal | Document a trustee's departure from office |
| `trustee_compensation` | Trustee Compensation | Approve trustee fee arrangements and compensation |
| `successor_trustee_acceptance` | Successor Trustee Acceptance & Qualification | Record a successor trustee's formal acceptance of trusteeship and qualification to serve |

### Property & Assets (8 templates)

| Template ID | Name | When to Use |
|---|---|---|
| `real_estate_purchase` | Real Estate Purchase | Authorize acquisition of real property for the trust |
| `acceptance_of_property` | Accept Property into Trust | Accept additional property into the trust corpus and update Schedule A |
| `disposition_of_asset` | Dispose / Sell Asset | Record the sale, transfer, or removal of an asset from Schedule A |
| `business_interest_acquisition` | Business Interest Acquisition | Authorize purchase of LLC, partnership, or corporate interest |
| `real_estate_lease` | Real Estate Lease | Authorize leasing of trust real property to third parties |
| `bill_of_sale` | Bill of Sale (Vehicle/Equipment) | Generate a bill of sale transferring tangible personal property to the trust |
| `assignment_of_personal_property` | Assignment of Personal Property (Art/Jewelry/Collectibles) | Assign artwork, antiques, jewelry, or collectibles to the trust |
| `general_assignment` | General Assignment (Intangible Assets) | Assign intangible assets (notes, IP, business interests, digital assets) |

### Financial (6 templates)

| Template ID | Name | When to Use |
|---|---|---|
| `bank_account_authorization` | Open Bank Account | Authorize opening a bank or investment account for the trust |
| `investment_policy` | Investment Policy | Adopt, amend, or review the trust's investment policy statement |
| `loan_authorization` | Loan Authorization | Authorize the trust to make or receive a loan |
| `insurance_authorization` | Insurance Authorization | Approve trust insurance policies and coverage |
| `spending_authorization` | Spending Authorization | Document trustee approval of an expenditure that exceeds the spending threshold |
| `reserve_account_resolution` | Reserve Account / Corpus Preservation | Establish or adjust a reserve policy preserving trust corpus against anticipated obligations |

### Distributions (7 templates)

| Template ID | Name | When to Use |
|---|---|---|
| `distribution_to_beneficiaries` | Distribution to Beneficiaries | Document a distribution of trust proceeds to beneficiaries |
| `hems_distribution` | HEMS Distribution | Health, Education, Maintenance, Support distribution with standard compliance |
| `beneficiary_loan` | Loan to Beneficiary | Authorize an intra-family loan to a beneficiary |
| `beneficiary_distribution_notice` | Beneficiary Distribution Notice | Notify a beneficiary of an approved distribution with formal documentation |
| `evaluate_distribution` | Evaluate Distribution Request | Get an AI evaluation of whether a distribution request complies with the trust document and trust law |
| `beneficiary_receipt_release` | Beneficiary Receipt & Release | Record a beneficiary's written acknowledgment of a distribution received |
| `beneficiary_periodic_notice` | Beneficiary Periodic Notice | Send the periodic beneficiary notice your state requires and record it against the compliance deadline |

### Legal & Governance (7 templates)

| Template ID | Name | When to Use |
|---|---|---|
| `trust_amendment` | Trust Amendment | Modify specific provisions of the trust instrument |
| `conflict_of_interest` | Conflict of Interest Disclosure | Document trustee's disclosure and waiver of conflict |
| `emergency_ratification` | Emergency Action Ratification | Ratify trustee actions taken during an emergency |
| `power_of_attorney` | Power of Attorney | Grant limited power of attorney to a trustee or agent |
| `trust_termination` | Trust Termination | Document trust dissolution and final distribution |
| `change_of_situs` | Change Trust Situs | Change the jurisdiction and principal place of administration |
| `trustee_indemnification_release` | Trustee Indemnification & Release | Document the trust's indemnification of a trustee and the scope of any release after a matter closes |

### Admin (5 templates)

| Template ID | Name | When to Use |
|---|---|---|
| `fiscal_year_election` | Fiscal Year Election | Document the trust's fiscal year choice for tax purposes |
| `tax_filing_authorization` | Tax Filing Authorization | Authorize preparation and filing of trust tax returns |
| `designation_of_beneficiaries` | Designate Beneficiaries | Establish or amend beneficiary designations and units of beneficial interest |
| `beneficiary_request_denial` | Beneficiary Request Denial | Document denial of a beneficiary request with proper reasoning |
| `grantor_trust_election` | Grantor Trust / Entity Election | Record the trustees' adoption of a tax-election position for the trust (e.g., check-the-box or an S-corp election for a held entity) |

### Benevolence (1 template)

| Template ID | Name | When to Use |
|---|---|---|
| `benevolence_approval` | Benevolence Assistance | Approve and document a benevolence grant for charitable assistance (requires benevolence_enabled on trust) |

## Mapping User Requests to Template Types

When a user asks the Trust Assistant to create or draft minutes, map their request to the correct template:

| User Says | Template Type |
|---|---|
| "create my initial trust minutes" / "first trustee meeting" / "accept trusteeship" / "initial minutes" | `initial_trustee_meeting` |
| "annual review" / "year-end review" / "annual meeting" | `annual_review` |
| "quarterly review" / "quarterly meeting" | `quarterly_review` |
| "general meeting" / "document a decision" / "record a resolution" | `general_meeting` |
| "appoint a trustee" / "add a co-trustee" | `appointment_additional_trustee` |
| "successor trustee" / "replace a trustee" | `appointment_successor_trustee` |
| "trustee resigning" / "removing a trustee" | `trustee_resignation` |
| "trustee compensation" / "trustee fees" / "pay trustee" | `trustee_compensation` |
| "successor accepts" / "successor qualification" / "accept appointment" | `successor_trustee_acceptance` |
| "buy real estate" / "purchase property" | `real_estate_purchase` |
| "accept property" / "add asset to trust" / "convey property" | `acceptance_of_property` |
| "sell asset" / "dispose of asset" / "remove from schedule A" | `disposition_of_asset` |
| "buy LLC" / "business interest" / "acquire business" | `business_interest_acquisition` |
| "lease property" / "rent out trust property" | `real_estate_lease` |
| "bill of sale" / "transfer vehicle" / "transfer equipment" | `bill_of_sale` |
| "assign artwork" / "assign jewelry" / "assign collectibles" | `assignment_of_personal_property` |
| "assign intangible" / "assign IP" / "assign digital assets" | `general_assignment` |
| "open bank account" / "open investment account" | `bank_account_authorization` |
| "investment policy" / "adopt investment standards" | `investment_policy` |
| "authorize loan" / "trust making a loan" / "trust receiving a loan" | `loan_authorization` |
| "insurance" / "coverage for trust" | `insurance_authorization` |
| "authorize spending" / "approve expenditure" / "large purchase" | `spending_authorization` |
| "reserve account" / "corpus preservation" / "reserve policy" | `reserve_account_resolution` |
| "distribute to beneficiary" / "make a distribution" | `distribution_to_beneficiaries` |
| "HEMS distribution" / "health education maintenance support" | `hems_distribution` |
| "loan to beneficiary" / "intra-family loan" | `beneficiary_loan` |
| "notify beneficiary of distribution" | `beneficiary_distribution_notice` |
| "beneficiary receipt" / "signed receipt" / "release of distribution" | `beneficiary_receipt_release` |
| "periodic beneficiary notice" / "required notice" | `beneficiary_periodic_notice` |
| "evaluate distribution request" / "is this distribution allowed" | `evaluate_distribution` |
| "amend trust" / "modify trust provisions" / "trust amendment" | `trust_amendment` |
| "conflict of interest" / "disclose conflict" | `conflict_of_interest` |
| "ratify emergency action" / "emergency ratification" | `emergency_ratification` |
| "power of attorney" / "grant POA" | `power_of_attorney` |
| "terminate trust" / "dissolve trust" / "close the trust" | `trust_termination` |
| "change jurisdiction" / "change situs" / "move trust to another state" | `change_of_situs` |
| "indemnify trustee" / "trustee release" / "trustee indemnification" | `trustee_indemnification_release` |
| "fiscal year election" / "choose tax year" | `fiscal_year_election` |
| "authorize tax filing" / "authorize tax return" | `tax_filing_authorization` |
| "designate beneficiaries" / "update beneficiary designations" | `designation_of_beneficiaries` |
| "deny beneficiary request" / "reject beneficiary request" | `beneficiary_request_denial` |
| "grantor trust election" / "check the box" / "entity election" | `grantor_trust_election` |
| "benevolence grant" / "charitable assistance" | `benevolence_approval` |

## Trust Data Available in Context

The Trust Assistant receives the following trust data in its system prompt under `## Current Trust Context`:

- **Trust name** — the trust's legal name
- **Type** — trust type (e.g., revocable, irrevocable)
- **Jurisdiction** — governing state/legal jurisdiction
- **State** — state code
- **Establishment Date** — the trust's start_date / formation date (from trust settings)
- **Beneficiary Standard** — distribution standard (HEMS, discretionary, etc.)
- **Trustees** — comma-separated list of trustee names
- **Defensibility Score** — current health score

**Never ask the user for information that's already in the trust context.** If the user asks to create initial minutes and the establishment date is in the context, reference it directly. If it shows "Not specified," then ask the user to set it in Settings.

## Creating Minutes — Assistant Behavior

When a user asks to create or draft minutes:

1. **Identify the template type** from the mapping table above.
2. **Check the trust context** for any information the template needs (establishment date, trustees, jurisdiction, etc.). If the data is present, mention it so the user knows they don't need to re-enter it.
3. **Direct the user to the correct creation page**: `/minutes/create?type={template_id}` — this opens the specific template form pre-selected.
4. **For initial trustee meetings specifically**: This is the most common first request. Direct to `/minutes/create?type=initial_trustee_meeting&from=onboarding`. Mention that the trust's establishment date, jurisdiction, and trustee names are already in the system and will be pre-filled.
5. **Do not attempt to generate minutes text yourself.** The template forms handle document generation. The assistant's role is to identify the right template and guide the user there.