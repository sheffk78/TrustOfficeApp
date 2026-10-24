"""Extract the Trustee-101 course PDFs into clean knowledge-base markdown.

WHY (2026-10-23, P2a): the Trustee-101 course went through 6 legal review
rounds. Its 7 lesson PDFs are member-facing product content that the Trust
Assistant should be able to retrieve and cite, but they were never in the
knowledge base, so the assistant could not ground answers in them.

HARD BOUNDARY: NO new legal text. Every character of doctrine in the output
comes verbatim from the PDF. The extractor only removes the PDF furniture
(running headers, page numbers, the marketing banner) and converts the
layout into markdown. It never paraphrases, summarizes, or adds.

STRUCTURE: pypdf's text visitor reports the font size of every text run, so
headings are detected by TYPE SIZE rather than by guessing from capital
letters. That is what keeps "H - Health" a heading and "[Your Name], Trustee"
a body line. Heading levels:

    H1 (largest)  -> the lesson/section title  -> "## "
    H2             -> sub-sections                -> "### "
    body           -> paragraphs / list items

SPLIT RULE: a PDF whose body exceeds ~6,000 chars is split into SEPARATE KB
articles, each titled so it makes sense standalone. Within an article, "## "
headings mark the PDF's own sections so the FTS index can retrieve a section
rather than the head of a file.

PROVENANCE: every article carries a "from Trustee 101" tag plus the source
PDF name and its SHA-256, so any line can be traced back to the reviewed
source.
"""
import hashlib
import re
import sys
from typing import Optional

import pypdf

SRC_DIR = sys.argv[1] if len(sys.argv) > 1 else (
    "/Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/"
    "TrustOffice-Website/frontend/public/pdfs"
)
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else (
    "/Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/"
    "TrustOfficeApp/backend/knowledge"
)

# (pdf stem, output base name, article title)
PDFS = [
    ("minute-templates-l3", "26-trustee-101-minute-templates",
     "Trustee 101 - Minute Templates (Lesson 3)"),
    ("hems-decision-framework", "27-trustee-101-hems-decision-framework",
     "Trustee 101 - HEMS Decision Framework (Lesson 4)"),
    ("separation-checklist", "28-trustee-101-separation-checklist",
     "Trustee 101 - The Commingling Trap: Separation Checklist (Lesson 5)"),
    ("trust-tax-calendar-l6", "29-trustee-101-trust-tax-calendar",
     "Trustee 101 - Trust Tax Calendar (Lesson 6)"),
    ("investment-policy-statement-template-l7", "30-trustee-101-investment-policy-statement",
     "Trustee 101 - Prudent Investor Rule & Investment Policy Statement (Lesson 7)"),
    ("beneficiary-communication-templates-l8", "31-trustee-101-beneficiary-communication-templates",
     "Trustee 101 - Beneficiary Communication Templates (Lesson 8)"),
    ("family-governance-framework-l9", "32-trustee-101-family-governance-framework",
     "Trustee 101 - Family Governance Framework (Lesson 9)"),
]

SPLIT_THRESHOLD = 6000

# --- PDF furniture (boilerplate that is not doctrine) ------------------------ #

