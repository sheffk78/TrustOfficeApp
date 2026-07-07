"""
Trust Document Intelligence — AI extraction pipeline.
Triggered when a trust instrument is uploaded to the Vault.
Extracts: grantor, trustee(s), trust type, beneficiaries, distribution 
standard, trustee powers, removal/termination provisions, formation date.

Flow: PDF text extraction (PyMuPDF) → AI analysis (OpenRouter) → store in MongoDB
      → populate existing trust/entity fields (never overwrites user-entered data)
"""
import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from database import db
from ai_client import ai_sonnet

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are a trust document analyzer. Extract the following information 
from the trust document text below. Return ONLY valid JSON with these exact fields:

{
  "grantor_name": "string — the person who created the trust (also called settlor or trustor)",
  "trustee_names": ["array of strings — all named trustees"],
  "trust_type": "revocable | irrevocable | unknown",
  "beneficiary_names": ["array of strings — all named beneficiaries"],
  "distribution_standard": {
    "exact_language": "string — the exact text from the document describing distribution standards",
    "type": "HEMS | sole_discretion | ascertainable_standard | other",
    "article_reference": "string — article and section number where this appears"
  },
  "distribution_rules": {
    "specific_purposes": ["array of strings — specific permitted purposes like education, medical, housing, support"],
    "amount_guidance": "string — any specific dollar amounts, formulas, or guidance about distribution amounts (e.g., 'reasonable amounts', 'up to $50,000 per year', 'tuition and reasonable living expenses')",
    "needs_based_factors": ["array of strings — factors the trustee should consider like 'beneficiary's other resources', 'beneficiary's needs', 'standard of living'"],
    "equal_treatment_requirement": "string — whether the trust requires equal treatment, equitable treatment, or allows differential treatment. Include exact language if present",
    "article_reference": "string — article and section where distribution rules appear"
  },
  "trustee_powers_detail": {
    "investment_powers": "string — specific investment powers granted",
    "discretion_powers": "string — the scope of trustee discretion in distributions (sole discretion, reasonable discretion, etc.)",
    "spendthrift_provisions": "string — any spendthrift clause language that restricts beneficiary access to distributions",
    "article_reference": "string"
  },
  "trustee_powers": [
    {"power": "string — what the trustee can do", "article_reference": "string — article/section"}
  ],
  "removal_provisions": {
    "summary": "string — how a trustee can be removed",
    "article_reference": "string"
  },
  "termination_rules": {
    "summary": "string — when and how the trust terminates",
    "article_reference": "string"
  },
  "formation_date": "YYYY-MM-DD or null",
  "ein_required": true
}

Rules:
- If a field cannot be found in the document, use null or empty array.
- For article_reference, cite the specific article and section (e.g., "Article 4, Section 4.2").
- For distribution_standard.type, classify as HEMS if the document mentions Health, Education,
  Maintenance, Support. Classify as sole_discretion if it says "sole and absolute discretion"
  or similar. Classify as ascertainable_standard if it references a specific standard.
  Otherwise "other".
- Return ONLY the JSON, no commentary.

Document text:
"""

MAX_TEXT_LENGTH = 50000  # Truncate very long documents for AI context


def extract_text_from_pdf(file_content: bytes) -> Optional[str]:
    """
    Extract text from a document using PyMuPDF.
    Handles PDF, DOCX, DOC, and TXT files.
    Returns None if extraction fails or document is scanned (no text layer).
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_content, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        text = text.strip()
        if not text:
            logger.warning("PDF text extraction returned empty — likely a scanned document")
            return None
        return text
    except ImportError:
        logger.error("PyMuPDF not installed. Install with: pip install PyMuPDF")
        return None
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return None


