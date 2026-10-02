"""Phase 3a — one-page White-Label Governance Defense Summary (council #3).

GET /api/exports/defense-summary/{trust_id}        -> PDF (download inline)
GET /api/exports/defense-summary/{trust_id}/share  -> 7-day expiring share link
GET /api/exports/defense-summary/link/{token}      -> PDF via token (unauthenticated by token)

Advisor-gated ONLY for the white-label treatment; free/other tiers get a
watermarkedTrustOffice-branded copy (watermark control promise honored —
the FEATURE scales with tier, nothing free is invented).
"""
import io
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from database import db
from dependencies import get_current_user, is_white_label
from routers.orgs import _my_memberships

router = APIRouter(tags=["exports-defense-summary"])

NAVY = "#1B2A4A"
GOLD = "#B08A2E"


def _dates():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


async def _trust_for_user(trust_id: str, user: dict) -> dict:
    """Access: trust owner OR any member with an active org grant on it."""
    trust = await db.trusts.find_one({"trust_id": trust_id})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    if trust.get("user_id") == user.get("user_id"):
        return trust
    member_ids = [m["member_id"] for m in await _my_memberships(user) if m.get("status") == "active"]
    if member_ids:
        grant = await db.trust_grants.find_one({
            "trust_id": trust_id, "member_id": {"$in": member_ids}, "status": "active",
        })
        if grant:
            return trust
    raise HTTPException(status_code=403, detail={"code": "org_access_denied"})