_DISCLAIMER_LONG = re.compile(
    r"This content is provided for educational purposes only and does not constitute "
    r"legal advice\. Always consult a qualified attorney for your specific situation\."
)
_DISCLAIMER_MIN = re.compile(
    r"Educational purposes only\. Not legal advice\. Consult a qualified attorney "
    r"for your specific situation\."
)
_DISCLAIMER_TAX = re.compile(
    r"Educational resource only\. Tax deadlines vary by trust, state, fiscal year, and IRS "
    r"guidance\. Confirm with a qualified CPA or tax attorney\."
)
_EDU_NOT_LEGAL = re.compile(
    r"^TrustOffice Trustee 101 . Educational template, not legal or investment advice\.$"
)
_PAGE_MARK = re.compile(r"^(trustoffice\.app\s+)?Page\s+\d+\s*(of|/)?\s*\d*$")
_BRAND_ONLY = re.compile(r"^TrustOffice\s*.\s*trustoffice\.app$")
_RUNNING_LESSON = re.compile(r"^Trustee 101\s*[-—]\s*Lesson \d+.*$")
_RUNNING_CAL = re.compile(r"^TrustOffice\s+Trust\s+\w+(?:\s+\w+)*\s+.\s+Lesson\s+\d+$")
_AI_BANNER = re.compile(
    r"^The\s+AI\s+Minutes\s+Builder\s+turns\s+three\s+bullet\s+points\s+into\s+a\s+formal\s+"
    r"WHEREAS/RESOLVED\s+resolution\s+in\s+sixty\s+seconds\.\s*Try it free at trustoffice\.app$"
)
_AI_BANNER_A = re.compile(
    r"^The\s+AI\s+Minutes\s+Builder\s+turns\s+three\s+bullet\s+points\s+into\s+a\s+formal\s+"
    r"WHEREAS/RESOLVED\s+resolution\s+in\s+sixty$"
)
_AI_BANNER_B = re.compile(r"^seconds\.\s*Try it free at\b")
_AI_BANNER_C = re.compile(r"^trustoffice\.app\s*Try it free at\b")
_TRUSTOFFICE_AUTO = re.compile(r"^TrustOffice makes this automatic\.$")
# Visual separator rules. Underscore runs are NOT included: a run of
# underscores is a form's fill-in blank, which is content.
_RULE = re.compile(r"^(?:[—–-]\s*){3,}$")
# A single em-dash / hyphen on its own is a visual separator, not content.
_RULE_SINGLE = re.compile(r"^[—–\-]$")
# Running "Family Governance Framework (cont.)" style page furniture.
_CONT_MARKER = re.compile(r"\(cont\.\)\s*$", re.I)


def _is_furniture(s: str) -> bool:
    t = s.strip()
    if not t:
        return False
    if _EDU_NOT_LEGAL.match(t):
        return True
    if _PAGE_MARK.match(t):
        return True
    if _BRAND_ONLY.match(t):
        return True
    if _RUNNING_LESSON.match(t):
        return True
    if _RUNNING_CAL.match(t):
        return True
    if _AI_BANNER.match(t) or _AI_BANNER_A.match(t) or _AI_BANNER_B.match(t) or _AI_BANNER_C.match(t):
        return True
    if _TRUSTOFFICE_AUTO.match(t):
        return True
    return False


def _is_disclaimer(text: str) -> bool:
    t = text.strip()
    return bool(
        _DISCLAIMER_LONG.search(t)
        or _DISCLAIMER_MIN.search(t)
        or _DISCLAIMER_TAX.search(t)
    )


def _strip_inline(text: str) -> str:
    # The educational-purposes disclaimer is a running footer on every page.
    # The FIRST occurrence is kept (it is a legal notice that belongs in the
    # article); the repeats are removed here.
    text = re.sub(r"TrustOffice\s*-\s*trustoffice\.app", "", text)
    text = re.sub(r"trustoffice\.app", "", text)
    text = re.sub(r"Page\s+\d+\s*(?:(?:of|/)\s*\d+)?", "", text)
    # A bare brand mark left behind after the URL was removed.
    text = re.sub(r"(?m)^\s*TrustOffice\s*[.·]?\s*$", "", text)
    # ...and the same mark trailing a disclaimer that we keep.
    text = re.sub(r"(?m)\s*TrustOffice\s*[.·]\s*$", "", text)
    return text


