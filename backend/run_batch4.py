import json,subprocess,time,os,re
BASE="https://api.trustoffice.app"
TOK=json.load(open('/tmp/login.json'))['token']
TRUST="trust_1925e3235cf5"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

def call(method,path,body=None):
    cmd=["curl","-s","-X",method,BASE+path,"-H",f"Authorization: Bearer {TOK}","-H",f"User-Agent: {UA}","-H","Content-Type: application/json","-w","\n%{http_code}"]
    if body is not None:
        cmd+=["--data-raw",json.dumps(body)]
    out=subprocess.run(cmd,capture_output=True,text=True).stdout
    body_s,_,code=out.rpartition("\n")
    try: return int(code), json.loads(body_s)
    except Exception: return int(code), str(body_s)[:400]

COMMON={"meeting_date":"2026-01-15","meeting_time":"10:00","meeting_type":"unanimous_written_consent","trustees_present":["John Smith","Jane Doe"],"minute_number":"2026-TEST-001"}
TEMPLATES={
 "trust_amendment":{"amendment_summary":"Amend Section 4.1 to permit investment in mutual funds","amended_provisions":["Section 4.1 Investment Powers"],"effective_date":"2026-02-01","additional_notes":"Approved unanimously"},
 "conflict_of_interest":{"trustee_name":"Jane Doe","conflict_description":"Jane Doe's spouse is employed by a proposed investment manager","conflict_nature":"financial","waiver_granted":True,"additional_notes":"Waived after full disclosure"},
 "emergency_ratification":{"emergency_description":"Emergency roof repair on trust property after storm damage","actions_taken":"Trustee contracted emergency repairs for $12,000","ratification_date":"2026-01-15","additional_notes":None},
 "power_of_attorney":{"attorney_name":"John Smith","scope":"Banking and tax matters","duration":"12 months","additional_notes":None},
 "trust_termination":{"termination_reason":"Trust purpose completed; all beneficiaries received corpus","final_distribution_plan":"Remainder distributed equally to the two named beneficiaries","termination_date":"2026-03-01","additional_notes":None},
 "change_of_situs":{"situsData":{"current_situs":"California","new_situs":"Nevada","effective_date":"2026-02-15","reasons":["Better trust laws","Tax advantages"]}},
 "fiscal_year_election":{"fiscal_year_end":"06-30","effective_date":"2026-01-01","additional_notes":None},
}
results=[]
for ttype,extra in TEMPLATES.items():
    rec={"template_type":ttype,"status":"PASS","issues":[],"response_snippet":""}
    td=dict(COMMON); td.update(extra)
    st,d=call("POST","/api/minutes/draft",{"template_type":ttype,"template_data":td,"trust_id":TRUST})
    rec["draft_http"]=st
    txt=""
    if st!=200:
        rec["issues"].append(f"draft HTTP {st}: {json.dumps(d)[:300]}"); rec["status"]="FAIL"
    else:
        def find(o):
            if isinstance(o,str) and len(o)>300: return o
            if isinstance(o,dict):
                for v in o.values():
                    r=find(v)
                    if r: return r
            if isinstance(o,list):
                for v in o:
                    r=find(v)
                    if r: return r
            return None
        for k in ("draft_text","minutes_text","text","content"):
            if isinstance(d,dict) and isinstance(d.get(k),str) and d[k].strip(): txt=d[k]; break
        if not txt and isinstance(d,dict): txt=find(d) or ""
        if not txt:
            rec["issues"].append("empty/null draft text"); rec["status"]="FAIL"
        else:
            up=txt.upper()
            if "WHEREAS" not in up and "RESOLVED" not in up: rec["issues"].append("missing WHEREAS/RESOLVED structure")
            ph=re.findall(r"\{[a-z_]+\}",txt)
            if ph: rec["issues"].append(f"unreplaced placeholders {sorted(set(ph))[:8]}")
        rec["response_snippet"]=txt[:300] if txt else json.dumps(d)[:300]
    time.sleep(1)
    body={"trust_id":TRUST,"minutes_type":ttype,"meeting_date":"2026-01-15","participants_text":"John Smith, Jane Doe","decisions_text":(txt or "Test decisions")[:2000],"template_type":ttype,"template_data":td}
    st2,d2=call("POST","/api/minutes",body)
    rec["create_http"]=st2
    mid=d2.get("minutes_id") or d2.get("id") if isinstance(d2,dict) else None
    if st2 not in (200,201) or not mid:
        rec["issues"].append(f"create HTTP {st2}: {json.dumps(d2)[:300]}"); rec["status"]="FAIL"
        rec["pdf_http"]=None
    else:
        time.sleep(1)
        code=subprocess.run(["curl","-s",f"{BASE}/api/minutes/{mid}/pdf","-H",f"Authorization: Bearer {TOK}","-H",f"User-Agent: {UA}","-o","/tmp/out_{t}.pdf".replace("{t}",ttype),"-w","%{http_code}"],capture_output=True,text=True).stdout
        p="/tmp/out_%s.pdf"%ttype
        head=open(p,"rb").read(5)
        ok = code=="200" and head==b"%PDF-"
        rec["pdf_http"]=code
        if not ok:
            snippet=open(p,"rb").read(250).decode(errors='replace')
            rec["issues"].append(f"PDF http={code} valid_pdf={head==b'%PDF-'}: {snippet}")
            rec["status"]="FAIL"
        else:
            rec["pdf_bytes"]=os.path.getsize(p)
    results.append(rec)
    print(ttype,rec["status"],"draft:",rec["draft_http"],"create:",rec.get("create_http"),"pdf:",rec.get("pdf_http"),rec["issues"],flush=True)
    time.sleep(1)
json.dump(results,open("test-results-batch4.json","w"),indent=2)
print("WROTE test-results-batch4.json")
