# Trust Amendments and Modifications — Guide for Trustees

This document trains the Trust Assistant on trust amendments, modifications, and beneficiary changes. Use it when a user asks about modifying the trust, changing beneficiaries, beneficiary-to-trustee transitions, or what changes are possible within an irrevocable trust.

## Core Principle

"Irrevocable" does not mean "unchangeable." Most irrevocable trusts include mechanisms for modification. The trust instrument itself is the primary source of authority for what can be changed and how.

## The Amendment Power (Section 38 Pattern)

Most WingPoint trust declarations include an amendment provision (typically Section 38 or equivalent) that serves as the master key for modifications. The standard pattern is:

1. **Unanimous written decision of the Board of Trustees**, recorded in the Trust Minutes
2. **No amendment may alter the fundamental character of the trust** (private, irrevocable, ecclesiastical)
3. **No amendment may deprive a Beneficiary of vested beneficial interests without the written consent of such Beneficiary**

This means: if all trustees agree AND all affected beneficiaries consent, the trust can be modified in most ways — adding beneficiaries, changing distribution standards, modifying spendthrift provisions, updating trustee succession, and more.

### What Amendments Can Typically Do
- Add or remove beneficiaries (with consent of affected beneficiaries)
- Modify distribution standards and procedures
- Update spendthrift provisions with specific exceptions
- Change trustee succession rules
- Add new governance provisions
- Modify beneficiary class definitions
- Update situs or administrative provisions

### What Amendments Typically Cannot Do
- Alter the fundamental private, irrevocable character of the trust
- Deprive a beneficiary of vested interests without their written consent
- Convert the trust into a different type of entity (corporation, partnership, etc.)

## Common Amendment Scenarios

### Scenario: Adding a Non-Lineal Beneficiary

The Protector's power to add beneficiaries is typically limited to lineal descendants. However, the amendment power is broader. To add a non-blood relative (friend, spouse, etc.):

1. **All trustees must unanimously approve** the amendment in writing
2. **All adult beneficiaries must consent** in writing (since their proportional shares will be reduced)
3. **Record the amendment** in the Trust Minutes with the full text of the change
4. **Reissue Certificates of Beneficial Interest** to reflect the new allocation
5. **Store all consent documents** in the Vault

The assistant should:
- Confirm whether the trust has a Protector and whether the Protector's power is limited to lineal descendants
- Explain that the amendment power (Section 38 or equivalent) is the path for non-lineal additions
- Emphasize that unanimous trustee + beneficiary consent is required
- Offer to draft the amendment minutes for review
- Recommend attorney review since this modifies the trust's beneficiary composition

### Scenario: Beneficiary Becoming Trustee (Conflict of Interest Resolution)

When a beneficiary is appointed or succeeds as trustee, they may wish to relinquish their beneficial interest to serve purely in a fiduciary capacity. This avoids the conflict of interest of being both trustee and beneficiary.

The challenge: most trust declarations include a spendthrift clause (Section 32 or equivalent) that prevents beneficiaries from assigning, transferring, or alienating their beneficial interests. This means a simple "I give my units back" won't work without an amendment. The existing withdrawal/relinquishment provision (Section 31 or equivalent) may allow a beneficiary to voluntarily relinquish their interest, but the spendthrift clause still blocks the actual transfer of units.

**Two approaches:**

1. **If the trust declaration already includes a beneficiary-to-trustee transition provision:**
   - The beneficiary delivers a written relinquishment to the Board
   - The Board unanimously approves the redistribution
   - Minutes document the relinquishment and redistribution
   - Certificates of Beneficial Interest are reissued

2. **If the trust declaration does NOT include this provision (most existing trusts):**
   - The trustees must first pass an amendment (Section 38 or equivalent) creating the transition provision
   - The amendment must include an exception to the spendthrift clause for voluntary relinquishment upon becoming trustee
   - The relinquishing beneficiary must sign written consent
   - Then follow the same steps as approach 1

The assistant should:
- Explain the spendthrift clause obstacle
- Recommend an amendment to create a specific exception for beneficiary-to-trustee transitions
- Emphasize the beneficiary's written consent is required (can't be forced)
- Offer to draft both the amendment minutes and the relinquishment language
- Recommend attorney review for the amendment

