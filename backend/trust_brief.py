"""Trust Brief — per-trust always-injected context block.

Council-approved architecture (2026-09-14, 3/3 Go): two-layer context for the
Trust Assistant.

  Layer 1 (this module): the "Trust Brief" — one compact structured block per
  trust, ALWAYS injected into the system prompt. Tiered token cap; flat cost
  regardless of account size.

  Layer 2 (see chat_service retrieval): on-demand per-turn retrieval blocks
  (minutes search, vault doc detail). Detail enters context only for the turn
  that needs it.

Budget policy (tiered cap, per council refinement — a flat cap sheds too
aggressively on complex trusts):
  - CORE zone (~1.5k tokens target, NEVER shed): trust identity, distribution
    standard with exact language + article reference, trustee powers with
    article refs, beneficiary roster, class beneficiaries, deadlines
    (governance + tax), health score, money/structure summary lines.
    If core overflows, shed INSIDE core in this precedence:
    beneficiary roster truncation (marked) → summary lines. Distribution
    standard and identity are never dropped — a Brief without the exact
    distribution language is worse than no Brief.
  - OVERFLOW zone (~1k tokens): vault doc one-liners, latest minutes recap,
    entity one-liners. Sheds in council order: vault doc lines → minutes
    recap → entity lines.

Token estimation: chars/4 heuristic (documented; conservative for prose,
slightly generous for symbols — acceptable for a budget gate).

Staleness: v1 rebuilds the Brief from freshly-queried context on every full
request (staleness impossible by construction — assembly is pure string
building over data fetched in the same request). The stored copy
(db.trust_briefs) is for observability + the future fast path, where
`needs_rebuild()` (source_versions vs built_at) gates a synchronous rebuild.
Fast path ships OFF; enable after prod verification.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------- budgets ---

CHARS_PER_TOKEN = 4

CORE_BUDGET_TOKENS = 1500
OVERFLOW_BUDGET_TOKENS = 1000

MAX_TRUSTEE_POWERS = 8          # top-level powers rendered in core
MAX_BENEFICIARIES_FULL = 25     # roster beyond this truncates (marked)
MAX_VAULT_DOC_LINES = 50        # hard ceiling on doc one-liners
MAX_MINUTES_RECAP = 5
MAX_ENTITY_LINES = 15
MAX_DEADLINES = 8


def estimate_tokens(text: str) -> int:
    """~4 chars/token heuristic. Good enough for a budget gate."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def _clean(value: Any) -> str:
    """Coerce to a single-line display string. Neutralizes markdown heading
    markers so member content can never inject fake prompt sections."""
    if value is None:
        return ""
    s = str(value).replace("\n", " ").replace("\r", " ").strip()
    s = re.sub(r"#{1,6}\s+", "", s)  # strip heading markers (incl. flattened "\n## X" → "X")
    return " ".join(s.split())


# -------------------------------------------------------------- rendering ---

def _fmt_money(amount: Any) -> str:
    try:
        return f"${float(amount or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _render_distribution_standard(td: dict) -> list[str]:
    """The single most important section. Exact language + article ref —
    NEVER dropped. Returns list of lines."""
    lines = []
    std = td.get("distribution_standard", "")
    if std:
        lines.append(f"Distribution standard (exact language): {std}")
    std_type = td.get("distribution_standard_type", "")
    if std_type:
        lines.append(f"Distribution standard type: {std_type}")
    article = td.get("distribution_article", "")
    if article:
        lines.append(f"Article reference: {article}")
    rules = td.get("distribution_rules")
    if isinstance(rules, dict):
        compact = ", ".join(f"{k}={v}" for k, v in sorted(rules.items()) if v not in (None, "", []))
        if compact:
            lines.append(f"Distribution rules: {compact}")
    return lines


def _render_powers(td: dict) -> list[str]:
    powers = td.get("trustee_powers", []) or []
    lines = []
    for p in powers[:MAX_TRUSTEE_POWERS]:
        if isinstance(p, dict):
            power = _clean(p.get("power", ""))
            article = _clean(p.get("article", "") or p.get("article_reference", ""))
            if power:
                lines.append(f"- {power}" + (f" ({article})" if article else ""))
    detail = td.get("trustee_powers_detail")
    if isinstance(detail, dict) and detail.get("summary"):
        lines.append(f"Powers detail: {detail['summary']}")
    return lines


