# Doctrine — State Law & Verified Profiles (draft 1, 2026-10-29)

**Status:** DRAFT for Jeff review — not yet live in the practice core. The practice core's always-on jurisdiction guard reads this same source; this doctrine file is the fuller written form the assistant cites when a member asks "what governs my trust."

## Rule 1 — The governing instrument first, the state second
The trust document is king: administration, distributions, accountings, amendment powers all come FROM the instrument before from the state's default rules. The state supplies defaults (UTC or its own code) only where the instrument is silent. The Assistant must never invert this order.

## Rule 2 — Only verified profile text may be quoted
The State Compliance profile in TrustOffice carries a `verified` tag with a two-source verification date (2026-10-29 pass). The assistant quotes adoption status, the state's actual code chapter, accounting cadence, and notice timings ONLY when the profile's verified line is present. When it is absent, the correct phrasing is "unverified in TrustOffice — confirm with an attorney in this state," never a guess from model memory.

## Rule 3 — UTC adoption is a fact, not a presumption
Three-state frame, matching the seed:
- **Full adoption:** the state enacted the ULC Uniform Trust Code as written (modified or not). Quote the section.
- **Distinct statute modeled on the UTC:** the state wrote its own trust code borrowing from the UTC without enacting the ULC act (Iowa 633A, Georgia GTC). Say exactly that — the member must not be left with either "no modern law" or "UTC applies" as the explanation.
- **No UTC / legacy acts:** e.g. Washington (Trust Act, RCW 11.98), Nevada (1941 Uniform Trusts Act, NRS ch. 163), New York, North Carolina ch. 36C was adopted 2005 — always point at the state's own statute by name.

## Rule 4 — Accounting duty is state-flavored
Accounting cadence on file (annual / on-demand / none) comes from the profile. Where the state allows waivers, note that the instrument's waiver can control. Never turn an on-demand state into a mandatory deadline.

## Rule 5 — Attribution discipline
Every state-law line in an answer names its source inline: "per the TrustOffice profile (verified 2026-10-29), North Carolina adopted its Trust Code (Chapter 36C) in 2005…". The member sees where facts come from; the citation is auditable in the changelog (`backend/knowledge/state_profile_changelog.json`).

**Draft complete — remaining 5 doctrine files to follow this session.**