### Scenario: Moving Assets Between Trusts

A trustee may want to move an asset from one trust to another (e.g., consolidating assets, restructuring). This is typically within the trustee's existing authority:

1. **Check the trust instrument's disposition authority** (Section 35 or equivalent) — most trusts give the Board "full and exclusive authority" to sell, exchange, dispose, or transfer any asset
2. **No beneficiary consent is typically required** for the transfer itself
3. **Record the decision in Minutes** with the rationale
4. **Update Schedule A** in both trusts (remove from source, add to destination)
5. **Store supporting documents** (conveyance, assignment, bill of sale) in the Vault
6. **Consider tax implications** — the transfer may have gift tax or income tax consequences

The assistant should:
- Confirm the trustee has disposition authority under the trust instrument
- Offer to create disposition minutes and update Schedule A
- Recommend CPA review for tax implications of cross-trust transfers
- Recommend attorney review if the transfer is large or unusual

### Scenario: Modifying Distribution Standards

Trustees may want to change how distributions are made (e.g., from HEMS to sole discretion, or vice versa):

1. **Requires unanimous trustee amendment** (Section 38 or equivalent)
2. **Requires beneficiary consent** if the change affects vested interests
3. **Record the full text of the new distribution standard** in the amendment minutes
4. **Update the trust profile** in TrustOffice Settings to reflect the new standard
5. **Recommend attorney review** — distribution standards are core trust provisions

## How to Guide Trustees on Amendments

### Step-by-Step Amendment Process

1. **Identify the need** — what specifically needs to change and why
2. **Check the trust instrument** — what amendment power exists? What are the requirements?
3. **Draft the amendment text** — the specific language being added, modified, or removed
4. **Obtain trustee unanimity** — all trustees must approve in writing
5. **Obtain beneficiary consent** — if the amendment affects vested interests, get written consent from all affected beneficiaries
6. **Record in Trust Minutes** — document the amendment with full text, signatures, and date
7. **Update operational records** — Beneficiaries, Schedule A, Settings, or Certificates as needed
8. **Store in Vault** — upload the executed amendment, consent documents, and any supporting legal advice
9. **Professional review** — recommend attorney review for all amendments, especially those affecting beneficiary rights or distribution standards

### Guardrails for the Assistant

When guiding amendments, the assistant MUST:

1. **Always recommend attorney review** — amendments to irrevocable trusts are significant legal acts
2. **Never characterize an amendment as routine or simple** — even "small" changes can have unintended consequences
3. **Always identify who needs to consent** — trustees, beneficiaries, Protector (if appointed)
4. **Always flag the spendthrift clause** — if the amendment touches beneficiary interests, the spendthrift provision must be addressed
5. **Never draft amendment language that the assistant claims is legally sufficient** — the assistant can suggest language but must defer to an attorney for final wording
6. **Always remind the trustee to preserve the fundamental character of the trust** — amendments cannot convert the trust to a different entity type or remove its irrevocable nature

### Red Flags — When to Strongly Recommend Attorney Review

- Removing a beneficiary without their consent
- Changing the trust's situs or governing law
- Modifying the spendthrift clause (beyond narrow exceptions)
- Changing distribution standards from discretionary to mandatory or vice versa
- Adding beneficiaries who are not lineal descendants
- Any amendment that could affect the trust's tax status
- Any amendment during a beneficiary dispute or threatened litigation
- Any amendment that benefits the trustee personally

## Trust Assistant Capabilities for Amendments

The assistant can:
- **Draft amendment minutes** using `log_minutes` intent with the proposed amendment text
- **Create follow-up tasks** for obtaining beneficiary consent, attorney review, and updating records
- **Update beneficiary records** after an amendment is executed
- **Update Schedule A** if assets are affected
- **Suggest Vault document records** for storing the executed amendment and consent documents

The assistant cannot:
- Determine whether the trust instrument allows a specific amendment (defer to Trust Document Analysis or attorney)
- Certify legal sufficiency of amendment language
- Execute the amendment (trustee must review and approve)
- Determine tax consequences of amendments (defer to CPA)