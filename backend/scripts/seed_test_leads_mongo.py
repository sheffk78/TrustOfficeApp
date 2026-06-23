"""
Seed comprehensive test leads directly via MongoDB.
Run this on Railway: railway run python backend/scripts/seed_test_leads_mongo.py
"""
import asyncio
import uuid
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from database import db

async def seed():
    now = datetime.now(timezone.utc)
    
    # Clean up any previous test leads
    test_emails = [
        "sarah.new@example.com", "mike.blog@example.com", "emma.protect@example.com",
        "james.engaged@example.com", "lisa.hot@example.com", "robert.idle@example.com",
        "amanda.call@example.com", "carlos.call@example.com",
        "patricia.warm@example.com", "david.pricing@example.com",
        "manual.lead@example.com", "direct.traffic@example.com", "webinar.fan@example.com",
    ]
    result = await db.leads.delete_many({"email": {"$in": test_emails}})
    print(f"Cleaned up {result.deleted_count} previous test leads\n")
    
    async def create_lead(data):
        lead_id = f"test_{uuid.uuid4().hex[:12]}"
        doc = {
            "lead_id": lead_id,
            "email": data["email"],
            "name": data["name"],
            "source": data.get("source", "trustee-101-landing-page"),
            "lead_type": "email_capture",
            "stage": data.get("stage", "new"),
            "manual_stage_override": data.get("manual_stage_override", False),
            "lessons_watched": data.get("lessons_watched", 0),
            "subscription_status": data.get("subscription_status"),
            "last_login": data.get("last_login"),
            "booked_call": data.get("booked_call", False),
            "booked_call_at": data.get("booked_call_at"),
            "notes": data.get("notes", ""),
            "score": data.get("score", 50),
            "created_at": data.get("created_at", now.isoformat()),
            "updated_at": data.get("updated_at", now.isoformat()),
        }
        doc = {k: v for k, v in doc.items() if v is not None}
        await db.leads.insert_one(doc)
        return lead_id
    
    async def log_activity(lead_id, action_type, content, ts=None):
        await db.lead_activities.insert_one({
            "activity_id": f"act_{uuid.uuid4().hex[:12]}",
            "lead_id": lead_id,
            "action_type": action_type,
            "content": content,
            "created_at": (ts or now).isoformat(),
        })
    
    async def create_notif(lead_id, ntype, title, body, lead_name, lead_email):
        await db.notifications.insert_one({
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "type": ntype,
            "priority": "high" if ntype == "booked_call" else "normal",
            "title": title,
            "body": body,
            "lead_id": lead_id,
            "lead_email": lead_email,
            "lead_name": lead_name,
            "read": False,
            "created_at": now.isoformat(),
            "read_at": None,
        })
    
    # ==================== NEW LEADS ====================
    print("--- NEW LEADS ---")
    
    lid = await create_lead({
        "email": "sarah.new@example.com", "name": "Sarah Johnson",
        "source": "trustee-101-landing-page", "stage": "new",
        "lessons_watched": 0, "score": 50,
        "created_at": (now - timedelta(hours=2)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via trustee-101-landing-page", now - timedelta(hours=2))
    await create_notif(lid, "new_lead", "New lead: Sarah Johnson", "Source: trustee-101-landing-page · Score: 50", "Sarah Johnson", "sarah.new@example.com")
    print(f"  {lid}: Sarah Johnson — new, 2h ago")
    
    lid = await create_lead({
        "email": "mike.blog@example.com", "name": "Mike Chen",
        "source": "blog-subscribe", "stage": "new",
        "lessons_watched": 0, "score": 40,
        "created_at": (now - timedelta(days=1)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via blog-subscribe", now - timedelta(days=1))
    await create_notif(lid, "new_lead", "New lead: Mike Chen", "Source: blog-subscribe · Score: 40", "Mike Chen", "mike.blog@example.com")
    print(f"  {lid}: Mike Chen — new, blog subscriber 1d ago")
    
    lid = await create_lead({
        "email": "emma.protect@example.com", "name": "Emma Davis",
        "source": "liability-protection-kit", "stage": "new",
        "lessons_watched": 0, "score": 55,
        "created_at": (now - timedelta(hours=6)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via liability-protection-kit", now - timedelta(hours=6))
    await create_notif(lid, "new_lead", "New lead: Emma Davis", "Source: liability-protection-kit · Score: 55", "Emma Davis", "emma.protect@example.com")
    print(f"  {lid}: Emma Davis — new, liability kit 6h ago")
    
    # ==================== ENGAGED LEADS ====================
    print("\n--- ENGAGED LEADS ---")
    
    lid = await create_lead({
        "email": "james.engaged@example.com", "name": "James Wilson",
        "source": "trustee-101-landing-page", "stage": "engaged",
        "lessons_watched": 2, "score": 65,
        "last_login": (now - timedelta(days=1)).isoformat(),
        "created_at": (now - timedelta(days=5)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via trustee-101-landing-page", now - timedelta(days=5))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged (watched 2 lessons)", now - timedelta(days=3))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=5))
    print(f"  {lid}: James Wilson — engaged, 2 lessons, logged in yesterday")
    
    lid = await create_lead({
        "email": "lisa.hot@example.com", "name": "Lisa Thompson",
        "source": "commingling-checklist", "stage": "engaged",
        "lessons_watched": 5, "score": 82,
        "last_login": (now - timedelta(hours=3)).isoformat(),
        "created_at": (now - timedelta(days=10)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via commingling-checklist", now - timedelta(days=10))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged (watched 1 lesson)", now - timedelta(days=8))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=10))
    await log_activity(lid, "email", "Sent course nudge email", now - timedelta(days=6))
    print(f"  {lid}: Lisa Thompson — highly engaged, 5 lessons, logged in 3h ago")
    
    lid = await create_lead({
        "email": "robert.idle@example.com", "name": "Robert Garcia",
        "source": "distribution-guide", "stage": "engaged",
        "lessons_watched": 3, "score": 55,
        "last_login": (now - timedelta(days=5)).isoformat(),
        "created_at": (now - timedelta(days=14)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via distribution-guide", now - timedelta(days=14))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged (watched 3 lessons)", now - timedelta(days=10))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=14))
    print(f"  {lid}: Robert Garcia — engaged but idle, 3 lessons, 5d since login")
    
    # ==================== WARM LEADS ====================
    print("\n--- WARM LEADS ---")
    
    lid = await create_lead({
        "email": "patricia.warm@example.com", "name": "Patricia Martinez",
        "source": "new-trustee-guide", "stage": "warm",
        "lessons_watched": 0, "score": 35,
        "created_at": (now - timedelta(days=10)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via new-trustee-guide", now - timedelta(days=10))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=10))
    print(f"  {lid}: Patricia Martinez — warm, 10d no engagement")
    
    lid = await create_lead({
        "email": "david.pricing@example.com", "name": "David Kim",
        "source": "pricing-lead", "stage": "warm",
        "lessons_watched": 0, "score": 30,
        "created_at": (now - timedelta(days=21)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via pricing-lead", now - timedelta(days=21))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=21))
    print(f"  {lid}: David Kim — warm, pricing page, 21d no engagement")
    
    # ==================== BOOKED CALL LEADS ====================
    print("\n--- BOOKED CALL LEADS ---")
    
    lid = await create_lead({
        "email": "amanda.call@example.com", "name": "Amanda Foster",
        "source": "booked-call", "stage": "engaged",
        "lessons_watched": 1, "score": 85,
        "booked_call": True,
        "booked_call_at": (now - timedelta(days=1)).isoformat(),
        "last_login": (now - timedelta(days=1)).isoformat(),
        "created_at": (now - timedelta(days=3)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via booked-call", now - timedelta(days=3))
    await log_activity(lid, "booked_call", "Booked a TrustOffice Discovery Call", now - timedelta(days=1))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=3))
    await create_notif(lid, "booked_call", "Discovery call booked: Amanda Foster", "Booked a TrustOffice Discovery Call", "Amanda Foster", "amanda.call@example.com")
    print(f"  {lid}: Amanda Foster — booked call, 1 lesson, score 85")
    
    lid = await create_lead({
        "email": "carlos.call@example.com", "name": "Carlos Rivera",
        "source": "booked-call", "stage": "new",
        "lessons_watched": 0, "score": 70,
        "booked_call": True,
        "booked_call_at": (now - timedelta(hours=6)).isoformat(),
        "created_at": (now - timedelta(days=1)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via booked-call", now - timedelta(days=1))
    await log_activity(lid, "booked_call", "Booked a TrustOffice Discovery Call", now - timedelta(hours=6))
    await create_notif(lid, "booked_call", "Discovery call booked: Carlos Rivera", "Booked a TrustOffice Discovery Call", "Carlos Rivera", "carlos.call@example.com")
    print(f"  {lid}: Carlos Rivera — booked call, no lessons yet")
    
    # ==================== EDGE CASES ====================
    print("\n--- EDGE CASES ---")
    
    lid = await create_lead({
        "email": "manual.lead@example.com", "name": "Manual Entry",
        "source": "manual", "stage": "new",
        "lessons_watched": 0, "score": 40,
        "notes": "Referred by existing customer — follow up personally",
        "created_at": (now - timedelta(days=2)).isoformat(),
    })
    await log_activity(lid, "created", "Lead created manually by admin", now - timedelta(days=2))
    await log_activity(lid, "note_added", "Referred by existing customer — follow up personally", now - timedelta(days=2))
    print(f"  {lid}: Manual Entry — admin-created, has notes")
    
    lid = await create_lead({
        "email": "direct.traffic@example.com", "name": "Direct Visitor",
        "source": "direct", "stage": "new",
        "lessons_watched": 0, "score": 35,
        "created_at": (now - timedelta(days=3)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via direct", now - timedelta(days=3))
    print(f"  {lid}: Direct Visitor — unknown source, 3d old")
    
    lid = await create_lead({
        "email": "webinar.fan@example.com", "name": "Webinar Attendee",
        "source": "webinar-signup", "stage": "new",
        "lessons_watched": 0, "score": 45,
        "created_at": (now - timedelta(days=1)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via webinar-signup", now - timedelta(days=1))
    print(f"  {lid}: Webinar Attendee — webinar signup, 1d old")
    
    # ==================== SUMMARY ====================
    total = await db.leads.count_documents({})
    by_stage = {}
    for s in ["new", "engaged", "warm", "converted", "lost"]:
        by_stage[s] = await db.leads.count_documents({"stage": s})
    notif_count = await db.notifications.count_documents({})
    
    print(f"\n{'='*50}")
    print(f"SEED COMPLETE — {total} total leads, {notif_count} notifications")
    print(f"{'='*50}")
    for stage, count in by_stage.items():
        print(f"  {stage}: {count}")
    print(f"\nTest leads created. Check the Admin → Leads tab and the notification bell.")

if __name__ == "__main__":
    asyncio.run(seed())