def _extract_runs(pdf_path: str) -> list:
    """Return [(text, font_size)] for every text run, in page order.

    pypdf's visitor reports a run's font size, and the newline that ENDS a
    run is reported with the NEXT run's size. So the size of a run is only
    trustworthy when the run carries visible text; newline-only runs are
    treated as separators and inherit the size of the text that follows.
    """
    reader = pypdf.PdfReader(pdf_path)
    runs = []

    def visitor(text, cm, tm, font_dict, font_size):
        if not text:
            return
        runs.append((text, float(font_size or 0)))

    for page in reader.pages:
        page.extract_text(visitor_text=visitor)
    # A newline-only run carries the FOLLOWING run's size, not its own.
    fixed = []
    for i, (text, size) in enumerate(runs):
        if text.strip() == "" and text:
            nxt = runs[i + 1][1] if i + 1 < len(runs) else size
            fixed.append((text, nxt))
        else:
            fixed.append((text, size))
    return fixed


def _clean_runs(runs: list) -> list:
    """Drop PDF furniture, keep font size.

    Newline-only runs are KEPT: they are the line separators. Only runs
    with visible text can be furniture.
    """
    out = []
    seen_disclaimer = False
    for text, size in runs:
        if text.strip() == "":
            # Structural separator - keep as-is.
            out.append((text, size))
            continue
        if _is_disclaimer(text):
            if seen_disclaimer:
                continue
            seen_disclaimer = True
        text = _strip_inline(text)
        if _is_furniture(text):
            continue
        stripped = text.strip()
        if not stripped:
            continue
        if _RULE.match(stripped) or _RULE_SINGLE.match(stripped):
            continue
        # A running document title with a "(cont.)" marker is page furniture,
        # not content.
        if _CONT_MARKER.search(stripped) and len(stripped) < 70:
            continue
        # Keep the trailing newline: it is the line separator. Only trailing
        # spaces are removed.
        out.append((text.rstrip(" \t"), size))
    return out


def _body_size(runs: list) -> float:
    """The most common (by character count) font size = body text size."""
    if not runs:
        return 0.0
    counts = {}
    for text, size in runs:
        counts[size] = counts.get(size, 0) + len(text.strip())
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _group_lines(runs: list) -> list:
    """Merge runs into visual lines, keeping the max font size of the line.

    A run's own font size is used (not the newline run's), so a heading keeps
    its heading size even when it is followed by body text on the same
    visual line.

    A line made of TWO runs is a two-column table row (the source PDFs build
    their tables from separate text runs per cell). Those are returned as
    ("cell1\tcell2", size) so the markdown converter can emit a table.
    """
    lines = []
    buf = ""
    buf_size = 0.0
    cells: list = []
    for text, size in runs:
        body_text = text.rstrip("\n")
        if body_text:
            if buf:
                # A second run on the same line = a table cell boundary.
                cells.append(buf)
                buf = ""
            buf += body_text
            buf_size = max(buf_size, size)
        if text.endswith("\n"):
            if buf.strip():
                if cells:
                    cells.append(buf)
                    lines.append(("\t".join(c.strip() for c in cells), buf_size))
                    cells = []
                else:
                    lines.append((buf, buf_size))
            buf = ""
            buf_size = 0.0
            cells = []
    if buf.strip():
        if cells:
            cells.append(buf)
            lines.append(("\t".join(c.strip() for c in cells), buf_size))
        else:
            lines.append((buf, buf_size))
    return [(ln.strip(), sz) for ln, sz in lines if ln.strip()]


def _heading_sizes(runs: list, body: float) -> dict:
    """Map each font size above the body size to a heading level.

    Two thresholds, both relative and absolute, because the 7 PDFs use
    different type scales:

      H1 ("## ")  size >= 70% of the largest size on the page
      H2 ("### ") size >= 50% of the largest size AND >= body + 1.5pt
      body        everything else

    The absolute floor matters: a bold lead-in that is only half a point
    larger than body text (e.g. "H - Health:") is body text, not a heading,
    even though it looks like one.
    """
    if not runs:
        return {}
    all_sizes = [sz for _, sz in runs]
    largest = max(all_sizes)
    h1_floor = largest * 0.70
    h2_floor = max(largest * 0.50, body + 1.5)
    levels = {}
    for sz in sorted({round(s, 2) for s in all_sizes}, reverse=True):
        if sz >= h1_floor:
            levels[sz] = 2      # "## "
        elif sz >= h2_floor:
            levels[sz] = 3      # "### "
    return levels


