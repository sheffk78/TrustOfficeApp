# Audit Defense PDF Export — court-ready separation evidence report
import io
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors

from database import db
from dependencies import get_current_user

router = APIRouter(tags=["audit-defense"])

NAVY = colors.HexColor('#010079')
GOLD = colors.HexColor('#d5ad36')
GRAY = colors.HexColor('#666666')
LIGHT_GRAY = colors.HexColor('#f0f0f0')
RED = colors.HexColor('#dc2626')
AMBER = colors.HexColor('#d97706')
GREEN = colors.HexColor('#16a34a')


def build_styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('AuditTitle', parent=base['Heading1'], fontSize=20, spaceAfter=4,
                                textColor=NAVY, alignment=1, fontName='Helvetica-Bold'),
        'subtitle': ParagraphStyle('AuditSubtitle', parent=base['Normal'], fontSize=10, spaceAfter=12,
                                   textColor=GRAY, alignment=1, fontName='Helvetica'),
        'section': ParagraphStyle('SectionTitle', parent=base['Heading2'], fontSize=13, spaceBefore=20,
                                  spaceAfter=8, textColor=NAVY, fontName='Helvetica-Bold'),
        'subsection': ParagraphStyle('SubSection', parent=base['Heading3'], fontSize=11, spaceBefore=12,
                                     spaceAfter=4, textColor=NAVY, fontName='Helvetica-Bold'),
        'body': ParagraphStyle('BodyText', parent=base['Normal'], fontSize=9, spaceAfter=4,
                               fontName='Helvetica', leading=12),
        'small': ParagraphStyle('SmallText', parent=base['Normal'], fontSize=8, textColor=GRAY,
                                fontName='Helvetica', leading=10),
        'label': ParagraphStyle('Label', parent=base['Normal'], fontSize=9, fontName='Helvetica-Bold',
                                textColor=NAVY),
    }


def separator_line():
    t = Table([[""]], colWidths=[6.5 * inch], rowHeights=[1])
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 1, NAVY)]))
    return t


def info_table(rows, label_width=1.8 * inch, value_width=4.7 * inch):
    t = Table(rows, colWidths=[label_width, value_width])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), NAVY),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def data_table(header, rows, col_widths=None):
    data = [header] + rows
    if not col_widths:
        col_widths = [6.5 * inch / len(header)] * len(header)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
    ]
    t.setStyle(TableStyle(style))
    return t


