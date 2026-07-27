"""
Beneficiary report service — PDF report generation for trust beneficiaries.

Phase 4 (Enhanced Features) of the TrustOffice plan.

Generates professional PDF beneficiary reports using ReportLab and stores
them in db.vault_documents with category "beneficiary_report".
"""
import io
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from database import db
from pdf_utils import NAVY, GRAY, LIGHT_GRAY, separator_line, create_doc_template


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


async def get_owned_trust(trust_id: str, user_id: str) -> Optional[dict]:
    """Fetch a trust only if owned by this user (mirrors meeting_service pattern)."""
    return await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )


async def _get_units_settings(trust_id: str, user_id: str) -> dict:
    """Get units settings for a trust (creates defaults if missing)."""
    settings = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
    )
    if not settings:
        settings = {
            "trust_id": trust_id,
            "user_id": user_id,
            "total_authorized_units": 100,
            "unit_label": "Certificate Unit",
            "allow_fractional": False,
            "created_at": _now(),
            "updated_at": None,
        }
        await db.trust_units_settings.insert_one(settings)
    return settings


async def _aggregate_beneficiaries(trust_id: str, user_id: str) -> tuple:
    """Aggregate beneficiaries from trust_unit_certificates.

    Returns (beneficiaries_list, total_issued, active_cert_count).
    Mirrors the dashboard logic in routers/beneficiaries.py.
    """
    certificates = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "user_id": user_id, "status": "active"},
        {"_id": 0},
    ).to_list(1000)

    holder_map: dict = {}
    for cert in certificates:
        holder_key = (
            cert["holder_name"],
            cert.get("holder_identifier") or "",
            cert.get("holder_type") or "individual",
        )
        if holder_key not in holder_map:
            holder_map[holder_key] = {
                "holder_name": cert["holder_name"],
                "holder_identifier": cert.get("holder_identifier"),
                "holder_type": cert.get("holder_type", "individual"),
                "email": cert.get("email"),
                "phone": cert.get("phone"),
                "total_units": 0,
                "certificate_count": 0,
            }
        holder_map[holder_key]["total_units"] += cert.get("units", 0)
        holder_map[holder_key]["certificate_count"] += 1

    beneficiaries = sorted(
        holder_map.values(), key=lambda h: h["total_units"], reverse=True
    )
    total_issued = sum(h["total_units"] for h in beneficiaries)
    return beneficiaries, total_issued, len(certificates)


def _build_pdf(
    trust: dict,
    beneficiaries: List[dict],
    class_beneficiaries: List[dict],
    total_authorized: int,
    total_issued: int,
    active_cert_count: int,
    unit_label: str,
) -> bytes:
    """Build the beneficiary report PDF and return raw bytes."""
    doc, buffer = create_doc_template()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        spaceAfter=4,
        textColor=NAVY,
        alignment=1,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=12,
        textColor=GRAY,
        alignment=1,
        fontName="Helvetica",
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=20,
        spaceAfter=8,
        textColor=NAVY,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=4,
        fontName="Helvetica",
        leading=12,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=GRAY,
        alignment=1,
        fontName="Helvetica-Oblique",
    )

    story = []
    generated_date = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # ---- Header ----
    trust_name = trust.get("name", "Unnamed Trust")
    trust_type = trust.get("trust_type", "N/A")
    jurisdiction = trust.get("jurisdiction", trust.get("state", "N/A"))

    story.append(Paragraph("BENEFICIARY REPORT", title_style))
    story.append(Paragraph(f"Generated {generated_date}", subtitle_style))
    story.append(separator_line())
    story.append(Spacer(1, 12))

    # Trust info table
    info_rows = [
        ["Trust Name:", trust_name],
        ["Trust Type:", str(trust_type).replace("_", " ").title()],
        ["Jurisdiction:", str(jurisdiction)],
        ["Date Generated:", generated_date],
    ]
    info_table = Table(info_rows, colWidths=[1.8 * inch, 4.7 * inch])
    info_table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(info_table)
    story.append(Spacer(1, 16))

    # ---- Executive Summary ----
    story.append(Paragraph("Executive Summary", section_style))
    remaining = total_authorized - total_issued
    summary_rows = [
        ["Total Authorized Units:", f"{total_authorized:,} {unit_label}s"],
        ["Total Issued Units:", f"{total_issued:,} {unit_label}s"],
        ["Remaining Units:", f"{remaining:,} {unit_label}s"],
        ["Active Certificates:", str(active_cert_count)],
        ["Beneficiaries:", str(len(beneficiaries))],
    ]
    summary_table = Table(summary_rows, colWidths=[2.2 * inch, 4.3 * inch])
    summary_table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(summary_table)
    story.append(Spacer(1, 16))

    # ---- Beneficiary Table ----
    if beneficiaries:
        story.append(Paragraph("Beneficiary Allocations", section_style))
        header = ["Name", "Email", "Allocation %", "Units Held", "Certificates"]
        rows = []
        for b in beneficiaries:
            pct = (
                f"{(b['total_units'] / total_authorized * 100):.2f}%"
                if total_authorized > 0
                else "0.00%"
            )
            rows.append([
                b["holder_name"],
                b.get("email") or "—",
                pct,
                f"{b['total_units']:,}",
                str(b["certificate_count"]),
            ])
        col_widths = [1.6 * inch, 1.8 * inch, 1.0 * inch, 1.0 * inch, 1.1 * inch]
        data = [header] + rows
        bt = Table(data, colWidths=col_widths, repeatRows=1)
        bt.setStyle(
            TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ])
        )
        story.append(bt)
    else:
        story.append(Paragraph(
            "No active beneficiary certificates found for this trust.",
            body_style,
        ))
    story.append(Spacer(1, 16))

    # ---- Class Beneficiaries ----
    if class_beneficiaries:
        story.append(Paragraph("Class Beneficiary Designations", section_style))
        cb_header = ["Class Type", "Description", "Percentage", "Notes"]
        cb_rows = []
        for cb in class_beneficiaries:
            cb_rows.append([
                cb.get("class_type_label", cb.get("class_type", "—")),
                cb.get("description") or "—",
                f"{cb.get('percentage', 0):.1f}%" if cb.get("percentage") else "—",
                (cb.get("notes") or "—")[:60],
            ])
        cb_widths = [1.5 * inch, 2.2 * inch, 1.0 * inch, 1.8 * inch]
        cb_data = [cb_header] + cb_rows
        cbt = Table(cb_data, colWidths=cb_widths, repeatRows=1)
        cbt.setStyle(
            TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ])
        )
        story.append(cbt)
        story.append(Spacer(1, 16))

    # ---- Footer ----
    story.append(Spacer(1, 20))
    story.append(separator_line())
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Generated by TrustOffice on {generated_date}",
        footer_style,
    ))
    story.append(Paragraph(
        f"{trust_name} – Beneficiary Report – Confidential",
        footer_style,
    ))

    doc.build(story)
    return buffer.getvalue()