def _render_identity(trust: dict, td: dict) -> list[str]:
    lines = [
        f"Trust: {trust.get('name', 'Unknown')}",
        f"Type: {trust.get('type', 'Not specified')}",
        f"Jurisdiction: {trust.get('jurisdiction') or trust.get('state_code') or 'Not specified'}",
    ]
    if trust.get("start_date"):
        lines.append(f"Established: {trust['start_date']}")
    if trust.get("beneficiary_standard"):
        lines.append(f"Beneficiary standard: {trust['beneficiary_standard']}")
    trustees = trust.get("trustees", "")
    if trustees:
        lines.append(f"Trustees: {trustees}")
    if td.get("grantor"):
        lines.append(f"Grantor: {td['grantor']}")
    return lines


def _render_beneficiaries(beneficiaries: list, class_bens: list) -> tuple[list[str], bool]:
    """Returns (lines, truncated). Truncation is always marked inline."""
    lines = []
    truncated = False
    if beneficiaries:
        shown = beneficiaries[:MAX_BENEFICIARIES_FULL]
        for b in shown:
            name = _clean(b.get("name", "Unknown"))
            units = b.get("units")
            lines.append(f"- {name}" + (f" ({units} units)" if units else ""))
        if len(beneficiaries) > MAX_BENEFICIARIES_FULL:
            truncated = True
            lines.append(
                f"- …and {len(beneficiaries) - MAX_BENEFICIARIES_FULL} more "
                "(full roster via records; ask for specifics)"
            )
    if class_bens:
        for cb in class_bens[:10]:
            label = cb.get("label") or cb.get("class_type", "")
            pct = cb.get("percentage", "")
            lines.append(f"- Class: {label}" + (f" ({pct}%)" if pct not in ("", None, 0) else ""))
    if not lines:
        lines = ["None recorded"]
    return lines, truncated


def _render_deadlines(upcoming: list, tax: list) -> list[str]:
    lines = []
    for d in upcoming[:MAX_DEADLINES]:
        due = (d.get("due_date") or "")[:10]
        desc = _clean(d.get("description") or d.get("type") or "Task")
        pri = d.get("priority", "")
        lines.append(f"- {desc} — due {due}" + (f" [{pri}]" if pri and pri != "normal" else ""))
    for t in (tax or [])[:MAX_DEADLINES]:
        lines.append(f"- {t.get('filing', 'Tax filing')} — due {(t.get('due_date') or '')[:10]}")
    if not lines:
        lines = ["None in the next 14 days"]
    return lines


def _render_summaries(money: dict, structure: dict, health: dict) -> list[str]:
    lines = [
        f"Defensibility Score: {health.get('total', 0)}/{health.get('max_score', 100)}"
        f" ({health.get('color', 'red')})",
        (
            f"Money: {money.get('distributions_total', 0)} distributions total"
            f" ({_fmt_money(money.get('distributions_ytd_amount', 0))} YTD),"
            f" {money.get('compensation_active_plans', 0)} compensation plans,"
            f" {money.get('investments_count', 0)} investments"
            f" ({_fmt_money(money.get('investments_total_value', 0))})"
        ),
        (
            f"Structure: {structure.get('entity_count', 0)} entities,"
            f" {structure.get('beneficiary_count', 0)} beneficiaries,"
            f" {structure.get('schedule_a_asset_count', 0)} Schedule A assets"
            f" ({_fmt_money(structure.get('schedule_a_total_value', 0))})"
        ),
    ]
    return lines


def _render_pending(pending: list) -> list[str]:
    lines = []
    for p in (pending or [])[:8]:
        if p.get("type") == "pending_distribution":
            lines.append(f"- Pending distribution: {p.get('summary', '')}")
        elif p.get("type") == "overdue_task":
            lines.append(f"- OVERDUE: {p.get('summary', '')} (was due {(p.get('due_date') or '')[:10]})")
    return lines