def ocr_pdf(file_content: bytes, max_pages: int = 30) -> Optional[str]:
    """
    Run OCR on a scanned PDF using Tesseract.
    Renders each page to an image with PyMuPDF, then extracts text with pytesseract.
    Limits to max_pages to prevent excessive processing time on large documents.

    Args:
        file_content: Raw PDF bytes
        max_pages: Maximum number of pages to OCR (safety limit)

    Returns:
        Extracted text string, or None if OCR fails
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io

        doc = fitz.open(stream=file_content, filetype="pdf")
        total_pages = len(doc)
        pages_to_ocr = min(total_pages, max_pages)

        logger.info(f"Starting OCR on {pages_to_ocr} of {total_pages} pages")

        text_parts = []
        for i in range(pages_to_ocr):
            page = doc[i]
            # Render at 200 DPI — good balance of accuracy and speed
            pix = page.get_pixmap(dpi=200)
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))

            # Run Tesseract OCR
            page_text = pytesseract.image_to_string(image)
            if page_text.strip():
                text_parts.append(page_text.strip())

        doc.close()

        if not text_parts:
            logger.warning("OCR completed but extracted no text")
            return None

        full_text = "\n".join(text_parts)
        logger.info(f"OCR extracted {len(full_text)} characters from {pages_to_ocr} pages")
        return full_text

    except ImportError as e:
        logger.error(f"OCR dependencies not installed: {e}. Need: pip install pytesseract Pillow")
        return None
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return None


def extract_text_from_docx(file_content: bytes) -> Optional[str]:
    """Extract text from a .docx file using python-docx."""
    try:
        from docx import Document
        import io
        doc = Document(io.BytesIO(file_content))
        text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        return text if text else None
    except ImportError:
        logger.error("python-docx not installed. Install with: pip install python-docx")
        return None
    except Exception as e:
        logger.error(f"DOCX text extraction failed: {e}")
        return None


def extract_text_from_txt(file_content: bytes) -> Optional[str]:
    """Extract text from a plain text file."""
    try:
        # Try UTF-8 first, fall back to latin-1
        for encoding in ("utf-8", "latin-1"):
            try:
                text = file_content.decode(encoding).strip()
                if text:
                    return text
            except UnicodeDecodeError:
                continue
        return None
    except Exception as e:
        logger.error(f"TXT extraction failed: {e}")
        return None


def extract_text(file_content: bytes, filename: str = "") -> Optional[str]:
    """
    Extract text from any supported file format.
    Detects format by file signature (magic bytes) first, falls back to filename extension.
    """
    if not file_content:
        return None

    # Detect by magic bytes
    if file_content[:4] == b'%PDF':
        return extract_text_from_pdf(file_content)
    elif file_content[:2] == b'PK':
        # ZIP-based format (DOCX, ODT)
        return extract_text_from_docx(file_content)
    else:
        # Try as plain text
        text = extract_text_from_txt(file_content)
        if text:
            return text
        # Last resort: try PDF (some files have weird headers)
        return extract_text_from_pdf(file_content)


def _clean_json_response(response: str) -> str:
    """Strip markdown code fences and whitespace from AI response."""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


async def _populate_trust_fields(trust_id: str, user_id: str, extracted: dict):
    """
    Flow extracted data into the trusts collection (Settings → Trust Profile).
    Only fills EMPTY fields — never overwrites user-entered data.
    """
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "start_date": 1, "beneficiary_standard": 1, "trust_type": 1}
    )
    if not trust:
        return

    safe_updates = {}

    # Formation date → start_date (only if not already set)
    if extracted.get("formation_date") and not trust.get("start_date"):
        safe_updates["start_date"] = extracted["formation_date"]

    # Distribution standard → beneficiary_standard (only if not already set)
    dist_std = extracted.get("distribution_standard", {})
    if dist_std.get("exact_language") and not trust.get("beneficiary_standard"):
        safe_updates["beneficiary_standard"] = dist_std["exact_language"]

    # Trust type note (always set — doesn't overwrite the enum trust_type field)
    if extracted.get("trust_type") and extracted["trust_type"] != "unknown":
        safe_updates["trust_type_note"] = extracted["trust_type"]

    if safe_updates:
        safe_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.trusts.update_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"$set": safe_updates}
        )
        logger.info(f"Populated trust fields for {trust_id}: {list(safe_updates.keys())}")


async def _populate_entity_fields(trust_id: str, user_id: str, extracted: dict):
    """
    Flow extracted data into the entities collection.
    Updates the primary trust entity with trustee names and distribution article ref.
    """
    entity = await db.entities.find_one({
        "trust_id": trust_id, "user_id": user_id, "entity_type": "trust"
    })

    if not entity:
        return

    updates = {}

    if extracted.get("trustee_names"):
        # Only set if not already populated
        if not entity.get("trustee_names"):
            updates["trustee_names"] = extracted["trustee_names"]

    dist_std = extracted.get("distribution_standard", {})
    if dist_std.get("article_reference"):
        if not entity.get("article_ref_distribution"):
            updates["article_ref_distribution"] = dist_std["article_reference"]

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.entities.update_one(
            {"entity_id": entity["entity_id"]},
            {"$set": updates}
        )
        logger.info(f"Populated entity fields for trust {trust_id}: {list(updates.keys())}")


async def _update_onboarding_step(trust_id: str, user_id: str):
    """Mark the trust_doc_analyzed onboarding step as complete."""
    try:
        await db.user_onboarding.update_one(
            {"user_id": user_id},
            {"$set": {
                "trust_doc_analyzed": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
    except Exception as e:
        logger.warning(f"Failed to update onboarding step: {e}")


async def analyze_trust_document(
    trust_id: str,
    user_id: str,
    doc_id: str,
    file_content: bytes,
    is_amendment: bool = False
) -> dict:
    """
    Full pipeline: extract text → AI analysis → store results → populate fields.
    Called async after vault upload, or manually via re-analyze endpoint.

    Args:
        trust_id: The trust this document belongs to
        user_id: The user who owns this trust
        doc_id: The vault document ID
        file_content: Raw PDF bytes
        is_amendment: If True, this is an amendment (merge with existing analysis)

    Returns:
        dict with status and extracted_fields (or error)
    """
    analysis_id = f"tda_{doc_id[:20]}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    # Create pending analysis record
    await db.trust_document_analysis.insert_one({
        "analysis_id": analysis_id,
        "trust_id": trust_id,
        "user_id": user_id,
        "vault_document_id": doc_id,
        "is_amendment": is_amendment,
        "status": "pending",
        "extracted_fields": {},
        "raw_text_length": 0,
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        # Step 1: Extract text from document (supports PDF, DOCX, TXT)
        text = extract_text(file_content)
        if not text:
            # Fallback: try OCR for scanned PDFs (renders pages to images, runs Tesseract)
            logger.info(f"Text extraction returned no text for doc {doc_id}, attempting OCR fallback")
            text = ocr_pdf(file_content)

        if not text:
            await db.trust_document_analysis.update_one(
                {"analysis_id": analysis_id},
                {"$set": {
                    "status": "failed",
                    "error_message": "Could not extract text from the document. The file may be scanned, image-only, or in an unsupported format. Please upload a text-based PDF or Word document.",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            return {"status": "failed", "error": "Text extraction failed — likely scanned or unsupported format"}

        # Step 2: Update status to analyzing
        await db.trust_document_analysis.update_one(
            {"analysis_id": analysis_id},
            {"$set": {
                "status": "analyzing",
                "raw_text_length": len(text),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        # Truncate very long documents
        text_for_ai = text[:MAX_TEXT_LENGTH] if len(text) > MAX_TEXT_LENGTH else text

        # Step 3: AI analysis via OpenRouter
        response = await ai_sonnet(
            system_prompt=ANALYSIS_PROMPT,
            user_content=text_for_ai,
            max_tokens=4000,
            temperature=0.1
        )

        # Step 4: Parse JSON response
        cleaned = _clean_json_response(response)
        extracted = json.loads(cleaned)

        # Step 5: Store results
        await db.trust_document_analysis.update_one(
            {"analysis_id": analysis_id},
            {"$set": {
                "status": "complete",
                "extracted_fields": extracted,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        # Step 6: Flow data into existing collections
        await _populate_trust_fields(trust_id, user_id, extracted)
        await _populate_entity_fields(trust_id, user_id, extracted)
        await _update_onboarding_step(trust_id, user_id)

        logger.info(f"Trust document analysis complete for trust {trust_id}, doc {doc_id}")
        return {"status": "complete", "extracted_fields": extracted}

    except json.JSONDecodeError as e:
        logger.error(f"AI returned invalid JSON for trust {trust_id}: {e}")
        await db.trust_document_analysis.update_one(
            {"analysis_id": analysis_id},
            {"$set": {
                "status": "failed",
                "error_message": f"AI returned invalid JSON: {str(e)}",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return {"status": "failed", "error": f"JSON parse error: {e}"}

    except Exception as e:
        logger.error(f"Trust document analysis failed for trust {trust_id}: {e}")
        await db.trust_document_analysis.update_one(
            {"analysis_id": analysis_id},
            {"$set": {
                "status": "failed",
                "error_message": str(e),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return {"status": "failed", "error": str(e)}


# ==================== BANK STATEMENT ANALYSIS ====================

BANK_STATEMENT_PROMPT = """You are a bank statement analyzer. Extract the following information
from the bank statement text below. Return ONLY valid JSON with these exact fields:

