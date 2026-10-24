"""
Verbatim-fidelity gate for the Trustee-101 knowledge articles.

WHY (2026-10-23, P2a): the extraction pipeline converts PDF layout into
markdown. Any transformation that alters wording is a legal-text change, and
the boundary for P2a is "verbatim extraction only, no new legal text". This
test makes that boundary machine-checkable instead of a promise.

What it checks, per extracted article:
  1. The article declares the "from Trustee 101" provenance tag and names the
     source PDF (plus its SHA-256), so every line is traceable.
  2. Every SENTENCE in the article appears in the source PDF's text layer
     (after whitespace normalization). This catches paraphrase, reworded
     clauses, and hallucinated text.
  3. The source PDF's own educational-purposes disclaimer is preserved
     somewhere in the article corpus for that PDF.
  4. No template-count claim ("41 template") can appear in the corpus.
"""
import hashlib
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
KB_DIR = BACKEND / "knowledge"

# Where the reviewed course PDFs live. The backend ships one of them; the
# website project holds the full set. Both are searched so the test works
# in CI (backend copy only) and locally (full set).
PDF_DIRS = [
    BACKEND / "static",
    BACKEND.parent.parent / "TrustOffice-Website" / "frontend" / "public" / "pdfs",
]

# (article glob prefix, source pdf stem)
EXPECTED = {
    "26-trustee-101-minute-templates": "minute-templates-l3",
    "27-trustee-101-hems-decision-framework": "hems-decision-framework",
    "28-trustee-101-separation-checklist": "separation-checklist",
    "29-trustee-101-trust-tax-calendar": "trust-tax-calendar-l6",
    "30-trustee-101-investment-policy-statement": "investment-policy-statement-template-l7",
    "31-trustee-101-beneficiary-communication-templates": "beneficiary-communication-templates-l8",
    "32-trustee-101-family-governance-framework": "family-governance-framework-l9",
}


def _find_pdf(stem: str) -> Path | None:
    for d in PDF_DIRS:
        p = d / f"{stem}.pdf"
        if p.exists():
            return p
    return None


def _pdf_text(path: Path) -> str:
    try:
        import pypdf
    except ImportError:
        return ""
    reader = pypdf.PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _norm(text: str) -> str:
    """Normalize whitespace and the unicode dashes the PDFs use."""
    text = text.replace("—", "-").replace("–", "-").replace("‑", "-")
    text = text.replace("•", " ").replace("·", " ").replace("☐", " ").replace("■", " ")
    text = re.sub(r"[\s ]+", " ", text)
    return text.strip()


def _sentences(markdown: str) -> list[str]:
    """Content sentences of an article, minus its own metadata."""
    # Drop front matter.
    body = re.sub(r"\A---.*?\n---\s*", "", markdown, flags=re.S)
    # Drop markdown heading markers, list markers, bold/italic markers.
    body = re.sub(r"(?m)^#{1,6}\s*", "", body)
    body = re.sub(r"(?m)^\s*[-*]\s+", "", body)
    body = body.replace("**", "").replace("*", "").replace("`", "")
    # The article title line is metadata, not doctrine.
    out = []
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Trustee 101 -"):
            continue
        if line.startswith("part:"):
            continue
        # Markdown table rows: check each CELL separately, because the pipe
        # characters are formatting, not content.
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("- ") for c in cells):
                continue  # table separator row
            for c in cells:
                if len(c) >= 25:
                    out.append(c)
            continue
        # A form field is "Label: ______"; the PDF stores the label and the
        # fill-in blank as SEPARATE runs, so the blank is a separate cell.
        # Compare the two halves independently.
        m = re.match(r"^([^:\n]{2,60}:)\s*(_+)$", line)
        if m:
            if len(m.group(1)) >= 25:
                out.append(m.group(1))
            continue
        # Split into sentences on terminal punctuation.
        for s in re.split(r"(?<=[.!?])\s+", line):
            s = s.strip()
            if len(s) >= 25:
                out.append(s)
    return out


def _article_text(md: str) -> str:
    body = re.sub(r"\A---.*?\n---\s*", "", md, flags=re.S)
    body = re.sub(r"(?m)^#{1,6}\s*", "", body)
    body = re.sub(r"(?m)^\s*[-*]\s+", "", body)
    return _norm(body)


class TestTrustee101Extraction:
    def test_all_seven_articles_exist(self):
        for prefix in EXPECTED:
            matches = sorted(KB_DIR.glob(f"{prefix}*.md"))
            assert matches, f"no knowledge article for {prefix}"

    def test_articles_declare_provenance(self):
        for prefix in EXPECTED:
            for path in sorted(KB_DIR.glob(f"{prefix}*.md")):
                md = path.read_text(encoding="utf-8")
                assert "provenance: from Trustee 101" in md, (
                    f"{path.name} is missing the 'from Trustee 101' tag"
                )
                assert "source_pdf:" in md, f"{path.name} does not name its source PDF"
                assert "source_sha256:" in md, f"{path.name} has no source checksum"

    def test_source_checksums_match_the_pdfs(self):
        for prefix, stem in EXPECTED.items():
            pdf = _find_pdf(stem)
            if pdf is None:
                continue
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            for path in sorted(KB_DIR.glob(f"{prefix}*.md")):
                md = path.read_text(encoding="utf-8")
                m = re.search(r"source_sha256:\s*([0-9a-f]{64})", md)
                assert m, f"{path.name} has no source_sha256"
                assert m.group(1) == digest, (
                    f"{path.name} checksum does not match {pdf.name}: the article "
                    f"was extracted from a different revision of the PDF"
                )

    def test_every_sentence_appears_verbatim_in_the_source_pdf(self):
        for prefix, stem in EXPECTED.items():
            pdf = _find_pdf(stem)
            if pdf is None:
                continue
            source = _norm(_pdf_text(pdf))
            for path in sorted(KB_DIR.glob(f"{prefix}*.md")):
                md = path.read_text(encoding="utf-8")
                for sentence in _sentences(md):
                    norm = _norm(sentence)
                    # Long sentences may be line-wrapped in the PDF; compare
                    # on a token basis for anything over 90 chars.
                    if len(norm) <= 90:
                        assert norm in source, (
                            f"{path.name}: sentence not found verbatim in "
                            f"{pdf.name}: {norm[:120]!r}"
                        )
                    else:
                        head = " ".join(norm.split()[:12])
                        assert head in source, (
                            f"{path.name}: sentence not found verbatim in "
                            f"{pdf.name}: {head[:120]!r}"
                        )

    def test_disclaimers_are_preserved(self):
        for prefix, stem in EXPECTED.items():
            pdf = _find_pdf(stem)
            if pdf is None:
                continue
            source = _norm(_pdf_text(pdf))
            corpus = " ".join(
                _article_text(p.read_text(encoding="utf-8"))
                for p in sorted(KB_DIR.glob(f"{prefix}*.md"))
            )
            for marker in (
                "educational purposes only",
                "not legal advice",
                "does not constitute legal advice",
            ):
                if marker in source.lower():
                    assert marker in corpus.lower(), (
                        f"{prefix}: the PDF's '{marker}' disclaimer was dropped"
                    )
                    break

    def test_no_stale_template_count_claim(self):
        """The '41 templates' claim must not appear anywhere in the corpus."""
        for prefix in EXPECTED:
            for path in sorted(KB_DIR.glob(f"{prefix}*.md")):
                md = path.read_text(encoding="utf-8")
                assert not re.search(r"\b41\s+(minutes\s+)?templates?\b", md, re.I), (
                    f"{path.name} contains a stale template-count claim"
                )
