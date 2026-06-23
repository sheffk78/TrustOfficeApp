"""
Seed comprehensive test leads across all stages and scenarios.
Creates leads at various levels of interest, course progress, and engagement.
"""
import asyncio
import uuid
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from database import db

API_BASE = "https://api.trustoffice.app"
ADMIN_KEY = "to_admin_3Iksf_YmMpApyapMpr0ffZLke9cwqPJx9sh8dhZqqO0"

async def create_lead(lead_data):
    """Insert a lead directly into MongoDB with full control over timestamps."""
    lead_id = f"lead_{uuid.uuid4().hex[:12]}"
    doc = {
        "lead_id": lead_id,
        "email": lead_data["email"],
        "name": lead_data["name"],
        "source": lead_data.get("source", "trustee-101-landing-page"),
        "lead_type": "email_capture",
        "stage": lead_data.get("stage", "new"),
        "manual_stage_override": lead_data.get("manual_stage_override", False),
        "lessons_watched": lead_data.get("lessons_watched", 0),
        "subscription_status": lead_data.get("subscription_status"),
        "last_login": lead_data.get("last_login"),
        "booked_call": lead_data.get("booked_call", False),
        "booked_call_at": lead_data.get("booked_call_at"),
        "notes": lead_data.get("notes", ""),
        "score": lead_data.get("score", 50),
        "created_at": lead_data.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": lead_data.get("updated_at", datetime.now(timezone.utc).isoformat()),
    }
    # Remove None values
    doc = {k: v for k, v in doc.items() if v is not None}
    await db.leads.insert_one(doc)
    return lead_id

async def log_activity(lead_id, action_type, content, created_at=None):
    """Log an activity entry for a lead."""
    activity = {
        "lead_id": lead_id,
        "action_type": action_type,
        "content": content,
        "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
    }
    await db.lead_activities.insert_one(activity)

