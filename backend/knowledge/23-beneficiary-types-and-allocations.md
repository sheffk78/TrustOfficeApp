# Beneficiary Types and Allocation Models

## Overview

TrustOffice supports three beneficiary types — individual, organization, and class — and two allocation modes — percentage and units. This document explains each type, the allocation mechanics, distribution implications, and how to choose the right approach for your trust.

## Beneficiary Types

### Individual Beneficiaries

An individual beneficiary is a named person who receives a direct allocation of trust units or a percentage of the trust's distributable value. This is the most common beneficiary type.

**Examples:** Spouse, child, sibling, friend, named grandchild.

**Key characteristics:**
- The beneficiary is identified by name and contact information
- The allocation is specific and fixed (unless later amended)
- A certificate of trust units can be issued to the beneficiary
- The trustee can send the certificate via email through TrustOffice

**When to use:** When you know exactly who the beneficiary is and want to assign them a specific, identifiable share of the trust.

### Organization Beneficiaries

An organization beneficiary is a legal entity — such as a charity, LLC, corporation, or nonprofit — that holds a direct allocation of trust units. For allocation purposes, organizations are treated identically to individuals: they receive a fixed share, and the total allocation counts toward the 100% cap.

**Examples:** A church, a charitable foundation, a family LLC, a nonprofit organization.

**Key characteristics:**
- The beneficiary is identified by organization name and optionally a contact person
- The allocation is specific and fixed
- A certificate can be issued in the organization's name
- Holder type options include: individual, trust, LLC, corporation, charity/nonprofit, estate, or other entity

**When to use:** When a formal entity (not a natural person) is intended to receive trust distributions.

### Class Beneficiaries

A class beneficiary is a group defined by relationship rather than by naming specific individuals. The class receives a reserved pool of the trust's allocation, and the pool is distributed among confirmed class members according to a distribution convention.

**Examples:** "All children, including after-born," "descendants," "issue," "heirs at law," "blood relatives."

**Key characteristics:**
- The class is defined by a relationship category, not by individual names
- The class receives a percentage allocation (a reserved pool)
- The pool is distributed among confirmed members when members are recorded
- The distribution convention (per capita or per stirpes) determines how the pool divides
- Adding confirmed members reduces the remaining pool proportionally
- Class allocations are separate from individual/organization allocations but contribute to the total 100% cap

**Available class types in TrustOffice:**
- Children (including after-born)
- Descendants
- Issue (lineal descendants)
- Heirs
- Heirs at Law
- Blood Relatives
- Per Stirpes (by branch)
- Per Capita (by head)
- Custom Class

**When to use:** When you want to designate beneficiaries by relationship rather than by name, especially for future or unborn members (e.g., "all children, including those born later").

## Distribution Conventions for Class Beneficiaries

### Per Capita (by head)

Each confirmed class member receives an equal share of the reserved pool. If a class has 4 confirmed members and the pool is 40%, each member receives 10% of the trust.

**Example:** Class of "Children" with 40% pool. Three children confirmed → each receives ~13.33%. A fourth child is born and confirmed → each now receives 10%.

### Per Stirpes (by branch)

Shares are divided by family branch. If a beneficiary in the class is deceased, their share passes to their descendants rather than being redistributed among surviving class members.

**Example:** Class of "Descendants" with 60% pool, per stirpes. Grantor has three children: A, B, C. A is deceased with two children (A1, A2). The pool divides into three branches: A's branch (A1 and A2 split A's third = 10% each), B's branch (B gets 20%), C's branch (C gets 20%).

**When to choose per stirpes:** When you want a deceased beneficiary's share to pass to their descendants rather than be redistributed among surviving members. This is common in multi-generational trusts.

## Allocation Models

### Percentage Mode (Default)

In Percentage mode, you assign beneficiaries a share of the trust as a percentage. TrustOffice calculates the equivalent raw units based on the total authorized units.

- **Example:** 25% of a 100-unit trust = 25 units
- **100% cap:** The combined allocation of all beneficiaries (individuals + organizations + class pools) must not exceed 100%
- **Class allocations are reserved pools:** The percentage assigned to a class is reserved and distributed among confirmed members
- **One percentage point does NOT necessarily equal one unit** — it depends on the total authorized units

**When to use Percentage mode:** When you think in terms of shares ("my spouse gets 50%, my children split 50%"). This is the most intuitive model for most trustees.

### Unit Mode

