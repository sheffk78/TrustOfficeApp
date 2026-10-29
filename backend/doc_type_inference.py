# Doc-type inference module: filename/extension + title keywords -> DOC_CATEGORIES key
# Scaffold for the council doc-recognition pillar (2026-10-29). Pure function,
# no LLM call - cheap, deterministic, override-friendly. Used by routers/vault.py
# at upload; the member can change the category afterwards (override wins).

DOC_TYPE_HINTS = [
    # (category, regex patterns over "filename + title", lowercased)
    ("amendment", [r"\bamend", r"\brestat", r"first[- _]?amendment", r"second[- _]?amendment"]),
    ("trust_instrument", [r"trust\s+agreement", r"declaration\s+of\s+trust", r"trust\s+instrument",
                          r"revocable\s+trust", r"irrevocable\s+trust", r"\btrust\b.*\bdated\b"]),
    ("schedule_a", [r"schedule\s+a"]),
    ("minutes", [r"minutes", r"meeting\s+minutes", r"resolution(s)?\b"]),
    ("tax_return", [r"1041", r"tax\s+return"]),
    ("k1", [r"\bk-?1\b", r"schedule\s+k"]),
    ("ein_letter", [r"\bein\b", r"cp575", r"cp\s?575", r"determination\s+letter.*ein"]),
    ("irs_determination", [r"501\s*\(?c\)?\s*\(?\s*3\s*\)?", r"determination\s+letter"]),
    ("financial_statement", [r"accounting\b", r"financial\s+statement", r"statement\s+of\s+account"]),
    ("appraisal", [r"appraisal", r"\bvaluation\b"]),
    ("notice", [r"\bnotice\b.*beneficiar", r"beneficiar.*\bnotice\b"]),
    ("insurance", [r"insurance\s+policy", r"\brider\b", r"\bpolicy\b"]),
    ("deed", [r"\bdeed\b", r"quitclaim", r"warranty\s+deed"]),
    ("bank_statement", [r"bank\s+statement", r"account\s+statement", r"\bstatement\b.*\b(2023|2024|2025|2026)\b"]),
    ("legal_opinion", [r"legal\s+opinion", r"attorney\s+letter", r"counsel\s+letter"]),
    ("court_order", [r"court\s+order", r"\bjudgment\b", r"\bdecree\b"]),
]

EXT_PDF_IMAGE = ("pdf", "png", "jpg", "jpeg", "webp")


def infer_doc_type(file_name: str, title: str = "", content_type: str = "") -> str | None:
    """Return a DOC_CATEGORIES key inferred from the filename + title, or None.

    Deterministic and cheap (regex only, no LLM). Returns None when nothing
    matches confidently enough - the caller keeps the member-chosen category.
    """
    import re

    hay = f"{file_name or ''} {title or ''}".lower()
    if not hay.strip():
        return None
    for category, patterns in DOC_TYPE_HINTS:
        for pat in patterns:
            if re.search(pat, hay):
                return category
    return None