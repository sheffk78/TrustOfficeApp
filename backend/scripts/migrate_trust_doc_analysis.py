"""
Batch migration script — analyze trust documents already in the vault for existing users.

This script finds all trust instruments and amendments in the vault that have file content
but no corresponding analysis record, and triggers AI extraction for each.

Usage:
    cd /Users/socializerender/Projects/TrustOfficeApp
    python -m scripts.migrate_trust_doc_analysis

    # Or to process a single trust:
    python -m scripts.migrate_trust_doc_analysis --trust-id trust_xxx

    # Dry run (see what would be processed without triggering):
    python -m scripts.migrate_trust_doc_analysis --dry-run
"""
import asyncio
import argparse
import logging
import sys
import os

# Add backend to path when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import db
from trust_doc_analyzer import analyze_trust_document

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def find_unanalyzed_docs(trust_id_filter: str = None):
    """
    Find all trust instruments and amendments in the vault that have file content
    but no completed analysis record.
    """
    query = {
        "category": {"$in": ["trust_instrument", "amendment"]},
        "file_content": {"$exists": True, "$ne": None},
    }
    if trust_id_filter:
        query["trust_id"] = trust_id_filter

    docs = await db.vault_documents.find(
        query,
        {"_id": 0, "doc_id": 1, "trust_id": 1, "user_id": 1, "category": 1,
         "file_name": 1, "file_content_type": 1, "created_at": 1}
    ).sort("created_at", 1).to_list(1000)

    unanalyzed = []
    for doc in docs:
        # Check if there's already a complete analysis for this doc
        existing = await db.trust_document_analysis.find_one({
            "vault_document_id": doc["doc_id"],
            "status": "complete"
        })
        if not existing:
            unanalyzed.append(doc)

    return unanalyzed


async def run_migration(trust_id_filter: str = None, dry_run: bool = False):
    """Run the batch migration."""
    logger.info("Scanning for unanalyzed trust documents in the vault...")

    docs = await find_unanalyzed_docs(trust_id_filter)

    if not docs:
        logger.info("No unanalyzed trust documents found. All existing docs have been processed.")
        return

    logger.info(f"Found {len(docs)} document(s) to analyze.")

    if dry_run:
        for doc in docs:
            logger.info(
                f"  [DRY RUN] Would analyze: doc_id={doc['doc_id']}, "
                f"trust_id={doc['trust_id']}, "
                f"file={doc.get('file_name', 'unknown')}, "
                f"type={doc.get('file_content_type', 'unknown')}"
            )
        return

    success_count = 0
    fail_count = 0

    for i, doc in enumerate(docs, 1):
        logger.info(
            f"  [{i}/{len(docs)}] Analyzing doc_id={doc['doc_id']}, "
            f"trust_id={doc['trust_id']}, "
            f"file={doc.get('file_name', 'unknown')}"
        )

        # Only process PDFs (text extraction only works on PDFs for now)
        content_type = doc.get("file_content_type", "")
        if "pdf" not in content_type.lower():
            logger.warning(f"    Skipping — not a PDF (content_type={content_type})")
            fail_count += 1
            continue

        file_content = doc.get("file_content")
        if not file_content:
            logger.warning(f"    Skipping — no file content")
            fail_count += 1
            continue

        is_amendment = doc.get("category") == "amendment"

        try:
            result = await analyze_trust_document(
                trust_id=doc["trust_id"],
                user_id=doc["user_id"],
                doc_id=doc["doc_id"],
                file_content=file_content,
                is_amendment=is_amendment
            )

            if result["status"] == "complete":
                fields = result.get("extracted_fields", {})
                grantor = fields.get("grantor_name", "unknown")
                trust_type = fields.get("trust_type", "unknown")
                powers_count = len(fields.get("trustee_powers", []))
                logger.info(
                    f"    ✅ Complete — grantor={grantor}, "
                    f"type={trust_type}, powers={powers_count}"
                )
                success_count += 1
            else:
                logger.warning(f"    ❌ Failed — {result.get('error', 'unknown error')}")
                fail_count += 1

        except Exception as e:
            logger.error(f"    ❌ Error — {e}")
            fail_count += 1

        # Small delay between analyses to avoid rate limiting
        if i < len(docs):
            await asyncio.sleep(2)

    logger.info(f"\nMigration complete: {success_count} succeeded, {fail_count} failed.")


def main():
    parser = argparse.ArgumentParser(
        description="Batch analyze trust documents already in the vault"
    )
    parser.add_argument(
        "--trust-id", type=str, default=None,
        help="Process only this trust ID (optional)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be processed without triggering analysis"
    )
    args = parser.parse_args()

    asyncio.run(run_migration(
        trust_id_filter=args.trust_id,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    main()