async def _summary_data(trust_id: str) -> dict:
    today = _dates()
    # health
    snap = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id}, sort=[("created_at", -1)]
    )
    # minutes finalized vs pending (approximation of house status model)
    finalized = None
    try:
        finalized = await db.meeting_minutes.count_documents({"trust_id": trust_id, "status": "finalized"})
    except Exception:
        finalized = 0
    OPEN = ["draft", "pending_review", "under_review", "changes_requested"]
    pending = 0
    try:
        async for row in db.meeting_minutes.aggregate([
            {"$match": {"trust_id": trust_id}},
            {"$lookup": {"from": "minutes_approval_status", "localField": "minutes_id", "foreignField": "minutes_id", "as": "_ap"}},
            {"$addFields": {"_st": {"$ifNull": [{"$arrayElemAt": ["$_ap.current_status", 0]}, "$status"]}}},
            {"$match": {"_st": {"$in": OPEN}}},
            {"$count": "n"},
        ]):
            pending = row.get("n", 0)
    except Exception:
        # degrade to bare-status count (no approval-state collection present)
        try:
            pending = await db.meeting_minutes.count_documents({"trust_id": trust_id, "status": {"$in": OPEN}})
        except Exception:
            pending = 0
    distributions = 0
    try:
        distributions = await db.distributions.count_documents({"trust_id": trust_id})
    except Exception:
        distributions = 0
    upcoming = []
    async for t in db.governance_tasks.find(
        {"trust_id": trust_id, "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}], "due_date": {"$gte": today}},
        {"_id": 0, "task_type": 1, "due_date": 1, "description": 1},
    ).sort("due_date", 1).limit(5):
        upcoming.append(t)
    return {
        "health_score": snap.get("score") if snap else None,
        "health_chips": (snap or {}).get("breakdown") or None,
        "minutes_finalized": finalized or 0,
        "minutes_pending": pending,
        "distributions_logged": distributions,
        "upcoming": upcoming,
    }


def _build_pdf(trust: dict, data: dict, white_label: bool) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    accent = HexColor("#000000") if white_label else HexColor(NAVY)
    h1 = ParagraphStyle("h1", fontName="Times-Bold", fontSize=17, textColor=accent, spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName="Times-Bold", fontSize=12, textColor=accent, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", fontName="Times-Roman", fontSize=10.5, leading=15)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.6 * inch)
    story = [
        Paragraph("Governance Defense Summary", h1),
        Paragraph(f"{trust.get('name') or trust.get('trust_name') or 'Trust'} · as of {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
                  ParagraphStyle("sub", parent=body, textColor=HexColor("#444444"))),
        Spacer(1, 8),
    ]
    rows = [
        ["Governance health score", str(data["health_score"]) if data["health_score"] is not None else "Not yet scored"],
        ["Minutes finalized", str(data["minutes_finalized"])],
        ["Minutes pending approval", str(data["minutes_pending"])],
        ["Distributions on record", str(data["distributions_logged"])],
    ]
    if data["upcoming"]:
        rows.append(["Next deadlines", "; ".join(f"{t.get('task_type')} {str(t.get('due_date'))[:10]}" for t in data["upcoming"][:3])])
    table = Table([[Paragraph(k, body), Paragraph(v, body)] for k, v in rows], colWidths=[2.6 * inch, 3.6 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [Paragraph("Record of Governance", h2), table]
    platform_line = ("maintained in the TrustOffice governance platform" if not white_label
                     else "maintained in the firm's governance records system")
    story += [Spacer(1, 12),
              Paragraph(f"This summary compiles the trust's governance records — board-style minutes with "
                        f"owner approvals, distribution records, and scheduled reviews — as {platform_line}. "
                        "It is a point-in-time aid for review with counsel; it is not legal advice.", body)]
    if not white_label:
        story += [Spacer(1, 10), Paragraph("Prepared with TrustOffice · trustoffice.app",
                  ParagraphStyle("wm", parent=body, fontSize=8.5, textColor=HexColor(GOLD)))]
    doc.build(story)
    return buf.getvalue()


@router.get("/exports/defense-summary/{trust_id}")
async def defense_summary_pdf(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await _trust_for_user(trust_id, user)
    data = await _summary_data(trust_id)
    white = await is_white_label(user["user_id"])
    pdf = _build_pdf(trust, data, white)
    name = quote(f"defense-summary-{trust_id}.pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "no-store"},
    )


@router.post("/exports/defense-summary/{trust_id}/share")
async def defense_share_link(trust_id: str, user: dict = Depends(get_current_user)):
    """7-day expiring, unguessable share token (mirrors revoke-token rigor).
    One active token per trust+purpose; re-share replaces it."""
    await _trust_for_user(trust_id, user)
    token = f"dsum_{secrets.token_urlsafe(24)}"
    now = datetime.now(timezone.utc)
    await db.share_links.update_many(
        {"purpose": "defense_summary", "trust_id": trust_id, "revoked_at": {"$exists": False}},
        {"$set": {"revoked_at": now.isoformat()}},
    )
    await db.share_links.insert_one({
        "token": token, "purpose": "defense_summary", "trust_id": trust_id,
        "created_by": user["user_id"], "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
    })
    return {"token": token, "expires_at": (now + timedelta(days=7)).isoformat(),
            "url": f"/exports/defense-summary/link/{token}"}


@router.get("/exports/defense-summary/link/{token}")
async def defense_summary_by_token(token: str):
    link = await db.share_links.find_one({
        "token": token, "purpose": "defense_summary", "revoked_at": {"$exists": False},
    })
    if not link:
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    if link.get("expires_at"):
        exp = datetime.fromisoformat(str(link["expires_at"]).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(status_code=410, detail="This link has expired")
    trust = await db.trusts.find_one({"trust_id": link["trust_id"]}) or {}
    data = await _summary_data(link["trust_id"])
    # shared links are always white-label (advisor artifact travels)
    pdf = _build_pdf(trust, data, white_label=True)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="defense-summary.pdf"', "Cache-Control": "no-store"})


# ==================== 3b — BATCH CLIENT PACKET ====================

@router.post("/exports/client/{client_user_id}/packet")
async def client_packet(client_user_id: str, user: dict = Depends(get_current_user)):
    """One-click ZIP: for each trust owned by the client, the defense-summary
    PDF + a portfolio cover sheet (trust inventory + rollup). Zip in-request
    (defense summaries are one-page, tens of trusts = seconds) — no archive
    table dependency."""
    import zipfile as _zf
    import io as _io
    from routers.schedule_a import NAVY as _
    # access: caller owns the client's trusts OR holds org grants on >=1 of them
    client_trusts = []
    async for t in db.trusts.find({"user_id": client_user_id}, {"_id": 0, "trust_id": 1, "name": 1}):
        client_trusts.append(dict(t))
    if not client_trusts:
        raise HTTPException(status_code=404, detail="No trusts for that client")
    my_member_ids = [m["member_id"] for m in await _my_memberships(user) if m.get("status") == "active"]
    granted_ids = set()
    if my_member_ids:
        async for g in db.trust_grants.find(
            {"trust_id": {"$in": [t["trust_id"] for t in client_trusts]}, "member_id": {"$in": my_member_ids}, "status": "active"},
            {"_id": 0, "trust_id": 1},
        ):
            granted_ids.add(g["trust_id"])
    is_owner = any(t.get("user_id") == user.get("user_id") for t in client_trusts)
    allowed = [t for t in client_trusts if is_owner or t["trust_id"] in granted_ids]
    if not allowed:
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    white = await is_white_label(user["user_id"])
    zbuf = _io.BytesIO()
    with _zf.ZipFile(zbuf, "w", _zf.ZIP_DEFLATED) as z:
        rollup = []
        for t in allowed:
            data = await _summary_data(t["trust_id"])
            pdf = _build_pdf(t, data, white)
            z.writestr(f"{t['trust_id']}-defense-summary.pdf", pdf)
            rollup.append([t.get("name") or t.get("trust_name") or t["trust_id"], str(data["health_score"] if data["health_score"] is not None else "—")])
        # cover sheet
        cov = _io.BytesIO()
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        accent = HexColor("#000000") if white else HexColor(NAVY)
        doc = SimpleDocTemplate(cov, pagesize=letter, topMargin=0.7 * inch)
        story = [Paragraph("Client Governance Packet", ParagraphStyle("t", fontName="Times-Bold", fontSize=17, textColor=accent)),
                 Spacer(1, 6),
                 Paragraph(f"{len(allowed)} trust packet · generated {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
                           ParagraphStyle("s", fontName="Times-Roman", fontSize=10.5))]
        if rollup:
            tbl = Table([[Paragraph(a, ParagraphStyle("c1", fontName="Times-Roman", fontSize=10)),
                          Paragraph(b, ParagraphStyle("c2", fontName="Times-Roman", fontSize=10))] for a, b in rollup])
            tbl.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, HexColor("#CCCCCC"))]))
            story += [Spacer(1, 10), tbl]
        doc.build(story)
        z.writestr("00-cover.pdf", cov.getvalue())
    zbuf.seek(0)
    name = quote(f"client-packet-{client_user_id}.zip")
    return Response(content=zbuf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/exports/org/{org_id}/packet")
async def org_packet(org_id: str, user: dict = Depends(get_current_user)):
    """Whole-book packet for an org: every granted trust's defense summary +
    portfolio cover. Grant-scoped (only trusts the CALLER can see)."""
    import io as _io
    import zipfile as _zf
    org = await db.orgs.find_one({"org_id": org_id}, {"_id": 0, "org_id": 1, "name": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    from routers.org_queue import _granted_trusts
    tids, level_by_trust, _ = await _granted_trusts(org_id, user)
    if not tids:
        raise HTTPException(status_code=404, detail="No granted trusts in this org")
    white = await is_white_label(user["user_id"])
    zbuf = _io.BytesIO()
    rollup = []
    with _zf.ZipFile(zbuf, "w", _zf.ZIP_DEFLATED) as z:
        names = {}
        async for t in db.trusts.find({"trust_id": {"$in": tids}}, {"_id": 0, "trust_id": 1, "name": 1}):
            names[t["trust_id"]] = t
        for tid in tids:
            t = names.get(tid) or {"trust_id": tid}
            data = await _summary_data(tid)
            z.writestr(f"{tid}-defense-summary.pdf", _build_pdf(t, data, white))
            rollup.append([t.get("name") or tid, str(data["health_score"] if data["health_score"] is not None else "—")])
        cov = _io.BytesIO()
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        accent = HexColor("#000000") if white else HexColor(NAVY)
        doc = SimpleDocTemplate(cov, pagesize=letter, topMargin=0.7 * inch)
        story = [Paragraph(f"{org.get('name') or 'Organization'} — Governance Packet",
                            ParagraphStyle("t", fontName="Times-Bold", fontSize=17, textColor=accent)),
                 Spacer(1, 6),
                 Paragraph(f"{len(tids)} trusts · generated {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
                           ParagraphStyle("s", fontName="Times-Roman", fontSize=10.5))]
        if rollup:
            tbl = Table([[Paragraph(a, ParagraphStyle("c1", fontName="Times-Roman", fontSize=10)),
                          Paragraph(b, ParagraphStyle("c2", fontName="Times-Roman", fontSize=10))] for a, b in rollup])
            tbl.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, HexColor("#CCCCCC"))]))
            story += [Spacer(1, 10), tbl]
        doc.build(story)
        z.writestr("00-cover.pdf", cov.getvalue())
    zbuf.seek(0)
    fname = quote(f"{(org.get('name') or 'governance')[:24].replace(' ', '_')}-packet.zip")
    return Response(content=zbuf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"', "Cache-Control": "no-store"})