In Unit mode, you assign beneficiaries a specific number of raw units directly. The percentage is calculated from the total authorized units.

- **Example:** 25 units in a 100-unit trust = 25%
- **Configurable ceiling:** You can set the total authorized units to any number (default: 100)
- **Units are the canonical measure:** Percentage is always derived (units ÷ total authorized × 100)
- **Changing the total authorized units** changes the percentage each beneficiary receives for a fixed unit amount

**When to use Unit mode:** When your trust document specifies allocations in units, or when you need a non-standard total (e.g., 1,000 units for fine-grained allocation among many beneficiaries).

### Relationship Between Units and Percentage

Units and percentages are two views of the same allocation. The canonical value is always raw units. Percentage is derived: (units ÷ total authorized) × 100.

- 50 units in a 100-unit trust = 50%
- 50 units in a 200-unit trust = 25%
- One unit equals one percent ONLY when total authorized units equal 100

Changing the total authorized units changes the percentage each beneficiary receives for a fixed unit amount. This is important when amending a trust or adding new beneficiaries.

## Total Allocation

The combined allocation of all beneficiary types must not exceed 100% (or the total authorized units in Unit mode):

- **Individual allocations** — each person's percentage or units
- **Organization allocations** — each entity's percentage or units
- **Class pool allocations** — each class's reserved percentage

TrustOffice tracks these separately and computes a combined total:
- `certificate_percentage_total` — sum of individual + organization allocations
- `class_beneficiary_percentage_total` — sum of class pool allocations
- `total_allocated_percentage` — combined total of all three types

If the total exceeds 100%, TrustOffice prevents the allocation from being saved. The dashboard and overview tab display the combined allocation summary so you can see at a glance how much of the trust is allocated and how much remains.

## Mixed Allocations

A trust can have a mix of beneficiary types. For example:

- **Spouse: 50%** (individual)
- **Children class: 40%** (class, per capita, reserved pool distributed among confirmed children)
- **Charity: 10%** (organization)

In this example:
- The certificate total (individual + organization) = 60%
- The class total = 40%
- The combined total = 100% — fully allocated

As children are confirmed in the class, the 40% pool is divided among them. The individual and organization allocations are unaffected.

## Choosing a Beneficiary Type

### Individual vs. Organization

The choice between individual and organization is usually clear from the beneficiary's nature:
- A natural person → individual
- A legal entity → organization (charity, LLC, corporation, etc.)

For allocation purposes, both are treated identically — they receive a fixed, direct allocation.

### Individual vs. Class

The choice between naming an individual and designating a class depends on whether you want to identify specific people or define a group by relationship:

- **Name a specific child as an individual** when you want that child to have a fixed, personal allocation that doesn't change when other children are born.
- **Designate "children" as a class** when you want all children — including future-born — to share a pool, with each child's share adjusting as the class grows.

### When to Use a Class

Class beneficiaries are particularly useful when:
- You want to include future or unborn members (e.g., "children, including after-born")
- You want shares to adjust automatically as family circumstances change
- Your trust document defines beneficiaries by relationship rather than by name
- You want per stirpes distribution to handle deceased-beneficiary scenarios automatically

### When NOT to Use a Class

- When the beneficiary is a specific, named person with a fixed share
- When the trust instrument names specific individuals rather than classes
- When you need the allocation to remain constant regardless of family changes

## Trust-Specific vs. General Knowledge

This document explains general beneficiary and allocation concepts. Your specific trust may have different rules:

- **Your trust document controls.** If your trust instrument defines "issue" differently from the general definition above, the trust instrument prevails.
- **Distribution standards (HEMS, discretionary, mandatory) affect how and when distributions are made,** but they do not change how beneficiaries are allocated in TrustOffice.
- **State law may impose additional requirements** on class definitions, per stirpes distribution, or beneficiary rights.
- **Always consult your trust instrument and a qualified attorney** if you are unsure whether a class designation matches your trust document's intent.

## Important Disclaimer

Units and percentages are allocation choices for planning and administration purposes only. They do not constitute legal advice. The allocation model you choose in TrustOffice is a record-keeping tool — it does not override your trust instrument, state law, or the advice of qualified legal counsel.

Consult a trust and estates attorney before making trust distribution decisions, especially when:
- Designating class beneficiaries with after-born members
- Choosing per stirpes vs. per capita distribution
- Amending allocations after initial setup
- Adding or removing beneficiaries from an existing trust