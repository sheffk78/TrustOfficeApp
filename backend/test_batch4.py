import json, time, urllib.request

BASE="https://api.trustoffice.app"
TOK=json.load(open('/tmp/login.json'))['token']
TRUST="trust_1925e3235cf5"

def call(method, path, body=None, raw=False):
    req=urllib.request.Request(BASE+path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization":"Bearer "+TOK,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            data=r.read()
            return r.status, (data if raw else (json.loads(data) if data else {}))
    except urllib.error.HTTPError as e:
        data=e.read()
        try: return e.code, json.loads(data)
        except Exception: return e.code, data.decode(errors='replace')[:500]

COMMON={"meeting_date":"2026-01-15","meeting_time":"10:00",
        "meeting_type":"unanimous_written_consent",
        "trustees_present":["John Smith","Jane Doe"],
        "minute_number":"2026-TEST-001"}

TEMPLATES={
 "trust_amendment":{"amendment_summary":"Amend Section 4.1 to permit investment in mutual funds","amended_provisions":["Section 4.1 Investment Powers"],"effective_date":"2026-02-01","additional_notes":"Approved unanimously"},
 "conflict_of_interest":{"trustee_name":"Jane Doe","conflict_description":"Jane Doe's spouse is employed by a proposed investment manager","conflict_nature":"financial","waiver_granted":True,"additional_notes":"Waived after full disclosure"},
 "emergency_ratification":{"emergency_description":"Emergency roof repair on trust property after storm damage","actions_taken":"Trustee contracted emergency repairs for $12,000","ratification_date":"2026-01-15","additional_notes":None},
 "power_of_attorney":{"attorney_name":"John Smith","scope":"Banking and tax matters","duration":"12 months","additional_notes":None},
 "trust_termination":{"termination_reason":"Trust purpose completed; all beneficiaries received corpus","final_distribution_plan":"Remainder distributed equally to the two named beneficiaries","termination_date":"2026-03-01","additional_notes":None},
 "change_of_situs":{"situsData":{"current_situs":"California","new_situs":"Nevada","effective_date":"2026-02-15","reasons":["Better trust laws","Tax advantages"]}},
 "fiscal_year_election":{"fiscal_year_end":"06-30","effective_date":"2026-01-01","additional_notes":"Aligns with business entity fiscal year"},
}

results=[]
for ttype, extra in TEMPLATES.items():
    rec={"template_type":ttype,"status":"PASS","issues":[],"response_snippet":""}
    td=dict(COMMON); td.update(extra)
    # draft
    st,d=call("POST","/api/minutes/draft",{"template_type":ttype,"template_data":td,"trust_id":TRUST})
    rec["draft_http"]=st
    txt=""
    if st!=200:
        rec["issues"].append(f"draft HTTP {st}: {json.dumps(d)[:300]}")
        rec["status"]="FAIL"
    else:
        s=json.dumps(d)
        # find drafted text wherever it lives
        for k in ("draft_text","minutes_text","text","content","draft"):
            v=d.get(k) if isinstance(d,dict) else None
            if isinstance(v,str) and v.strip(): txt=v; break
        if not txt and isinstance(d,dict):
            # search nested
            def find(o):
                if isinstance(o,str) and len(o)>200: return o
                if isinstance(o,dict):
                    for vv in o.values():
                        r=find(vv)
                        if r: return r
                if isinstance(o,list):
                    for vv in o:
                        r=find(vv)
                        if r: return r
                return None
            txt=find(d) or ""
        if not txt:
            rec["issues"].append("empty/null draft text")
            rec["status"]="FAIL"
        else:
            up=txt.upper()
            if "WHEREAS" not in up and "RESOLVED" not in up:
                rec["issues"].append("missing WHEREAS/RESOLVED structure")
            import re
            ph=re.findall(r"\{[a-zA-Z_]+\}",txt)
            if ph:
                rec["issues"].append(f"unreplaced placeholders {sorted(set(ph))[:6]}")
            if any(w in txt.lower() for w in ("error","failed to generate","an error occurred")):
                rec["issues"].append("error-like text in draft")
        rec["response_snippet"]=txt[:300] if txt else json.dumps(d)[:300]
    time.sleep(2)
    # finalize record
    body={"trust_id":TRUST,"minutes_type":ttype,"meeting_date":"2026-01-15",
          "participants_text":"John Smith, Jane Doe",
          "decisions_text":(rec["response_snippet"] or "Test decisions")[:2000],
          "template_type":ttype,"template_data":td}
    st2,d2=call("POST","/api/minutes",body)
    rec["create_http"]=st2
    mid=None
    if isinstance(d2,dict):
        mid=d2.get("minutes_id") or d2.get("id")
    if st2 not in (200,201) or not mid:
        rec["issues"].append(f"create HTTP {st2}: {json.dumps(d2)[:300]}")
        rec["status"]="FAIL"
    else:
        time.sleep(1)
        st3,pdf=call("GET",f"/api/minutes/{mid}/pdf",raw=True)
        rec["pdf_http"]=st3
        is_pdf = isinstance(pdf,bytes) and pdf[:5]==b"%PDF-"
        if st3!=200 or not is_pdf:
            snippet = pdf.decode(errors='replace')[:250] if isinstance(pdf,bytes) else str(pdf)[:250]
            rec["issues"].append(f"PDF HTTP {st3} valid_pdf={is_pdf}: {snippet}")
            rec["status"]="FAIL"
        else:
            rec["pdf_bytes"]=len(pdf)
    results.append(rec)
    print(ttype, rec["status"], rec["issues"])
    time.sleep(2)

json.dump(results,open('/Users/socializerender/.openclaw/workspace/TrustOfficeApp/backend/test-results-batch4.json','w'),indent=2)
print("DONE")
