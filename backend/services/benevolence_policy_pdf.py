from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from pdf_utils import (
    NAVY, GRAY, create_doc_template, build_styles,
    separator_line, info_table, data_table, signature_block,
)


async def generate_policy_pdf(version: dict, trust: dict, show_watermark: bool) -> bytes:
    """Generate a styled PDF of a benevolence policy version.

    Reuses the shared pdf_utils helpers (create_doc_template, build_styles,
    data_table, separator_line, signature_block) — same pattern as
    beneficiary_report_service.py and the inline benevolence report.
    """
    doc, buffer = create_doc_template()
    styles = build_styles()
    s = styles  # shorthand

    story = []

    # Title
    story.append(Paragraph("BENEVOLENCE POLICY", s["title"]))
    story.append(
        Paragraph(
            f"Trust: {trust.get('name', 'N/A')}  |  "
            f"Version {version['version_label']}  |  "
            f"Status: {version['status'].title()}",
            s["subtitle"],
        )
    )
    story.append(separator_line())
    story.append(Spacer(1, 12))

    # Section 1: Charitable Class & Purpose
    story.append(Paragraph("Charitable Class & Purpose", s["section"]))
    story.append(Paragraph(f"Class: {version.get('charitable_class', 'Not specified')}", s["body"]))
    if version.get("charitable_class_description"):
        story.append(Paragraph(f"Description: {version['charitable_class_description']}", s["body"]))
    story.append(Spacer(1, 8))

    # Section 2: Eligibility Criteria
    story.append(Paragraph("Eligibility Criteria", s["section"]))
    if version.get("eligibility_criteria"):
        for c in version["eligibility_criteria"]:
            req = "Required" if c.get("is_required") else "Preferred"
            story.append(Paragraph(f"{c.get('criterion', '')} ({req})", s["body"]))
    else:
        story.append(Paragraph("No eligibility criteria defined.", s["body"]))
    story.append(Spacer(1, 8))

    # Section 3: Allowable Types of Assistance
    story.append(Paragraph("Allowable Types of Assistance", s["section"]))
    if version.get("assistance_types"):
        at_rows = [["Type", "Label", "Status", "Per-Recipient Limit"]]
        for at in version["assistance_types"]:
            status_label = "Allowed" if at.get("is_allowed") else "Excluded"
            if at.get("per_recipient_limit"):
                limit = (
                    f"${at['per_recipient_limit']:,.2f} / "
                    f"{at.get('per_recipient_period', 'N/A')}"
                )
            else:
                limit = "No limit"
            at_rows.append(
                [at.get("purpose", ""), at.get("label", ""), status_label, limit]
            )
        story.append(
            data_table(at_rows[0], at_rows[1:], col_widths=[0.8 * 100, 1.2 * 100, 0.7 * 100, 1 * 100])
        )
    else:
        story.append(Paragraph("No assistance types defined.", s["body"]))
    story.append(Spacer(1, 8))

    # Section 4: Per-Recipient Limits
    story.append(Paragraph("Per-Recipient Limits", s["section"]))
    global_limit = version.get("per_recipient_annual_limit")
    if global_limit:
        story.append(Paragraph(f"Global annual limit per recipient: ${global_limit:,.2f}", s["body"]))
    else:
        story.append(Paragraph("No global per-recipient annual limit.", s["body"]))

    per_type_limits = [at for at in (version.get("assistance_types") or []) if at.get("per_recipient_limit")]
    if per_type_limits:
        story.append(Paragraph("Per-type limits:", s["body"]))
        for at in per_type_limits:
            story.append(
                Paragraph(
                    f"  {at.get('purpose', '')}: ${at['per_recipient_limit']:,.2f} per "
                    f"{at.get('per_recipient_period', 'N/A')}",
                    s["body"],
                )
            )
    story.append(Spacer(1, 8))

    # Section 5: Approval Process
    story.append(Paragraph("Approval Process", s["section"]))
    story.append(Paragraph(version.get("approval_process", "Not specified."), s["body"]))
    if version.get("approval_threshold"):
        story.append(Paragraph(f"Single-approver threshold: ${version['approval_threshold']:,.2f}", s["body"]))
    story.append(Spacer(1, 8))

    # Section 6: Committee Members
    story.append(Paragraph("Committee Members", s["section"]))
    if version.get("committee_members"):
        cm_rows = [["Name", "Role", "Email"]]
        for cm in version["committee_members"]:
            cm_rows.append([cm.get("name", ""), cm.get("role", ""), cm.get("email", "")])
        story.append(data_table(cm_rows[0], cm_rows[1:], col_widths=[1.5 * 100, 0.8 * 100, 1.5 * 100]))
    else:
        story.append(Paragraph("No committee members defined.", s["body"]))
    story.append(Spacer(1, 8))

    # Section 7: Documentation Requirements
    story.append(Paragraph("Documentation Requirements", s["section"]))
    if version.get("documentation_requirements"):
        for dr in version["documentation_requirements"]:
            req = "Required" if dr.get("is_required") else "Optional"
            story.append(Paragraph(f"[{req}] {dr.get('item', '')}", s["body"]))
    else:
        story.append(Paragraph("No documentation requirements defined.", s["body"]))
    story.append(Spacer(1, 8))

    # Section 8: Gift Prohibition
    story.append(Paragraph("Designated Gift Prohibition", s["section"]))
    story.append(Paragraph(version.get("designated_gift_prohibition", "Not specified."), s["body"]))
    story.append(Spacer(1, 8))

    # Section 9: Employee Benevolence Tax Note
    story.append(Paragraph("Employee Benevolence (IRC &#167;102 / &#167;139)", s["section"]))
    story.append(Paragraph(version.get("employee_benevolence_note", "Not specified."), s["body"]))
    story.append(Spacer(1, 8))

    # Section 10: Board Approval
    story.append(Paragraph("Board Approval", s["section"]))
    if version.get("board_approval_date"):
        story.append(Paragraph(f"Date: {version['board_approval_date']}", s["body"]))
    if version.get("board_approval_reference"):
        story.append(Paragraph(f"Reference: {version['board_approval_reference']}", s["body"]))
    else:
        story.append(Paragraph("Board approval: Not yet recorded.", s["body"]))

    # Signature block
    story.append(Spacer(1, 12))
    # Shared helper expects a list of signatories and the styles dictionary.
    story.extend(signature_block([trust.get("name", "")], s))

    # Watermark (soft-gate indicator)
    if show_watermark:
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "NOTICE: This document is provided for informational purposes only. "
                "It does not constitute legal or tax advice.",
                ParagraphStyle(
                    "Watermark",
                    parent=s["body"],
                    textColor=colors.HexColor("#999999"),
                    fontSize=8,
                    alignment=1,
                ),
            )
        )

    doc.build(story)
    buffer.seek(0)
    return buffer.read()