async def seed():
    now = datetime.now(timezone.utc)
    
    print("Seeding test leads...\n")
    
    # ==================== SCENARIO 1: NEW LEADS ====================
    print("--- NEW LEADS ---")
    
    # 1a. Brand new — just signed up from Trustee 101 landing page
    lid = await create_lead({
        "email": "sarah.new@example.com",
        "name": "Sarah Johnson",
        "source": "trustee-101-landing-page",
        "stage": "new",
        "lessons_watched": 0,
        "score": 50,
        "created_at": (now - timedelta(hours=2)).isoformat(),
        "updated_at": (now - timedelta(hours=2)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via trustee-101-landing-page", now - timedelta(hours=2))
    print(f"  {lid}: Sarah Johnson — new, just signed up 2h ago")
    
    # 1b. New from blog subscribe (lower quality)
    lid = await create_lead({
        "email": "mike.blog@example.com",
        "name": "Mike Chen",
        "source": "blog-subscribe",
        "stage": "new",
        "lessons_watched": 0,
        "score": 40,
        "created_at": (now - timedelta(days=1)).isoformat(),
        "updated_at": (now - timedelta(days=1)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via blog-subscribe", now - timedelta(days=1))
    print(f"  {lid}: Mike Chen — new, blog subscriber 1d ago")
    
    # 1c. New from liability protection kit (high intent source)
    lid = await create_lead({
        "email": "emma.protect@example.com",
        "name": "Emma Davis",
        "source": "liability-protection-kit",
        "stage": "new",
        "lessons_watched": 0,
        "score": 55,
        "created_at": (now - timedelta(hours=6)).isoformat(),
        "updated_at": (now - timedelta(hours=6)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via liability-protection-kit", now - timedelta(hours=6))
    print(f"  {lid}: Emma Davis — new, downloaded liability kit 6h ago")
    
    # ==================== SCENARIO 2: ENGAGED LEADS ====================
    print("\n--- ENGAGED LEADS ---")
    
    # 2a. Engaged — watched 2 lessons, logged in yesterday
    lid = await create_lead({
        "email": "james.engaged@example.com",
        "name": "James Wilson",
        "source": "trustee-101-landing-page",
        "stage": "engaged",
        "lessons_watched": 2,
        "score": 65,
        "last_login": (now - timedelta(days=1)).isoformat(),
        "created_at": (now - timedelta(days=5)).isoformat(),
        "updated_at": (now - timedelta(hours=12)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via trustee-101-landing-page", now - timedelta(days=5))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged (watched 2 lessons)", now - timedelta(days=3))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=5))
    print(f"  {lid}: James Wilson — engaged, 2 lessons, logged in yesterday")
    
    # 2b. Highly engaged — watched 5 lessons, logged in today, high score
    lid = await create_lead({
        "email": "lisa.hot@example.com",
        "name": "Lisa Thompson",
        "source": "commingling-checklist",
        "stage": "engaged",
        "lessons_watched": 5,
        "score": 82,
        "last_login": (now - timedelta(hours=3)).isoformat(),
        "created_at": (now - timedelta(days=10)).isoformat(),
        "updated_at": (now - timedelta(hours=3)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via commingling-checklist", now - timedelta(days=10))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged (watched 1 lesson)", now - timedelta(days=8))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=10))
    await log_activity(lid, "email", "Sent course nudge email", now - timedelta(days=6))
    print(f"  {lid}: Lisa Thompson — highly engaged, 5 lessons, logged in 3h ago")
    
    # 2c. Engaged but idle — watched 3 lessons, hasn't logged in 5 days
    lid = await create_lead({
        "email": "robert.idle@example.com",
        "name": "Robert Garcia",
        "source": "distribution-guide",
        "stage": "engaged",
        "lessons_watched": 3,
        "score": 55,
        "last_login": (now - timedelta(days=5)).isoformat(),
        "created_at": (now - timedelta(days=14)).isoformat(),
        "updated_at": (now - timedelta(days=5)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via distribution-guide", now - timedelta(days=14))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged (watched 3 lessons)", now - timedelta(days=10))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=14))
    print(f"  {lid}: Robert Garcia — engaged but idle, 3 lessons, 5d since login")
    
    # ==================== SCENARIO 3: WARM LEADS ====================
    print("\n--- WARM LEADS ---")
    
    # 3a. Warm — signed up 10 days ago, never watched a lesson
    lid = await create_lead({
        "email": "patricia.warm@example.com",
        "name": "Patricia Martinez",
        "source": "new-trustee-guide",
        "stage": "warm",
        "lessons_watched": 0,
        "score": 35,
        "created_at": (now - timedelta(days=10)).isoformat(),
        "updated_at": (now - timedelta(days=10)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via new-trustee-guide", now - timedelta(days=10))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=10))
    print(f"  {lid}: Patricia Martinez — warm, 10d no engagement")
    
    # 3b. Warm from pricing page (lower intent)
    lid = await create_lead({
        "email": "david.pricing@example.com",
        "name": "David Kim",
        "source": "pricing-lead",
        "stage": "warm",
        "lessons_watched": 0,
        "score": 30,
        "created_at": (now - timedelta(days=21)).isoformat(),
        "updated_at": (now - timedelta(days=21)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via pricing-lead", now - timedelta(days=21))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=21))
    print(f"  {lid}: David Kim — warm, pricing page, 21d no engagement")
    
    # ==================== SCENARIO 4: BOOKED CALL LEADS ====================
    print("\n--- BOOKED CALL LEADS ---")
    
    # 4a. Booked a call, watched 1 lesson — high intent
    lid = await create_lead({
        "email": "amanda.call@example.com",
        "name": "Amanda Foster",
        "source": "booked-call",
        "stage": "engaged",
        "lessons_watched": 1,
        "score": 85,
        "booked_call": True,
        "booked_call_at": (now - timedelta(days=1)).isoformat(),
        "last_login": (now - timedelta(days=1)).isoformat(),
        "created_at": (now - timedelta(days=3)).isoformat(),
        "updated_at": (now - timedelta(hours=12)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via booked-call", now - timedelta(days=3))
    await log_activity(lid, "booked_call", "Booked a TrustOffice Discovery Call", now - timedelta(days=1))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=3))
    print(f"  {lid}: Amanda Foster — booked call, 1 lesson, score 85")
    
    # 4b. Booked a call, no lessons — needs prep
    lid = await create_lead({
        "email": "carlos.call@example.com",
        "name": "Carlos Rivera",
        "source": "booked-call",
        "stage": "new",
        "lessons_watched": 0,
        "score": 70,
        "booked_call": True,
        "booked_call_at": (now - timedelta(hours=6)).isoformat(),
        "created_at": (now - timedelta(days=1)).isoformat(),
        "updated_at": (now - timedelta(hours=6)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via booked-call", now - timedelta(days=1))
    await log_activity(lid, "booked_call", "Booked a TrustOffice Discovery Call", now - timedelta(hours=6))
    print(f"  {lid}: Carlos Rivera — booked call, no lessons yet")
    
    # ==================== SCENARIO 5: CONVERTED LEADS ====================
    print("\n--- CONVERTED LEADS ---")
    
    # 5a. Recently converted — subscribed 2 days ago
    lid = await create_lead({
        "email": "rachel.converted@example.com",
        "name": "Rachel Adams",
        "source": "trustee-101-landing-page",
        "stage": "converted",
        "lessons_watched": 6,
        "score": 95,
        "subscription_status": "active",
        "last_login": (now - timedelta(hours=6)).isoformat(),
        "created_at": (now - timedelta(days=20)).isoformat(),
        "updated_at": (now - timedelta(days=2)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via trustee-101-landing-page", now - timedelta(days=20))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged", now - timedelta(days=15))
    await log_activity(lid, "stage_change", "Stage changed: engaged → converted (subscribed)", now - timedelta(days=2))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=20))
    await log_activity(lid, "email", "Sent subscription pitch", now - timedelta(days=5))
    print(f"  {lid}: Rachel Adams — converted, 6 lessons, subscribed 2d ago")
    
    # 5b. Long-time converted — subscribed 60 days ago
    lid = await create_lead({
        "email": "thomas.loyal@example.com",
        "name": "Thomas Baker",
        "source": "webinar-signup",
        "stage": "converted",
        "lessons_watched": 9,
        "score": 98,
        "subscription_status": "active",
        "last_login": (now - timedelta(days=1)).isoformat(),
        "created_at": (now - timedelta(days=90)).isoformat(),
        "updated_at": (now - timedelta(days=60)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via webinar-signup", now - timedelta(days=90))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged", now - timedelta(days=80))
    await log_activity(lid, "stage_change", "Stage changed: engaged → converted (subscribed)", now - timedelta(days=60))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=90))
    print(f"  {lid}: Thomas Baker — converted, all 9 lessons, loyal subscriber")
    
    # ==================== SCENARIO 6: LOST LEADS ====================
    print("\n--- LOST LEADS ---")
    
    # 6a. Lost — 45 days, never watched a lesson
    lid = await create_lead({
        "email": "jessica.lost@example.com",
        "name": "Jessica Lee",
        "source": "blog-article-pdf",
        "stage": "lost",
        "lessons_watched": 0,
        "score": 15,
        "created_at": (now - timedelta(days=45)).isoformat(),
        "updated_at": (now - timedelta(days=45)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via blog-article-pdf", now - timedelta(days=45))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=45))
    await log_activity(lid, "email", "Sent re-engagement email", now - timedelta(days=35))
    print(f"  {lid}: Jessica Lee — lost, 45d no engagement")
    
    # 6b. Lost — 60 days, watched 1 lesson then went cold
    lid = await create_lead({
        "email": "kevin.lost2@example.com",
        "name": "Kevin Nguyen",
        "source": "trustee-90-day-checklist",
        "stage": "lost",
        "lessons_watched": 1,
        "score": 20,
        "last_login": (now - timedelta(days=50)).isoformat(),
        "created_at": (now - timedelta(days=60)).isoformat(),
        "updated_at": (now - timedelta(days=50)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via trustee-90-day-checklist", now - timedelta(days=60))
    await log_activity(lid, "stage_change", "Stage changed: new → engaged (watched 1 lesson)", now - timedelta(days=55))
    await log_activity(lid, "email", "Sent welcome email", now - timedelta(days=60))
    print(f"  {lid}: Kevin Nguyen — lost, watched 1 lesson then went cold")
    
    # ==================== SCENARIO 7: EDGE CASES ====================
    print("\n--- EDGE CASES ---")
    
    # 7a. Manual lead (admin-created)
    lid = await create_lead({
        "email": "manual.lead@example.com",
        "name": "Manual Entry",
        "source": "manual",
        "stage": "new",
        "lessons_watched": 0,
        "score": 40,
        "notes": "Referred by existing customer — follow up personally",
        "created_at": (now - timedelta(days=2)).isoformat(),
        "updated_at": (now - timedelta(days=2)).isoformat(),
    })
    await log_activity(lid, "created", "Lead created manually by admin", now - timedelta(days=2))
    await log_activity(lid, "note_added", "Referred by existing customer — follow up personally", now - timedelta(days=2))
    print(f"  {lid}: Manual Entry — admin-created, has notes")
    
    # 7b. High score but no login (fresh + booked call)
    lid = await create_lead({
        "email": "urgent.high@example.com",
        "name": "Urgent Prospect",
        "source": "governance-offer",
        "stage": "new",
        "lessons_watched": 0,
        "score": 60,
        "booked_call": True,
        "booked_call_at": (now - timedelta(hours=1)).isoformat(),
        "created_at": (now - timedelta(hours=1)).isoformat(),
        "updated_at": (now - timedelta(hours=1)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via governance-offer", now - timedelta(hours=1))
    await log_activity(lid, "booked_call", "Booked a TrustOffice Discovery Call", now - timedelta(hours=1))
    print(f"  {lid}: Urgent Prospect — just booked a call 1h ago")
    
    # 7c. Direct traffic (unknown source)
    lid = await create_lead({
        "email": "direct.traffic@example.com",
        "name": "Direct Visitor",
        "source": "direct",
        "stage": "new",
        "lessons_watched": 0,
        "score": 35,
        "created_at": (now - timedelta(days=3)).isoformat(),
        "updated_at": (now - timedelta(days=3)).isoformat(),
    })
    await log_activity(lid, "created", "Lead captured via direct", now - timedelta(days=3))
    print(f"  {lid}: Direct Visitor — unknown source, 3d old")
    
    # ==================== SUMMARY ====================
    total = await db.leads.count_documents({})
    by_stage = {}
    for s in ["new", "engaged", "warm", "converted", "lost"]:
        by_stage[s] = await db.leads.count_documents({"stage": s})
    
    print(f"\n{'='*50}")
    print(f"SEED COMPLETE — {total} total leads")
    print(f"{'='*50}")
    for stage, count in by_stage.items():
        print(f"  {stage}: {count}")
    print(f"\nTest leads created. Check the Admin → Leads tab and the notification bell.")

if __name__ == "__main__":
    asyncio.run(seed())
