#!/usr/bin/env python3
"""Batch 2: E2E test of 8 TrustOffice minutes templates against live API."""
import json, time, urllib.request, urllib.error

BASE = "https://api.trustoffice.app"
EMAIL = "test-scan@trustoffice.app"
PASSWORD = "TestScan2026!"
TRUST_ID = "trust_1925e3235cf5"

COMMON = {
    "meeting_date": "2026-01-15",
    "meeting_time": "10:00",
    "meeting_type": "unanimous_written_consent",
    "trustees_present": ["John Smith", "Jane Doe"],
    "minute_number": "2026-TEST-001",
}

def prop_data(**over):
    d = dict(grantor_name="Robert Anderson", property_description="One 2024 Honda Accord LX, VIN 1HGCV1F34RA123456",
             property_value=25000, property_identifier="VIN 1HGCV1F34RA123456",
             property_location="123 Main St, Wilmington, DE 19801", conveyance_date="2026-01-15")
    d.update(over); return d

TEMPLATES = {
    "real_estate_purchase": dict(
        agenda_items=["Review and approve purchase of real property"],
        key_decisions=["Approved purchase of the property described herein for $450,000 in cash"],
        additional_notes="Purchase funded from trust corpus.",
        property_address="456 Oak Avenue, Dover, DE 19901", purchase_price=450000,
        financing_source="Trust cash reserves"),
    "acceptance_of_property": dict(
        grantor_name="Robert Anderson", property_description="Lake house at 789 Shore Rd and associated furnishings",
        property_value=320000, property_identifier="Deed Book 1234 Page 56",
        property_location="789 Shore Road, Rehoboth Beach, DE 19971", conveyance_date="2026-01-15",
        add_to_schedule_a=True, schedule_a_category="Real Property",
        property_items=[{"name": "Lake house", "value": 300000}, {"name": "Furnishings", "value": 20000}]),
    "disposition_of_asset": dict(
        disposition_asset_id="SA-001", disposition_asset_description="Blue chip stock portfolio (AAPL, MSFT)",
        disposition_reason="Portfolio rebalancing per investment policy", disposition_date="2026-01-15",
        disposition_value=75000, disposition_recipient="Jane Doe (beneficiary)",
        disposition_notes="In-kind distribution to beneficiary.", update_schedule_a=True),
    "business_interest_acquisition": dict(
        agenda_items=["Consider acquisition of membership interest in Main Street LLC"],
        key_decisions=["Approved acquisition of 25% membership interest in Main Street LLC for $100,000"],
        additional_notes="Valuation supported by third-party appraisal."),
    "real_estate_lease": dict(
        agenda_items=["Approve lease of commercial unit"],
        key_decisions=["Approved 3-year lease of the commercial unit at market rate"],
        additional_notes="Tenant: Acme Services LLC."),
    "bill_of_sale": prop_data(),
    "assignment_of_personal_property": prop_data(),
    "general_assignment": dict(
        asset_description="Assorted personal property of the Grantor", asset_identifier="N/A - bulk assignment",
        asset_value=15000, conveyance_date="2026-01-15", grantor_name="Robert Anderson",
        additional_notes="Bulk assignment without warranty."),
}

def req(method, path, token=None, body=None, admin_key=None, raw=False):
    url = BASE + path
    data = None
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token: headers["Authorization"] = f"Bearer {token}"
    if admin_key: headers["X-Admin-API-Key"] = admin_key
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            content = resp.read()
            if raw:
                return resp.status, content
            return resp.status, json.loads(content or b"{}")
    except urllib.error.HTTPError as e:
        content = e.read()
        if raw: return e.code, content
        try: return e.code, json.loads(content or b"{}")
        except Exception: return e.code, {"detail": content.decode(errors="replace")[:300]}
    except Exception as e:
        return -1, {"detail": str(e)}

# login
st, out = req("POST", "/api/auth/login", body={"email": EMAIL, "password": PASSWORD})
assert st == 200, f"login failed {st} {out}"
TOKEN = out["token"]
print("login OK")