def _to_markdown(lines: list, body: float, heading_sizes: dict) -> str:
    out = []
    in_table = False
    for raw, size in lines:
        s = raw.strip()
        if not s:
            out.append("")
            continue
        if s[0] == "\x7f":
            s = s.lstrip("\x7f").strip()
            out.append(f"- {s}")
            continue
        if s[0] in "☐■□•✓✗":
            out.append(f"- {s[1:].strip()}")
            continue
        if s.startswith("\x7f"):
            out.append(f"- {s.lstrip(chr(0x7f)).strip()}")
            continue
        if s.startswith("⚠"):
            out.append(s.strip())
            continue
        if "\t" in s:
            cells = [c.strip() for c in s.split("\t") if c.strip()]
            # A cell that is only a fill-in blank must survive.
            if len(cells) == 1 and "_" in cells[0] and ":" in cells[0]:
                out.append(cells[0])
                continue
            # A row whose first cell ends with ":" and whose second cell is a
            # blank/underscore run is a FORM FIELD, not a table row. Keep it
            # as one plain line so the underscores survive verbatim.
            if len(cells) == 2 and cells[0].endswith(":"):
                # Keep the blank: it is the fill-in line of the form.
                out.append(f"{cells[0]} {cells[1]}".rstrip())
                continue
            if len(cells) == 1 and cells[0].endswith(":"):
                out.append(cells[0])
                continue
            # A row whose cells are all signature blanks is a form footer.
            if len(cells) >= 2 and all(
                c.count("_") >= 3 or c.startswith("[") for c in cells
            ):
                # A form footer (two signature blocks). Keep both halves as
                # plain text, separated by a space, so the line stays
                # verbatim-comparable to the PDF text layer.
                out.append(" ".join(cells))
                continue
            # A real table row has two SUBSTANTIVE cells (a label and a
            # value). A form field like "Decision: Approved / Denied ..." is
            # one cell that happens to contain a colon, and must stay plain
            # text so it stays verbatim-comparable to the PDF.
            substantive = [c for c in cells if not c.endswith(":")]
            if len(cells) >= 2 and len(substantive) >= 1 and "|" not in s:
                if not in_table:
                    out.append("| " + " | ".join(["Item", "Rule"] + [""] * (len(cells) - 2)) + " |")
                    out.append("|" + "|".join([" --- "] * len(cells)) + "|")
                    in_table = True
                out.append("| " + " | ".join(cells) + " |")
                continue
        if in_table and not s:
            in_table = False
        level = heading_sizes.get(round(size, 2))
        if level:
            out.append("#" * level + " " + s)
        else:
            out.append(s)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _merge_adjacent_headings(markdown: str) -> str:
    """Join a heading that is immediately followed by another heading.

    The source PDFs split a single visual title across two type sizes
    ("HEMS Decision Framework" + "& Quick Reference Card"). Joining them
    keeps the article's structure readable and the section title meaningful.
    """
    lines = markdown.split("\n")
    out = []
    for ln in lines:
        m = re.match(r"^(#{2,6}) (.+)$", ln)
        if m and out:
            pm = re.match(r"^(#{2,6}) (.+)$", out[-1])
            if pm and pm.group(1) == m.group(1):
                # Same level, adjacent: one visual title split across two
                # type sizes. Join them.
                out[-1] = f"{pm.group(1)} {pm.group(2)} {m.group(2)}".strip()
                continue
        out.append(ln)
    return "\n".join(out)


