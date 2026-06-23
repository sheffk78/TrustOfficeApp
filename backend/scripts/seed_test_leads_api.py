"""
Seed comprehensive test leads via the API.
Creates leads at various stages, then updates their progress.
"""
import requests
import json
import sys

API = "https://api.trustoffice.app/api"
ADMIN_KEY = "to_admin_3Iksf_YmMpApyapMpr0ffZLke9cwqPJx9sh8dhZqqO0"
ADMIN_HEADERS = {"X-Admin-API-Key": ADMIN_KEY, "Content-Type": "application/json"}

# Login as admin to get JWT for leads router (which uses require_admin JWT auth)
login_resp = requests.post(f"{API}/auth/login", json={
    "email": "contact@trustoffice.app",
    "password": "TrustOffice2024!"
})
if not login_resp.ok:
    print(f"Login failed: {login_resp.status_code} {login_resp.text[:200]}")
    sys.exit(1)

JWT = login_resp.json().get("token")
JWT_HEADERS = {"Authorization": f"Bearer {JWT}", "Content-Type": "application/json"}

def capture_lead(name, email, source):
    """Create a lead via the public capture endpoint."""
    r = requests.post(f"{API}/admin/leads/capture", json={
        "name": name, "email": email, "source": source
    })
    data = r.json()
    print(f"  {'✓' if r.ok else '✗'} {name} ({email}) — {data.get('lead_id', 'ERROR: ' + str(data))}")
    return data.get("lead_id") if r.ok else None

def set_course_progress(lead_id, lessons):
    """Set course progress via admin JWT endpoint."""
    r = requests.post(f"{API}/admin/leads/{lead_id}/course-progress",
                      json={"lessons_watched": lessons},
                      headers=JWT_HEADERS)
    return r.ok

def add_note(lead_id, content, action_type="system"):
    """Add a note/activity to a lead."""
    r = requests.post(f"{API}/admin/leads/{lead_id}/notes", 
                      json={"content": content, "action_type": action_type},
                      headers=JWT_HEADERS)
    return r.ok

def get_lead(lead_id):
    """Get lead details."""
    r = requests.get(f"{API}/admin/leads/{lead_id}", headers=JWT_HEADERS)
    return r.json() if r.ok else None

print("=" * 60)
print("SEEDING TEST LEADS")
print("=" * 60)

# ==================== NEW LEADS ====================
print("\n--- NEW LEADS ---")
leads = {}

lid = capture_lead("Sarah Johnson", "sarah.new@example.com", "trustee-101-landing-page")
if lid: leads["sarah_new"] = lid

lid = capture_lead("Mike Chen", "mike.blog@example.com", "blog-subscribe")
if lid: leads["mike_blog"] = lid

lid = capture_lead("Emma Davis", "emma.protect@example.com", "liability-protection-kit")
if lid: leads["emma_protect"] = lid

# ==================== ENGAGED LEADS ====================
print("\n--- ENGAGED LEADS ---")

lid = capture_lead("James Wilson", "james.engaged@example.com", "trustee-101-landing-page")
if lid:
    leads["james_engaged"] = lid
    ok = set_course_progress(lid, 2)
    print(f"    Course progress (2): {'✓' if ok else '✗'}")

lid = capture_lead("Lisa Thompson", "lisa.hot@example.com", "commingling-checklist")
if lid:
    leads["lisa_hot"] = lid
    ok = set_course_progress(lid, 5)
    print(f"    Course progress (5): {'✓' if ok else '✗'}")

lid = capture_lead("Robert Garcia", "robert.idle@example.com", "distribution-guide")
if lid:
    leads["robert_idle"] = lid
    ok = set_course_progress(lid, 3)
    print(f"    Course progress (3): {'✓' if ok else '✗'}")

# ==================== BOOKED CALL LEADS ====================
print("\n--- BOOKED CALL LEADS ---")

lid = capture_lead("Amanda Foster", "amanda.call@example.com", "booked-call")
if lid:
    leads["amanda_call"] = lid
    ok = set_course_progress(lid, 1)
    print(f"    Course progress (1): {'✓' if ok else '✗'}")

lid = capture_lead("Carlos Rivera", "carlos.call@example.com", "booked-call")
if lid: leads["carlos_call"] = lid

# ==================== WARM LEADS ====================
print("\n--- WARM LEADS ---")

lid = capture_lead("Patricia Martinez", "patricia.warm@example.com", "new-trustee-guide")
if lid: leads["patricia_warm"] = lid

lid = capture_lead("David Kim", "david.pricing@example.com", "pricing-lead")
if lid: leads["david_pricing"] = lid

# ==================== EDGE CASES ====================
print("\n--- EDGE CASES ---")

lid = capture_lead("Manual Entry", "manual.lead@example.com", "manual")
if lid:
    leads["manual_lead"] = lid
    add_note(lid, "Referred by existing customer — follow up personally", "manual")

lid = capture_lead("Direct Visitor", "direct.traffic@example.com", "direct")
if lid: leads["direct_visitor"] = lid

lid = capture_lead("Webinar Attendee", "webinar.fan@example.com", "webinar-signup")
if lid: leads["webinar_fan"] = lid

# ==================== VERIFICATION ====================
print("\n" + "=" * 60)
print("VERIFYING LEADS")
print("=" * 60)

for key, lid in leads.items():
    lead = get_lead(lid)
    if lead:
        print(f"\n{key}:")
        print(f"  Name: {lead.get('name')}")
        print(f"  Stage: {lead.get('stage')} ({lead.get('stage_label')})")
        print(f"  Score: {lead.get('score')}")
        print(f"  Source: {lead.get('source')}")
        print(f"  Lessons: {lead.get('lessons_watched')}")
        print(f"  Booked call: {lead.get('booked_call')}")
        print(f"  Next action: {lead.get('next_action')}")
        if lead.get('score_breakdown'):
            sb = lead['score_breakdown']
            print(f"  Score breakdown:")
            for k, v in sb.items():
                print(f"    {k}: {v['score']}/{v['max']} — {v['detail']}")
        print(f"  Activities: {len(lead.get('activities', []))}")
    else:
        print(f"\n{key}: FAILED to retrieve")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
r = requests.get(f"{API}/admin/leads/analytics", headers=JWT_HEADERS)
if r.ok:
    data = r.json()
    print(f"Total leads: {data.get('total_leads')}")
    print(f"Funnel: {data.get('funnel')}")
else:
    print(f"Analytics endpoint: {r.status_code} — {r.text[:200]}")

print("\nDone! Check the Admin → Leads tab and the notification bell.")
