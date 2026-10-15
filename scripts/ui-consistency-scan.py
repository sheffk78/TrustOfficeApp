#!/usr/bin/env python3
"""
UI Consistency Ratchet Gate — TrustOffice
Scans frontend/src/pages for violations of frontend/UI-STANDARD.md and fails
( exit 1 ) when a file gains violations vs scripts/ui-consistency-baseline.json.

Usage:
  python3 scripts/ui-consistency-scan.py            # ratchet check (exit 1 on regression)
  python3 scripts/ui-consistency-scan.py --update   # accept new counts -> update baseline
  python3 scripts/ui-consistency-scan.py --report   # print full per-file table

Rules encoded (see UI-STANDARD.md):
  R1 header      page must carry .page-title + .page-container (auth/onboarding/404 exempt)
  R2 radius      rounded-lg|xl|2xl|md anywhere in pages (hard); rounded-full allowed
                 only on avatars/spinner/badge lines
  R3 palette     text|bg|border-{gray,slate,zinc,neutral,stone}-{n} and pastels
  R4 raw buttons <button> not styled as a card (card-selectors exempt)
  R5 tabs        TabsTrigger classNames deviating from 'flex items-center gap-2'
  R6 badges      window.confirm instead of AlertDialog
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "frontend" / "src" / "pages"
BASELINE = ROOT / "scripts" / "ui-consistency-baseline.json"

# Files exempt from R1 (header rule) — intentional layouts per UI-STANDARD.md
R1_EXEMPT = {
    "LoginPage.js", "SignUpPage.js", "ForgotPasswordPage.js", "ResetPasswordPage.js", "AcceptInvitePage.js", "AuthCallback.js",
    "PostCheckoutPage.js", "NotFoundPage.js", "OnboardingPage.js",
    "ExternalRedirect.js", "WingPointRedirect.js", "WingPointWelcomePage.js",
    "ConnectWingPoint.js", "trustProtectorPowers.js",
    "SuccessorAccessPage.js",  # public token-gated route — centered layout intentional (Wave 4 audit F14)
    "TrustAccessPanel.js",     # Wave 5: 12-line superseded stub, zero imports anywhere — unreachable
    # (TrustAccessPage.js REMOVED from exemption in Wave 5 — logged-in shell route, migrated to PageHeader)
    "PricingPage.js",          # Wave 7: public marketing page — full-bleed layout, own navy nav + hero (no in-app shell)
    "AffiliatePage.js",        # Wave 7: public marketing page — full-bleed dark hero, external-partner funnel
    "ContactPage.js",          # Wave 7: public contact page — centered card layout, unrouted from App.js (marketing-site embed)
}

RE_PAGE_TITLE = re.compile(r'\bpage-title\b')
RE_CONTAINER = re.compile(r'\bpage-container\b')
# Pages whose shell (page-container) is supplied by a parent wrapper file — page renders
# only inside that wrapper, so container presence is checked through the chain.
WRAPPER_SUPPLIES = {
    "PrintableBinderPage.js": ("DocumentsTabbed.js",),
    "VaultPage.js": ("DocumentsTabbed.js",),
    "GovernancePage.js": ("HealthComplianceTabbed.js",),
    "RiskDashboardPage.js": ("HealthComplianceTabbed.js",),
    "StateCompliancePage.js": ("HealthComplianceTabbed.js",),
}
RE_RADIUS_HARD = re.compile(r'\brounded-(?:lg|xl|2xl|md)\b')
RE_ROUNDED_FULL = re.compile(r'\brounded-full\b')
RE_FULL_ALLOWED = re.compile(r'animate-spin|avatar|Avatar|badge|Badge|spinner|Spinner|uppercase tracking-wider|w-\d+\s+h-\d+[^\n]*rounded-full(?=.*flex-shrink|.*mx-auto|.*items-center)')  # heuristic per-line (icon medallions count as badge/Avatar class)
RE_PALETTE = re.compile(r'\b(?:text|bg|border)-(?:gray|slate|zinc|neutral|stone)-\d{2,3}\b|\b(?:bg|text)-(?:blue|purple|pink|cyan|indigo|violet)-\d{2,3}\b')
RE_RAW_BTN = re.compile(r'<button\b')
RE_TABS = re.compile(r'TabsTrigger[^>]*className="([^"]*)"')
WIN_CONFIRM = re.compile(r'(?://[^\n]*window\.confirm|<!--[^>]*window\.confirm[^>]*-->|\{/\*[^*]*\*/\s*\n?\s*\{*[^}]*window\.confirm)')

def scan_file(path: Path):
    t = path.read_text(errors="replace")
    # Resolve PageHeader usage: pages wired to the shared component carry the
    # header classes inside PageHeader.js, not the page file itself.
    uses_pageheader = bool(re.search(r"\bfrom\s+'@/components/PageHeader'", t))
    if uses_pageheader:
        header_ref = t + "\n" + (ROOT / "frontend" / "src" / "components" / "PageHeader.js").read_text(errors="replace")
    else:
        header_ref = t
    v = {"R1_header": 0, "R2_radius_hard": 0, "R2_radius_full": 0, "R3_palette": 0, "R4_raw_btn": 0, "R5_tabs": 0, "R6_confirm": 0}
    if path.name not in R1_EXEMPT and path.parent == PAGES:  # subdir Tab fragments render inside a routed page's shell
        container_files = [t]
        for wrapper in WRAPPER_SUPPLIES.get(path.name, ()):
            wp = PAGES / wrapper
            if wp.exists():
                container_files.append(wp.read_text(errors="replace"))
        has_header = bool(RE_PAGE_TITLE.search(header_ref)) and any(RE_CONTAINER.search(f) for f in container_files)
        if not has_header:
            v["R1_header"] = 1
    v["R2_radius_hard"] = len(RE_RADIUS_HARD.findall(t))
    for line in t.splitlines():
        if RE_ROUNDED_FULL.search(line) and not RE_FULL_ALLOWED.search(line):
            v["R2_radius_full"] += 1
    v["R3_palette"] = len(RE_PALETTE.findall(t))
    # raw buttons: exclude those whose className suggests a selectable card
    card_btn = 0
    for m in re.finditer(r'<button\b([^>]*)>', t):
        attrs = m.group(1)
        cm = re.search(r'className="([^"]*)"', attrs)
        if cm and re.search(r'card-trust|\bcard\b', cm.group(1)):
            card_btn += 1
    v["R4_raw_btn"] = len(RE_RAW_BTN.findall(t)) - card_btn
    for cm in RE_TABS.finditer(t):
        cls = cm.group(1).strip()
        if cls not in ("flex items-center gap-2",):
            v["R5_tabs"] += 1
    v["R6_confirm"] = len(WIN_CONFIRM.findall(t))
    return v

def main():
    update = "--update" in sys.argv
    report = "--report" in sys.argv
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    current, regressions, improvements = {}, [], []
    _page_files = list(PAGES.glob("*.js"))
    for _sub in PAGES.iterdir():
        if _sub.is_dir():
            if _sub.name in ("structures", "beneficiaries", "governance"):
                _page_files += [f for f in _sub.glob("*.js") if f.name.endswith(("Tab.js", "Tabbed.js", "Page.js"))]
                _page_files += [f for f in _sub.glob("*.jsx") if f.name.endswith(("Tab.jsx", "Page.jsx"))]
    for f in sorted(set(_page_files)):
        if f.name.endswith(".test.js"):
            continue
        v = scan_file(f)
        counts = {k: n for k, n in v.items() if n}
        current[f.name] = counts
        old = baseline.get(f.name, {})
        for k, n in counts.items():
            if n > old.get(k, 0):
                regressions.append(f"  + {f.name}: {k} {old.get(k,0)} -> {n}")
            elif n < old.get(k, 0):
                improvements.append(f"  - {f.name}: {k} {old.get(k,0)} -> {n}")
        for k, n in old.items():
            if k not in counts:
                improvements.append(f"  - {f.name}: {k} {n} -> 0")

    if report or not (update or regressions is not None):
        print(f"{'PAGE':36s} " + " ".join(f"{k.split('_',1)[0][:7]:>7s}" for k in ["R1_header","R2_radius_hard","R2_radius_full","R3_palette","R4_raw_btn","R5_tabs","R6_confirm"]))
        tot = {k: 0 for k in current[next(iter(current))]} if current else {}
        for name, counts in current.items():
            tot_line = ""
            for k in ["R1_header","R2_radius_hard","R2_radius_full","R3_palette","R4_raw_btn","R5_tabs","R6_confirm"]:
                n = counts.get(k, 0); tot[k] = tot.get(k, 0) + n
                tot_line += f"{n:>8d}"
            print(f"{name:36s} {tot_line}")
        print("TOTALS:", json.dumps(tot))

    if update:
        BASELINE.write_text(json.dumps(current, indent=1, sort_keys=True))
        print(f"\nBaseline updated: {BASELINE} ({sum(len(v) for v in current.values())} violation clusters)")
        return 0
    print("\nIMPROVEMENTS:\n" + ("\n".join(improvements) if improvements else "  (none)"))
    if regressions:
        print("\nREGRESSIONS — fix or run with --update to accept:\n" + "\n".join(regressions))
        return 1
    print("\nRATCHET OK — no regressions vs baseline.")
    return 0

if __name__ == "__main__":
    sys.exit(main())