def _sections(markdown: str) -> list:
    """Split on "## " headings into (heading, body) pairs."""
    chunks = re.split(r"(?m)^(##\s+.+)$", markdown)
    out = []
    pre = chunks[0].strip()
    if pre:
        out.append(("", pre))
    for i in range(1, len(chunks), 2):
        heading = chunks[i].strip()[3:].strip()
        body = chunks[i + 1].strip()
        if body:
            out.append((heading, body))
    return out


def _front_matter(title: str, pdf_stem: str, digest: str, part: Optional[str]) -> str:
    lines = [
        "---",
        f"title: {title}",
        "source: Trustee 101 course",
        "provenance: from Trustee 101",
        "tags: [trustee-101, doctrine, course-material]",
        f"source_pdf: {pdf_stem}.pdf",
        f"source_sha256: {digest}",
        "status: published",
    ]
    if part:
        lines.append(f"part: {part}")
    lines += ["---", ""]
    return "\n".join(lines)


def main() -> int:
    written = []
    for pdf_stem, out_base, title in PDFS:
        pdf_path = f"{SRC_DIR}/{pdf_stem}.pdf"
        try:
            with open(pdf_path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            print(f"MISSING SOURCE: {pdf_path}")
            return 1
        runs = _clean_runs(_extract_runs(pdf_path))
        body_size = _body_size(runs)
        heading_sizes = _heading_sizes(runs, body_size)
        lines = _group_lines(runs)
        markdown = _to_markdown(lines, body_size, heading_sizes)
        markdown = _merge_adjacent_headings(markdown)
        sections = _sections(markdown)
        total = sum(len(b) for _, b in sections)
        if total <= SPLIT_THRESHOLD:
            inner = "\n\n".join((f"## {h}\n\n{b}" if h else b) for h, b in sections)
            text = _front_matter(title, pdf_stem, digest, None)
            text += f"# {title}\n\n{inner}\n"
            with open(f"{OUT_DIR}/{out_base}.md", "w", encoding="utf-8") as f:
                f.write(text)
            written.append(out_base)
            print(f"WROTE {out_base}.md ({len(text)} chars, {len(sections)} section(s))")
            continue
        pieces = [(h, b) for h, b in sections if b.strip()]
        # A short lead-in (the PDF cover page) is folded into the first real
        # section rather than becoming a stub article of its own.
        if len(pieces) > 1 and len(pieces[0][1]) < 900:
            head, body0 = pieces[0]
            merged_head = pieces[1][0] or "Overview"
            pieces = [(merged_head, body0 + "\n\n" + pieces[1][1])] + pieces[2:]
        # If the first section is still oversized, split IT at its own
        # "### " sub-headings (the PDF's template list), so each article is a
        # coherent unit (one template per article) rather than a fragment.
        if pieces and len(pieces[0][1]) > SPLIT_THRESHOLD:
            first_head, first_body = pieces[0]
            subs = re.split(r"(?m)^(###\s+.+)$", first_body)
            if len(subs) > 3:
                lead = subs[0].strip()
                sub_pieces = []
                for j in range(1, len(subs), 2):
                    sub_head = subs[j].strip()[4:].strip()
                    sub_body = subs[j + 1].strip()
                    if not sub_body:
                        continue
                    if lead and j == 1:
                        sub_body = lead + "\n\n" + sub_body
                        lead = ""
                    sub_pieces.append((sub_head, sub_body))
                pieces = sub_pieces + pieces[1:]
        for idx, (heading, piece) in enumerate(pieces, start=1):
            suffix = heading or f"Part {idx}"
            part_title = f"{title} - {suffix}"
            name = f"{out_base}-{idx:02d}.md"
            text = _front_matter(part_title, pdf_stem, digest, f"{idx} of {len(pieces)}")
            text += f"# {part_title}\n\n{piece}\n"
            with open(f"{OUT_DIR}/{name}", "w", encoding="utf-8") as f:
                f.write(text)
            written.append(name)
            print(f"WROTE {name} ({len(text)} chars) - {suffix}")
    print(f"\nTOTAL {len(written)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