@router.get("/exports/audit-defense/{trust_id}")
async def export_audit_defense_pdf(trust_id: str, days: int = 365, user: dict = Depends(get_current_user)):
    """Generate a court-ready Audit Defense PDF for structural separation evidence"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc)

    # Fetch all data in parallel
    entities = await db.entities.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    ).to_list(100)

    relationships = await db.entity_relationships.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    ).to_list(100)

    txns = await db.transactions.find(
        {"trust_id": trust_id, "user_id": user["user_id"], "date": {"$gte": cutoff}}, {"_id": 0}
    ).sort("date", -1).to_list(10000)

    all_alerts = await db.separation_alerts.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)

    health_snapshots = await db.health_score_snapshots.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    ).sort("calculated_at", -1).to_list(12)

    minutes = await db.minutes_records.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    ).sort("meeting_date", -1).to_list(50)

    distributions = await db.distribution_records.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    ).sort("date", -1).to_list(100)

    comp_payments = await db.compensation_payments.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    ).sort("date", -1).to_list(100)

    # Build entity map
    entity_map = {e["entity_id"]: e for e in entities}

    # Styles
    S = build_styles()
    story = []

    # ==================== COVER / HEADER ====================
    story.append(Paragraph("AUDIT DEFENSE REPORT", S['title']))
    story.append(Paragraph("Structural Separation & Governance Evidence", S['subtitle']))
    story.append(Spacer(1, 6))

    trust_name = trust.get("name", "Trust")
    report_date = now.strftime("%B %d, %Y")
    period_start = cutoff
    period_end = now.strftime("%Y-%m-%d")

    story.append(info_table([
        ["Trust:", trust_name],
        ["Report Date:", report_date],
        ["Period Covered:", f"{period_start} to {period_end}"],
        ["Entities:", str(len(entities))],
        ["Transactions:", str(len(txns))],
        ["Active Alerts:", str(sum(1 for a in all_alerts if a.get('status') == 'active'))],
    ]))
    story.append(Spacer(1, 8))
    story.append(separator_line())

    # ==================== 1. ENTITY STRUCTURE ====================
    story.append(Paragraph("1. ENTITY STRUCTURE", S['section']))
    story.append(Paragraph(
        "The following entities comprise the trust governance structure. Each entity is a separately managed legal vehicle.",
        S['body']))

    if entities:
        header = ["Entity Name", "Type", "EIN", "Governing Law", "Formation Date"]
        rows = []
        for e in entities:
            rows.append([
                e.get("name", ""),
                e.get("entity_type", ""),
                e.get("ein", "N/A") or "N/A",
                e.get("governing_law", "N/A") or "N/A",
                (e.get("formation_date") or "N/A")[:10],
            ])
        story.append(data_table(header, rows, [2 * inch, 1.2 * inch, 1 * inch, 1 * inch, 1.3 * inch]))
    else:
        story.append(Paragraph("No entities configured.", S['small']))

    if relationships:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Entity Relationships", S['subsection']))
        header = ["Parent Entity", "Relationship", "Child Entity", "Ownership"]
        rows = []
        for r in relationships:
            parent = entity_map.get(r.get("parent_entity_id"), {}).get("name", "Unknown")
            child = entity_map.get(r.get("child_entity_id"), {}).get("name", "Unknown")
            pct = f"{r['ownership_percentage']}%" if r.get("ownership_percentage") else "N/A"
            rows.append([parent, r.get("relationship_type", "").replace("_", " ").title(), child, pct])
        story.append(data_table(header, rows, [2 * inch, 1.5 * inch, 2 * inch, 1 * inch]))

    # ==================== 2. PER-ENTITY TRANSACTION SUMMARY ====================
    story.append(PageBreak())
    story.append(Paragraph("2. TRANSACTION SUMMARY BY ENTITY", S['section']))
    story.append(Paragraph(
        "All money movement logged during the reporting period, classified by governance category.",
        S['body']))

    for entity in entities:
        eid = entity["entity_id"]
        entity_txns = [t for t in txns if t["entity_id"] == eid]
        if not entity_txns:
            continue

        story.append(Paragraph(f"{entity['name']} ({entity.get('entity_type', '')})", S['subsection']))

        total_in = sum(t["amount"] for t in entity_txns if t.get("direction") == "inflow")
        total_out = sum(t["amount"] for t in entity_txns if t.get("direction") == "outflow")

        story.append(info_table([
            ["Total Inflows:", f"${total_in:,.2f}"],
            ["Total Outflows:", f"${total_out:,.2f}"],
            ["Net Flow:", f"${total_in - total_out:,.2f}"],
            ["Transactions:", str(len(entity_txns))],
        ], 1.5 * inch, 2 * inch))
        story.append(Spacer(1, 4))

        # By classification breakdown
        by_class = {}
        for t in entity_txns:
            cls = t.get("governance_classification", "Other")
            by_class.setdefault(cls, {"in": 0, "out": 0, "count": 0})
            if t.get("direction") == "inflow":
                by_class[cls]["in"] += t["amount"]
            else:
                by_class[cls]["out"] += t["amount"]
            by_class[cls]["count"] += 1

        header = ["Classification", "Inflows", "Outflows", "Count"]
        rows = [[cls, f"${v['in']:,.2f}", f"${v['out']:,.2f}", str(v['count'])]
                for cls, v in sorted(by_class.items())]
        if rows:
            story.append(data_table(header, rows, [2.5 * inch, 1.5 * inch, 1.5 * inch, 1 * inch]))
        story.append(Spacer(1, 8))

    # ==================== 3. INTER-ENTITY TRANSFER LOG ====================
    inter_txns = [t for t in txns if t.get("governance_classification") == "Inter-Entity Transfer"]
    if inter_txns:
        story.append(Paragraph("3. INTER-ENTITY TRANSFER LOG", S['section']))
        story.append(Paragraph(
            "All transfers between entities within the trust structure. Each transfer should be supported by a governance action.",
            S['body']))

        header = ["Date", "From Entity", "To", "Amount", "Memo"]
        rows = []
        for t in inter_txns:
            ename = entity_map.get(t["entity_id"], {}).get("name", "")
            rows.append([
                t.get("date", "")[:10],
                ename,
                t.get("destination_account", ""),
                f"${t['amount']:,.2f}",
                (t.get("purpose_memo", "") or "")[:40],
            ])
        story.append(data_table(header, rows, [1 * inch, 1.5 * inch, 1.5 * inch, 1 * inch, 1.5 * inch]))

    # ==================== 4. SEPARATION ALERTS ====================
    story.append(PageBreak())
    story.append(Paragraph("4. SEPARATION ALERTS & RESOLUTIONS", S['section']))

    active_alerts = [a for a in all_alerts if a.get("status") == "active"]
    resolved_alerts = [a for a in all_alerts if a.get("status") == "resolved"]

    story.append(Paragraph(f"Active Alerts: {len(active_alerts)} | Resolved Alerts: {len(resolved_alerts)}", S['body']))
    story.append(Spacer(1, 4))

    if active_alerts:
        story.append(Paragraph("Active Alerts (Unresolved)", S['subsection']))
        header = ["Severity", "Type", "Description", "Entity", "Created"]
        rows = []
        for a in active_alerts[:50]:
            ename = entity_map.get(a.get("entity_id"), {}).get("name", "")
            rows.append([
                a.get("severity", "").upper(),
                a.get("title", ""),
                (a.get("description", "") or "")[:50],
                ename,
                (a.get("created_at", "") or "")[:10],
            ])
        story.append(data_table(header, rows, [0.7 * inch, 1.8 * inch, 1.8 * inch, 1.2 * inch, 1 * inch]))
        story.append(Spacer(1, 8))

    if resolved_alerts:
        story.append(Paragraph("Resolved Alerts (Audit Trail)", S['subsection']))
        header = ["Type", "Resolution", "Note", "Resolved"]
        rows = []
        for a in resolved_alerts[:50]:
            rows.append([
                a.get("title", ""),
                (a.get("resolution_type", "") or "").replace("_", " ").title(),
                (a.get("resolution_note", "") or "")[:50],
                (a.get("resolved_at", "") or "")[:10],
            ])
        story.append(data_table(header, rows, [2 * inch, 1.2 * inch, 2.3 * inch, 1 * inch]))

    if not all_alerts:
        story.append(Paragraph("No separation alerts have been generated for this trust.", S['body']))

    # ==================== 5. GOVERNANCE ACTIONS ====================
    story.append(PageBreak())
    story.append(Paragraph("5. LINKED GOVERNANCE ACTIONS", S['section']))

    # Minutes
    if minutes:
        story.append(Paragraph("Minutes Records", S['subsection']))
        header = ["Date", "Type", "Participants", "Created"]
        rows = []
        for m in minutes[:30]:
            rows.append([
                (m.get("meeting_date", "") or "")[:10],
                (m.get("minutes_type", "") or "").replace("_", " ").title(),
                (m.get("participants_text", "") or "")[:40],
                (m.get("created_at", "") or "")[:10],
            ])
        story.append(data_table(header, rows, [1 * inch, 1.8 * inch, 2.5 * inch, 1.2 * inch]))
        story.append(Spacer(1, 8))

    # Distributions
    if distributions:
        story.append(Paragraph("Distribution Authorizations", S['subsection']))
        header = ["Date", "Beneficiary", "Amount", "Classification", "Approved"]
        rows = []
        for d in distributions[:30]:
            rows.append([
                (d.get("date", "") or "")[:10],
                (d.get("beneficiary_name", "") or "")[:20],
                f"${d.get('amount', 0):,.2f}",
                (d.get("purpose_classification", "") or ""),
                "Yes" if d.get("approved_at") else "Pending",
            ])
        story.append(data_table(header, rows, [1 * inch, 1.5 * inch, 1 * inch, 1.8 * inch, 1.2 * inch]))
        story.append(Spacer(1, 8))

    # Compensation
    if comp_payments:
        story.append(Paragraph("Compensation Payments", S['subsection']))
        header = ["Date", "Recipient", "Amount", "Type", "Minutes Linked"]
        rows = []
        for p in comp_payments[:30]:
            rows.append([
                (p.get("date", "") or "")[:10],
                (p.get("recipient_name", "") or p.get("payee", "") or "")[:20],
                f"${p.get('amount', 0):,.2f}",
                (p.get("payment_type", "") or ""),
                "Yes" if p.get("minutes_record_id") else "No",
            ])
        story.append(data_table(header, rows, [1 * inch, 1.5 * inch, 1 * inch, 1.5 * inch, 1.5 * inch]))

    if not minutes and not distributions and not comp_payments:
        story.append(Paragraph("No governance actions recorded for this trust.", S['body']))

    # ==================== 6. GOVERNANCE HEALTH SCORE HISTORY ====================
    if health_snapshots:
        story.append(Paragraph("6. GOVERNANCE HEALTH SCORE HISTORY", S['section']))
        header = ["Date", "Score", "Status"]
        rows = []
        for h in health_snapshots:
            score = h.get("score_value", 0)
            color_label = h.get("color", "red").upper()
            rows.append([
                (h.get("calculated_at", "") or "")[:10],
                f"{score}/100",
                color_label,
            ])
        story.append(data_table(header, rows, [2.5 * inch, 2 * inch, 2 * inch]))

    # ==================== FOOTER / CERTIFICATION ====================
    story.append(Spacer(1, 24))
    story.append(separator_line())
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"This report was generated by TrustOffice on {report_date}. "
        "It represents a complete record of structural separation governance maintained "
        "through the TrustOffice platform. All transaction classifications, alert resolutions, "
        "and governance actions are preserved as immutable audit records.",
        S['small']))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "CONFIDENTIAL — Prepared for trustee use and legal counsel. "
        "This document may be presented as evidence of fiduciary competence in court proceedings or IRS audit responses.",
        ParagraphStyle('Disclaimer', parent=S['small'], fontName='Helvetica-Bold', textColor=NAVY)))

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    doc.build(story)
    buffer.seek(0)

    filename = f"audit_defense_{trust_id}_{now.strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/audit-logs")
async def get_user_audit_logs(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """Fetch audit log entries for the authenticated user.
    
    Returns security and governance audit events (logins, password changes,
    trust profile edits, vault actions, etc.) for the audit trail page.
    """
    cursor = db.audit_logs.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("timestamp", -1).skip(offset).limit(min(limit, 200))
    
    logs = await cursor.to_list(length=min(limit, 200))
    return {"audit_logs": logs}