results = []
for tt, fields in TEMPLATES.items():
    rec = {"template_type": tt, "status": "PASS", "issues": [], "response_snippet": ""}
    td = {**fields, **COMMON}
    # 1) draft
    t0 = time.time()
    st, draft = req("POST", "/api/minutes/draft", TOKEN,
                    {"template_type": tt, "template_data": td, "trust_id": TRUST_ID})
    rec["draft_http_status"] = st
    if st != 200:
        # KNOWN LIVE BUG: decorator on /minutes/draft attached to _resolve_participants helper;
        # FastAPI treats body model as query param -> 422 for ALL templates.
        rec["issues"].append(f"draft HTTP {st}: {json.dumps(draft)[:250]}")
        if st == 422 and any(i.get("loc") == ["query", "request"] for i in (draft.get("detail") or []) if isinstance(i, dict)):
            rec["issues"].append("CONFIRMED BUG: /api/minutes/draft expects 'request' as QUERY param — route decorator misapplied to _resolve_participants helper; AI drafting broken for all templates")
        rec["status"] = "FAIL"
        body_txt = ""
    else:
        body_txt = draft.get("draft_body") or ""
        rec["draft_seconds"] = round(time.time() - t0, 1)
        if not body_txt.strip():
            rec["status"] = "FAIL"; rec["issues"].append("empty draft_body")
        else:
            import re
            placeholders = re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", body_txt)
            if placeholders:
                rec["issues"].append(f"unreplaced placeholders: {sorted(set(placeholders))[:8]}")
                rec["status"] = "FAIL"
            has_whereas = "WHEREAS" in body_txt.upper()
            has_resolved = "RESOLVED" in body_txt.upper() or "RESOLVE" in body_txt.upper()
            if not (has_whereas and has_resolved):
                rec["issues"].append(f"missing WHEREAS/RESOLVED structure (WHEREAS={has_whereas}, RESOLVED={has_resolved})")
                rec["status"] = "FAIL"
        rec["response_snippet"] = body_txt[:400].replace("\n", " ")
    # 2) create finalized minutes + PDF (decisions_text built from template fields since draft endpoint is broken)
    import re as _re
    decisions = "; ".join(f"{k}={v}" for k, v in td.items() if v)
    mid = None
    stc, created = req("POST", "/api/minutes", TOKEN, {
            "trust_id": TRUST_ID, "minutes_type": "general", "meeting_date": "2026-01-15",
            "participants_text": "John Smith, Jane Doe", "decisions_text": decisions,
            "template_type": tt, "template_data": td, "status": "finalized"})
    rec["create_http_status"] = stc
    if stc not in (200, 201):
        rec["status"] = "FAIL"
        rec["issues"].append(f"create HTTP {stc}: {json.dumps(created)[:300]}")
    else:
        mid = created.get("minutes_id") or created.get("id") or created.get("_id")
        rec["minutes_id"] = mid
        if not mid:
            rec["status"] = "FAIL"; rec["issues"].append(f"no minutes_id in create response: {list(created.keys())}")
    if mid:
        stp, pdf = req("GET", f"/api/minutes/{mid}/pdf", TOKEN, raw=True)
        rec["pdf_http_status"] = stp
        pdf_ok, pdf_len, note = False, 0, ""
        if stp == 200 and pdf[:1] == b"{":
            try:
                b64 = json.loads(pdf)["pdf_base64"]
                import base64
                decoded = base64.b64decode(b64)
                pdf_len, pdf_ok = len(decoded), decoded[:5] == b"%PDF-"
                if not pdf_ok: note = f"decoded does not start with %PDF: {decoded[:20]!r}"
            except Exception as ex:
                note = f"pdf_base64 JSON decode error: {ex}"
        elif stp == 200:
            pdf_len, pdf_ok = len(pdf), pdf[:5] == b"%PDF-"
            if not pdf_ok: note = f"raw response not PDF: {pdf[:60]!r}"
        else:
            note = f"HTTP {stp}: {pdf[:200]!r}"
        if not (pdf_ok and pdf_len > 500):
            rec["status"] = "FAIL"
            rec["issues"].append(f"PDF failed: HTTP {stp}, len {pdf_len}. {note}")
        else:
            rec["pdf_bytes"] = pdf_len
    results.append(rec)
    print(f"{tt}: {rec['status']} — {'; '.join(rec['issues']) or 'ok'}")

with open("/Users/socializerender/.openclaw/workspace/TrustOfficeApp/backend/test-results-batch2.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nSummary:", {r["template_type"]: r["status"] for r in results})