def _render_vault_lines(vault_docs: list) -> list[str]:
    """One line per vault doc: title — category, date, description gist."""
    lines = []
    for d in (vault_docs or [])[:MAX_VAULT_DOC_LINES]:
        title = _clean(d.get("title") or d.get("file_name") or "Untitled")
        cat = _clean(d.get("category_label") or d.get("category") or "")
        date = (d.get("date") or "")[:10]
        desc = _clean(d.get("description") or "")
        if len(desc) > 80:
            desc = desc[:77] + "…"
        bits = [b for b in (cat, date) if b]
        lines.append(f"- {title}" + (f" ({', '.join(bits)})" if bits else "") + (f" — {desc}" if desc else ""))
    return lines


def _render_minutes_recap(recent_activity: list) -> list[str]:
    """Latest minutes meetings from recent activity labels."""
    lines = []
    for item in (recent_activity or []):
        if item.get("type") == "minutes":
            lines.append(f"- {item.get('label', 'Minutes recorded')} ({item.get('date', '')})")
        if len(lines) >= MAX_MINUTES_RECAP:
            break
    return lines


def _render_entities(entities: list) -> list[str]:
    lines = []
    for e in (entities or [])[:MAX_ENTITY_LINES]:
        etype = e.get("entity_type", "entity")
        name = e.get("name") or e.get("legal_name") or "Unnamed"
        lines.append(f"- {name} ({etype})")
    return lines


# ------------------------------------------------------------ core builder ---