{
  "bank_name": "string — the name of the bank or financial institution",
  "account_last_four": "string — last 4 digits of the account number only (NOT the full account number)",
  "statement_period_start": "YYYY-MM-DD or null — start of the statement period",
  "statement_period_end": "YYYY-MM-DD or null — end of the statement period",
  "beginning_balance": number or null — balance at the start of the period,
  "ending_balance": number or null — balance at the end of the period,
  "total_deposits": number or null — total deposits/credits during the period,
  "total_withdrawals": number or null — total withdrawals/debits during the period
}

CRITICAL RULES:
- NEVER include full account numbers. Only extract the last 4 digits.
- If a field cannot be found, use null.
- Dollar amounts should be plain numbers (e.g., 15420.50, not "$15,420.50").
- For statement_period_start and end, use YYYY-MM-DD format. If the statement says
  "January 1-31, 2025", return start="2025-01-01" and end="2025-01-31".
- Return ONLY the JSON, no commentary.

Statement text:
"""


def _sanitize_extraction(raw: dict) -> dict:
    """Scrub any full account numbers from the extraction result. Only last 4 allowed."""
    import re as _re

    sanitized = dict(raw)

    # Scrub account_last_four — keep only last 4 if longer
    acct = sanitized.get("account_last_four")
    if acct and isinstance(acct, str):
        # Remove any non-digit characters, then take last 4
        digits = _re.sub(r'\D', '', acct)
        sanitized["account_last_four"] = digits[-4:] if len(digits) >= 4 else None

    # Scrub any other fields that might contain full account numbers
    for key, val in sanitized.items():
        if isinstance(val, str):
            # Remove any sequence of 8+ consecutive digits (likely account numbers)
            cleaned = _re.sub(r'\b\d{8,}\b', '[REDACTED]', val)
            sanitized[key] = cleaned

    return sanitized


async def analyze_bank_statement(
    trust_id: str,
    user_id: str,
    statement_id: str,
    file_content: bytes,
    account_id: Optional[str] = None,
) -> dict:
    """
    Extract key data from a bank statement PDF.
    Called async after vault upload when category=bank_statement.

    Extracts: bank_name, account_last_four, statement period, balances, totals.
    Stores results in bank_statements collection.

    Args:
        trust_id: The trust this statement belongs to
        user_id: The user who owns this trust
        statement_id: The bank_statements document ID
        file_content: Raw PDF bytes
        account_id: Optional bank account ID to link this statement to

    Returns:
        dict with status and extracted_fields (or error)
    """
    try:
        # Step 1: Extract text from PDF
        text = extract_text_from_pdf(file_content)
        if not text:
            # Fallback: OCR for scanned statements
            logger.info(f"Text extraction returned no text for statement {statement_id}, attempting OCR fallback")
            text = ocr_pdf(file_content)

        if not text:
            await db.bank_statements.update_one(
                {"statement_id": statement_id},
                {"$set": {
                    "extraction_status": "failed",
                    "extraction_error": "Could not extract text from the statement. The file may be scanned or in an unsupported format.",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            return {"status": "failed", "error": "Text extraction failed"}

        # Step 2: AI analysis
        text_for_ai = text[:MAX_TEXT_LENGTH] if len(text) > MAX_TEXT_LENGTH else text

        response = await ai_sonnet(
            system_prompt=BANK_STATEMENT_PROMPT,
            user_content=text_for_ai,
            max_tokens=2000,
            temperature=0.1
        )

        # Step 3: Parse JSON response
        cleaned = _clean_json_response(response)
        extracted = json.loads(cleaned)

        # Step 4: Sanitize — no full account numbers
        extracted = _sanitize_extraction(extracted)

        # Step 5: Validate account_last_four matches if account_id provided
        needs_review = False
        if account_id:
            account = await db.bank_accounts.find_one(
                {"account_id": account_id}, {"_id": 0, "last_four": 1}
            )
            if account and extracted.get("account_last_four"):
                if extracted["account_last_four"] != account.get("last_four"):
                    needs_review = True
                    logger.warning(
                        f"Statement {statement_id} account_last_four ({extracted['account_last_four']}) "
                        f"does not match account {account_id} last_four ({account.get('last_four')})"
                    )

        # Step 6: Store results
        update_doc = {
            "bank_name": extracted.get("bank_name"),
            "account_last_four": extracted.get("account_last_four"),
            "statement_period_start": extracted.get("statement_period_start"),
            "statement_period_end": extracted.get("statement_period_end"),
            "beginning_balance": extracted.get("beginning_balance"),
            "ending_balance": extracted.get("ending_balance"),
            "total_deposits": extracted.get("total_deposits"),
            "total_withdrawals": extracted.get("total_withdrawals"),
            "extraction_status": "needs_review" if needs_review else "completed",
            "extraction_confidence": 0.85,
            "needs_review": needs_review,
            "extraction_error": None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        await db.bank_statements.update_one(
            {"statement_id": statement_id},
            {"$set": update_doc}
        )

        # Step 7: Auto-update onboarding
        try:
            await _update_onboarding_step(trust_id, user_id)
        except Exception:
            pass

        logger.info(f"Bank statement analysis complete for statement {statement_id}")
        return {"status": "complete", "extracted_fields": extracted}

    except json.JSONDecodeError as e:
        logger.error(f"AI returned invalid JSON for statement {statement_id}: {e}")
        await db.bank_statements.update_one(
            {"statement_id": statement_id},
            {"$set": {
                "extraction_status": "failed",
                "extraction_error": f"AI returned invalid JSON: {str(e)}",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return {"status": "failed", "error": f"JSON parse error: {e}"}

    except Exception as e:
        logger.error(f"Bank statement analysis failed for statement {statement_id}: {e}")
        await db.bank_statements.update_one(
            {"statement_id": statement_id},
            {"$set": {
                "extraction_status": "failed",
                "extraction_error": str(e),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return {"status": "failed", "error": str(e)}