async def generate_beneficiary_report(trust_id: str, user_id: str) -> dict:
    """Generate a professional PDF beneficiary report and store in vault_documents.

    Returns {report_id, doc_id, generated_at, trust_name, beneficiary_count}.
    Raises ValueError if trust not found.
    """
    trust = await get_owned_trust(trust_id, user_id)
    if not trust:
        raise ValueError("Trust not found")

    trust_name = trust.get("name", "Unnamed Trust")

    # Gather data
    settings = await _get_units_settings(trust_id, user_id)
    total_authorized = settings.get("total_authorized_units", 100)
    unit_label = settings.get("unit_label", "Certificate Unit")

    beneficiaries, total_issued, active_cert_count = await _aggregate_beneficiaries(
        trust_id, user_id
    )

    class_beneficiaries = await db.class_beneficiaries.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)

    # Build PDF
    pdf_bytes = _build_pdf(
        trust, beneficiaries, class_beneficiaries,
        total_authorized, total_issued, active_cert_count, unit_label,
    )

    # Store in vault_documents
    now = _now()
    report_id = _new_id("rpt")
    doc_id = _new_id("doc")
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    size_bytes = len(pdf_bytes)
    if size_bytes < 1024:
        size_display = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_display = f"{size_bytes / 1024:.1f} KB"
    else:
        size_display = f"{size_bytes / (1024 * 1024):.1f} MB"

    record = {
        "doc_id": doc_id,
        "report_id": report_id,
        "trust_id": trust_id,
        "user_id": user_id,
        "title": f"Beneficiary Report — {trust_name} — {date_str}",
        "category": "beneficiary_report",
        "category_label": "Beneficiary Report",
        "date": now[:10],
        "description": f"Auto-generated beneficiary report with {len(beneficiaries)} beneficiaries",
        "storage_provider": "trustoffice",
        "storage_url": None,
        "storage_path": None,
        "file_name": f"beneficiary_report_{trust_id}_{date_str}.pdf",
        "file_size": size_display,
        "file_size_bytes": size_bytes,
        "file_content_type": "application/pdf",
        "file_content": pdf_bytes,
        "tags": ["beneficiary_report", "auto_generated"],
        "expiration_date": None,
        "needs_renewal": False,
        "created_at": now,
        "updated_at": now,
    }
    await db.vault_documents.insert_one(record)

    return {
        "report_id": report_id,
        "doc_id": doc_id,
        "generated_at": now,
        "trust_name": trust_name,
        "beneficiary_count": len(beneficiaries),
    }


async def list_reports(trust_id: str, user_id: str) -> list:
    """List all beneficiary reports for a trust."""
    trust = await get_owned_trust(trust_id, user_id)
    if not trust:
        raise ValueError("Trust not found")

    docs = await db.vault_documents.find(
        {
            "trust_id": trust_id,
            "user_id": user_id,
            "category": "beneficiary_report",
        },
        {"_id": 0, "file_content": 0},
    ).sort("created_at", -1).to_list(100)

    trust_name = trust.get("name", "Unnamed Trust")
    results = []
    for d in docs:
        results.append({
            "report_id": d.get("report_id", d["doc_id"]),
            "doc_id": d["doc_id"],
            "generated_at": d.get("created_at", ""),
            "trust_name": trust_name,
            "beneficiary_count": d.get("description", "").split("with ")[-1].split(" ")[0]
                if "with" in (d.get("description") or "")
                else "0",
        })
    return results