def build_trust_brief(ctx: dict) -> dict:
    """Render the Trust Brief from a trust context dict (same shape that
    chat_service.build_trust_context returns).

    Returns dict:
      text            — the rendered Brief (inject into system prompt)
      stats           — {core_tokens, overflow_tokens, total_tokens,
                         shed_sections: [...], roster_truncated: bool,
                         sections_rendered: [...]}
    """
    trust = ctx.get("trust", {}) or {}
    td = ctx.get("trust_document", {}) or {}
    health = ctx.get("health_score", {}) or {}
    money = ctx.get("money_summary", {}) or {}
    structure = ctx.get("structure_summary", {}) or {}

    # ---- CORE zone (never sheds whole sections; sheds inside by precedence)
    core_parts: list[tuple[str, list[str], int]] = []  # (title, lines, priority)

    identity = _render_identity(trust, td)
    dist = _render_distribution_standard(td)
    powers = _render_powers(td)
    if identity or dist or powers:
        core_parts.append(("Trust & Instrument", identity + dist + powers, 0))

    bens = _render_beneficiaries(ctx.get("beneficiaries", []) or [],
                                 ctx.get("class_beneficiaries", []) or [])
    roster_truncated = bens[1]
    core_parts.append(("Beneficiaries", bens[0], 1))

    deadlines = _render_deadlines(ctx.get("upcoming_deadlines", []) or [],
                                   ctx.get("tax_deadlines", []) or [])
    core_parts.append(("Upcoming Deadlines", deadlines, 2))

    pending = _render_pending(ctx.get("pending_items", []) or [])
    if pending:
        core_parts.append(("Pending / Overdue", pending, 3))

    summaries = _render_summaries(money, structure, health)
    core_parts.append(("Snapshots", summaries, 4))

    # Core overflow policy: shed lowest priority (highest number) first,
    # inside sections the roster truncation already handled. Summaries and
    # deadlines stay; if still over, drop Pending, then Snapshots.
    def _core_tokens(parts) -> int:
        return estimate_tokens("\n".join(f"## {t}\n" + "\n".join(l) for t, l, _ in parts))

    shed_sections: list[str] = []
    while _core_tokens(core_parts) > CORE_BUDGET_TOKENS and len(core_parts) > 2:
        victim = max(core_parts, key=lambda p: p[2])
        core_parts.remove(victim)
        shed_sections.append(victim[0])

    # ---- OVERFLOW zone
    # Council drop-order (hy3 refinement): when space is tight, shed VAULT doc
    # lines first → then entity lines → minutes recap is the last to go
    # (recent governance activity is the highest-value overflow content).
    # Keep-priority below is the inverse of drop-order.
    vault_lines = _render_vault_lines(ctx.get("vault_documents", []) or [])
    minutes_lines = _render_minutes_recap(ctx.get("recent_activity", []) or [])
    entity_lines = _render_entities(ctx.get("entities", []) or [])

    overflow_groups: list[tuple[str, list[str], int]] = []
    if minutes_lines:
        overflow_groups.append(("Recent Minutes", minutes_lines, 0))
    if entity_lines:
        overflow_groups.append(("Entities (Structures)", entity_lines, 1))
    if vault_lines:
        overflow_groups.append(("Vault Documents", vault_lines, 2))

    kept_overflow: list[tuple[str, list[str], int]] = []
    overflow_shed: list[str] = []
    for gi, group in enumerate(overflow_groups):  # keep-priority order
        candidate = kept_overflow + [group]
        used = estimate_tokens("\n".join(f"## {t}\n" + "\n".join(l) for t, l, _ in candidate))
        if used <= OVERFLOW_BUDGET_TOKENS:
            kept_overflow = candidate
        else:
            # The vault doc list (last, largest group) gets partial-fill:
            # keep as many lines as the remaining budget allows.
            if gi == len(overflow_groups) - 1:
                fit = []
                for line in group[1]:
                    trial = kept_overflow + [(group[0], fit + [line], 0)]
                    if estimate_tokens("\n".join(f"## {t}\n" + "\n".join(l) for t, l, _ in trial)) > OVERFLOW_BUDGET_TOKENS:
                        break
                    fit.append(line)
                if fit:
                    kept_overflow.append((group[0], fit, 0))
                    if len(fit) < len(group[1]):
                        overflow_shed.append(
                            f"{group[0]} (kept {len(fit)}/{len(group[1])} lines)"
                        )
                    continue
            overflow_shed.append(group[0])

    # ---- render
    core_text = "\n\n".join(f"## {t}\n" + "\n".join(l) for t, l, _ in core_parts)
    overflow_text = "\n\n".join(f"## {t}\n" + "\n".join(l) for t, l, _ in kept_overflow)

    header = "# TRUST BRIEF (always-current summary of this trust)\nUse this as the baseline. For detail beyond it, say what you'd need rather than guessing."
    text = header + "\n\n" + core_text
    if overflow_text:
        text += "\n\n" + overflow_text

    core_tokens = _core_tokens(core_parts)
    overflow_tokens = estimate_tokens(overflow_text)

    stats = {
        "core_tokens": core_tokens,
        "overflow_tokens": overflow_tokens,
        "total_tokens": core_tokens + overflow_tokens,
        "budget_tokens": CORE_BUDGET_TOKENS + OVERFLOW_BUDGET_TOKENS,
        "shed_sections": shed_sections + overflow_shed,
        "roster_truncated": roster_truncated,
        "vault_docs_in_brief": sum(len(l) for t, l, _ in kept_overflow if t == "Vault Documents"),
        "sections_rendered": [t for t, _, _ in core_parts] + [t for t, _, _ in kept_overflow],
    }
    return {"text": text, "stats": stats}


# ---------------------------------------------------------------- staleness ---

def compute_source_versions(updates: dict[str, Any]) -> dict[str, str]:
    """Normalize a {collection: max_updated_at} map into a comparable
    source_versions dict (ISO strings)."""
    return {k: str(v or "") for k, v in updates.items() if v}


def needs_rebuild(
    built_at: Optional[str],
    source_versions: dict[str, str],
    stored_versions: dict[str, str],
) -> bool:
    """Lazy staleness check (O(collections), no trigger graph).

    True when: no stored Brief, OR any collection's current max updated_at is
    newer than the version recorded when the Brief was built. ISO-string
    comparison is safe: Mongo stores UTC ISO strings that sort correctly.
    """
    if not built_at or not stored_versions:
        return True
    for coll, current in source_versions.items():
        recorded = stored_versions.get(coll, "")
        if current and current > recorded:
            return True
    return False


def brief_updated_at_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "estimate_tokens",
    "build_trust_brief",
    "compute_source_versions",
    "needs_rebuild",
    "brief_updated_at_now",
    "CORE_BUDGET_TOKENS",
    "OVERFLOW_BUDGET_TOKENS",
]