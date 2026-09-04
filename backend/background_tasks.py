"""
Background Tasks for TrustOffice
Scheduled jobs for task reminders, status updates, and maintenance
Uses APScheduler for scheduling background jobs
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Configuration
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


class BackgroundTaskRunner:
    """
    Background task runner for scheduled jobs.
    Uses APScheduler for cron-like scheduling.
    """
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.running = False
        
    async def start(self):
        """Start the background task runner with APScheduler"""
        if self.running:
            logger.warning("Background runner already running")
            return
            
        self.client = AsyncIOMotorClient(MONGO_URL)
        self.db = self.client[DB_NAME]
        self.running = True
        
        # Initialize APScheduler
        self.scheduler = AsyncIOScheduler(timezone='UTC')
        
        # Schedule task status update every hour
        self.scheduler.add_job(
            self.update_task_statuses,
            trigger=IntervalTrigger(hours=1),
            id='task_status_update',
            name='Update task statuses based on due dates',
            replace_existing=True
        )
        
        # Schedule daily reminders at 9 AM UTC
        self.scheduler.add_job(
            self.send_daily_reminders,
            trigger=CronTrigger(hour=9, minute=0, timezone='UTC'),
            id='daily_reminders',
            name='Send daily task reminder emails',
            replace_existing=True
        )
        
        # Schedule governance health snapshot daily at midnight UTC
        self.scheduler.add_job(
            self.create_daily_health_snapshots,
            trigger=CronTrigger(hour=0, minute=5, timezone='UTC'),
            id='daily_health_snapshots',
            name='Create daily governance health snapshots',
            replace_existing=True
        )

        # Schedule deadline reminder emails daily at 8 AM UTC
        self.scheduler.add_job(
            self.send_deadline_reminders,
            trigger=CronTrigger(hour=8, minute=0, timezone='UTC'),
            id='deadline_reminders',
            name='Send compliance deadline reminder emails',
            replace_existing=True
        )

        # Schedule lead re-engagement check every 6 hours
        self.scheduler.add_job(
            self.send_lead_reengagement_emails,
            trigger=IntervalTrigger(hours=6),
            id='lead_reengagement',
            name='Send re-engagement emails to stale leads',
            replace_existing=True
        )

        # Schedule nurture drip check every 6 hours
        self.scheduler.add_job(
            self.send_nurture_drip_emails,
            trigger=IntervalTrigger(hours=6),
            id='nurture_drip',
            name='Send nurture sequence emails 2-12 on schedule',
            replace_existing=True
        )

        # Schedule TidyCal booking sync every 5 minutes
        self.scheduler.add_job(
            self.sync_tidycal_bookings,
            trigger=IntervalTrigger(minutes=5),
            id='tidycal_sync',
            name='Sync TidyCal bookings to CRM leads',
            replace_existing=True
        )

        # Schedule same-day booking confirmation emails each morning at 7 AM UTC
        self.scheduler.add_job(
            self.send_booking_confirmation_emails,
            trigger=CronTrigger(hour=7, minute=0, timezone='UTC'),
            id='booking_confirmation',
            name='Send same-day booking confirmation emails',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Background task runner started with APScheduler")
        
    async def sync_tidycal_bookings(self):
        """
        Poll TidyCal API for bookings and sync them to CRM leads.
        Runs every 5 minutes. Matches bookings to leads by email and sets
        booked_call=True with the scheduled date/time.
        Creates new leads for bookings that don't match an existing lead.
        """
        import httpx

        token = os.environ.get('TIDYCAL_API_TOKEN')
        if not token:
            logger.debug("TIDYCAL_API_TOKEN not set — skipping TidyCal sync")
            return

        try:
            resp = await asyncio.to_thread(
                httpx.get,
                "https://tidycal.com/api/bookings?cancelled=false",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            bookings = resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"TidyCal sync failed: {e}")
            return

        now = datetime.now(timezone.utc).isoformat()
        created = 0
        updated = 0

        for b in bookings:
            contact = b.get("contact", {})
            email = (contact.get("email") or "").strip().lower()
            name = contact.get("name", "Unknown")
            starts_at = b.get("starts_at")

            if not email:
                continue

            # Skip Jeff's own test bookings
            if email in ("sheffk78@gmail.com", "jeff@socialize.video"):
                continue

            existing = await self.db.leads.find_one({"email": email})

            if existing:
                if existing.get("booked_call") and existing.get("booked_call_at"):
                    continue  # Already synced

                # Preserve the lead's true origin: never overwrite `source` with
                # "booked-call" (a booking is an action, not an origin channel).
                # Backfill origin_source for legacy leads that predate the field.
                origin = existing.get("origin_source") or existing.get("source") or "booked-call"
                await self.db.leads.update_one(
                    {"email": email},
                    {"$set": {
                        "name": name,
                        "booked_call": True,
                        "booked_call_at": starts_at,
                        "origin_source": origin,
                        "updated_at": now,
                    }}
                )
                # Format next_action in Mountain Time
                try:
                    from datetime import datetime as dt_cls, timezone as tz_cls, timedelta as td_cls
                    booking_dt = dt_cls.fromisoformat(starts_at.replace("Z", "+00:00"))
                    mt_time = booking_dt.astimezone(tz_cls(td_cls(hours=-6)))
                    mt_str = mt_time.strftime("%b %d, %I:%M %p MT").replace(" 0", " ")
                    next_action = f"Booked: {mt_str}"
                except:
                    next_action = "Prepare for upcoming discovery call"
                await self.db.leads.update_one(
                    {"email": email},
                    {"$set": {"next_action": next_action}}
                )
                await self.db.lead_activities.insert_one({
                    "activity_id": f"act_{uuid.uuid4().hex[:12]}",
                    "lead_id": existing["lead_id"],
                    "action_type": "booked_call",
                    "content": f"Booked a TrustOffice Discovery Call at {starts_at} (TidyCal sync)",
                    "created_at": now,
                })
                updated += 1
            else:
                # Format next_action in Mountain Time
                try:
                    from datetime import datetime as dt_cls, timezone as tz_cls, timedelta as td_cls
                    booking_dt = dt_cls.fromisoformat(starts_at.replace("Z", "+00:00"))
                    mt_time = booking_dt.astimezone(tz_cls(td_cls(hours=-6)))
                    mt_str = mt_time.strftime("%b %d, %I:%M %p MT").replace(" 0", " ")
                    next_action = f"Booked: {mt_str}"
                except:
                    next_action = "Prepare for upcoming discovery call"
                lead_id = f"lead_{uuid.uuid4().hex[:12]}"
                try:
                    await self.db.leads.insert_one({
                        "lead_id": lead_id,
                        "email": email,
                        "name": name,
                        "source": "booked-call",
                        "origin_source": "booked-call",
                        "lead_type": "email_capture",
                        "stage": "new",
                        "manual_stage_override": False,
                        "booked_call": True,
                        "booked_call_at": starts_at,
                        "lessons_watched": 0,
                        "subscription_status": None,
                        "last_login": None,
                        "notes": "",
                        "next_action": next_action,
                        "score": 70,
                        "created_at": now,
                        "updated_at": now,
                    })
                except Exception as insert_err:
                    # DuplicateKeyError — another instance already created this lead
                    if "duplicate key" in str(insert_err).lower() or "11000" in str(insert_err):
                        logger.info(f"TidyCal sync: lead {email} already created by another instance — skipping")
                        continue
                    raise
                await self.db.lead_activities.insert_one({
                    "activity_id": f"act_{uuid.uuid4().hex[:12]}",
                    "lead_id": lead_id,
                    "action_type": "created",
                    "content": "Lead captured via TidyCal booking (API sync)",
                    "created_at": now,
                })
                await self.db.lead_activities.insert_one({
                    "activity_id": f"act_{uuid.uuid4().hex[:12]}",
                    "lead_id": lead_id,
                    "action_type": "booked_call",
                    "content": f"Booked a TrustOffice Discovery Call at {starts_at} (TidyCal sync)",
                    "created_at": now,
                })
                created += 1

        if created or updated:
            logger.info(f"TidyCal sync: {created} created, {updated} updated, {len(bookings)} total bookings")

    async def stop(self):
        """Stop the background task runner"""
        self.running = False
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        if self.client:
            self.client.close()
        logger.info("Background task runner stopped")
    
    def get_jobs_info(self) -> list:
        """Get information about scheduled jobs"""
        if not self.scheduler:
            return []
        
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": next_run,
                "pending": job.pending
            })
        return jobs
    
    async def send_booking_confirmation_emails(self) -> int:
        """
        Send same-day booking confirmation emails to leads with calls scheduled today.

        Fetches today's TidyCal bookings (not cancelled), sends a confirmation email
        with the Google Meet link to each, and records the send on the lead so each
        booking is confirmed at most once. Runs each morning.
        """
        logger.info("Running booking confirmation job")
        try:
            from email_service import email_service

            if not email_service.is_configured:
                logger.warning("Email service not configured, skipping booking confirmations")
                return 0

            token = os.environ.get('TIDYCAL_API_TOKEN')
            if not token:
                logger.debug("TIDYCAL_API_TOKEN not set — skipping booking confirmations")
                return 0

            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            # Fetch today's bookings from TidyCal
            import httpx
            try:
                resp = await asyncio.to_thread(
                    httpx.get,
                    f"https://tidycal.com/api/bookings?starts_at={today_start.isoformat()}Z&ends_at={today_end.isoformat()}Z",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                bookings = resp.json().get("data", [])
            except Exception as e:
                logger.warning(f"Booking confirmation: TidyCal fetch failed: {e}")
                return 0

            emails_sent = 0
            for b in bookings:
                try:
                    contact = b.get("contact", {})
                    email = (contact.get("email") or "").strip().lower()
                    name = contact.get("name", "there")
                    if not email:
                        continue
                    # Skip internal/test bookings
                    if email in ("sheffk78@gmail.com", "jeff@socialize.video"):
                        continue

                    meeting_url = b.get("meeting_url") or ""
                    starts_at = b.get("starts_at")

                    # Convert to the booker's timezone for display
                    tz_name = b.get("timezone") or "America/Denver"
                    call_date = ""
                    call_time = ""
                    try:
                        from datetime import datetime as dt_cls
                        from zoneinfo import ZoneInfo
                        b_dt = dt_cls.fromisoformat(starts_at.replace("Z", "+00:00")) if starts_at else None
                        if b_dt:
                            b_local = b_dt.astimezone(ZoneInfo(tz_name))
                            call_date = b_local.strftime("%A, %B %d, %Y")
                            call_time = b_local.strftime("%I:%M %p")
                    except Exception:
                        pass

                    result = await email_service.send_booking_confirmation(
                        to_email=email,
                        name=name,
                        call_date=call_date,
                        call_time=call_time,
                        timezone=tz_name,
                        meeting_url=meeting_url,
                    )
                    if result.get("status") == "sent":
                        emails_sent += 1
                        logger.info(f"Booking confirmation sent to {email}")
                except Exception as e:
                    logger.error(f"Booking confirmation failed for {b.get('id')}: {e}")

            logger.info(f"Booking confirmation job complete: {emails_sent} emails sent")
            return emails_sent

        except Exception as e:
            logger.error(f"Error in booking confirmation job: {e}")
            return 0

    async def update_task_statuses(self) -> int:
        """
        Update task statuses based on due dates.
        Marks tasks as overdue if past due date.
        """
        logger.info("Running task status update job")
        
        try:
            now = datetime.now(timezone.utc)
            today = now.date().isoformat()
            
            # Find all incomplete tasks
            tasks = await self.db.governance_tasks.find({
                "completed_at": None
            }, {"_id": 0}).to_list(1000)
            
            updates_made = 0
            
            for task in tasks:
                due_date = task.get("due_date", "")[:10]
                current_status = task.get("calculated_status")
                
                # Determine new status
                if due_date < today:
                    new_status = "overdue"
                else:
                    new_status = "upcoming"
                
                # Update if status changed
                if current_status != new_status:
                    await self.db.governance_tasks.update_one(
                        {"task_id": task["task_id"]},
                        {"$set": {"calculated_status": new_status}}
                    )
                    updates_made += 1
                    
                    # Log audit event for status change
                    await self._log_audit(
                        user_id="system",
                        action="task_status_change",
                        entity_type="task",
                        entity_id=task["task_id"],
                        details={
                            "old_status": current_status,
                            "new_status": new_status,
                            "due_date": due_date
                        }
                    )
            
            logger.info(f"Task status update complete: {updates_made} tasks updated")
            return updates_made
            
        except Exception as e:
            logger.error(f"Error updating task statuses: {e}")
            return 0
    
    async def send_daily_reminders(self) -> int:
        """
        Send daily reminder emails for upcoming and overdue tasks.
        """
        logger.info("Running daily reminder job")
        
        try:
            from email_service import email_service
            
            if not email_service.is_configured:
                logger.warning("Email service not configured, skipping reminders")
                return 0
            
            now = datetime.now(timezone.utc)
            today = now.date()
            upcoming_cutoff = (today + timedelta(days=7)).isoformat()
            
            # Get all users with trusts
            users = await self.db.users.find({}, {"_id": 0}).to_list(1000)
            
            emails_sent = 0
            
            for user in users:
                user_id = user["user_id"]
                user_email = user["email"]
                user_name = user.get("name", "")
                
                # Get user's trusts — exclude demo trusts so demo data never triggers emails
                trusts = await self.db.trusts.find(
                    {"user_id": user_id, "is_demo": {"$ne": True}},
                    {"_id": 0}
                ).to_list(100)
                
                for trust in trusts:
                    trust_id = trust["trust_id"]
                    trust_name = trust.get("name", "")
                    
                    # Get incomplete tasks — exclude demo tasks
                    tasks = await self.db.governance_tasks.find({
                        "trust_id": trust_id,
                        "user_id": user_id,
                        "completed_at": None,
                        "is_demo": {"$ne": True}
                    }, {"_id": 0}).to_list(100)
                    
                    for task in tasks:
                        task_due = task.get("due_date", "")[:10]
                        task_type = task.get("task_type", "")
                        description = task.get("description", "")
                        task_id = task.get("task_id")
                        
                        # Check if overdue
                        if task_due < today.isoformat():
                            # Only send overdue notification ONCE - check if we already notified
                            overdue_notified_at = task.get("overdue_notified_at")
                            
                            if not overdue_notified_at:
                                # First time this task is overdue - send notification
                                try:
                                    due_date_obj = datetime.fromisoformat(task_due).date()
                                    days_overdue = (today - due_date_obj).days
                                except ValueError:
                                    days_overdue = 1
                                
                                try:
                                    await email_service.send_task_overdue(
                                        to_email=user_email,
                                        user_name=user_name,
                                        trust_name=trust_name,
                                        task_type=task_type,
                                        due_date=task_due,
                                        days_overdue=days_overdue
                                    )
                                    emails_sent += 1
                                    
                                    # Mark this task as having been notified
                                    await self.db.governance_tasks.update_one(
                                        {"task_id": task_id},
                                        {"$set": {"overdue_notified_at": now.isoformat()}}
                                    )
                                    logger.info(f"Sent one-time overdue notification for task {task_id}")
                                except Exception as e:
                                    logger.error(f"Failed to send overdue email: {e}")
                            
                        # Check if upcoming (within 7 days) - send reminder only ONCE
                        elif task_due <= upcoming_cutoff:
                            # Only send reminder ONCE - check if we already sent one
                            reminder_sent_at = task.get("reminder_sent_at")
                            
                            if not reminder_sent_at:
                                try:
                                    await email_service.send_task_reminder(
                                        to_email=user_email,
                                        user_name=user_name,
                                        trust_name=trust_name,
                                        task_type=task_type,
                                        due_date=task_due,
                                        description=description
                                    )
                                    emails_sent += 1
                                    
                                    # Mark this task as having received a reminder
                                    await self.db.governance_tasks.update_one(
                                        {"task_id": task_id},
                                        {"$set": {"reminder_sent_at": now.isoformat()}}
                                    )
                                    logger.info(f"Sent one-time reminder for task {task_id}")
                                except Exception as e:
                                    logger.error(f"Failed to send reminder email: {e}")
            
            logger.info(f"Daily reminders complete: {emails_sent} emails sent")
            return emails_sent

        except Exception as e:
            logger.error(f"Error sending daily reminders: {e}")
            return 0

    async def send_lead_reengagement_emails(self) -> int:
        """
        Send re-engagement emails to leads who signed up 3+ days ago
        but haven't watched any lessons yet.
        Runs every 6 hours. Only sends once per lead (checks reengagement_sent_at).
        """
        logger.info("Running lead re-engagement check")
        try:
            from email_service import email_service

            if not email_service.is_configured:
                logger.warning("Email service not configured, skipping lead re-engagement")
                return 0

            now = datetime.now(timezone.utc)
            cutoff = (now - timedelta(days=3)).isoformat()

            # Find leads: created 3+ days ago, 0 lessons watched, no re-engagement sent yet
            leads = await self.db.leads.find({
                "created_at": {"$lte": cutoff},
                "lessons_watched": 0,
                "reengagement_sent_at": None,
                "stage": {"$ne": "converted"},
            }, {"_id": 0}).to_list(200)

            emails_sent = 0
            course_url = f"{email_service.app_url}/courses/trustee-101"

            for lead in leads:
                try:
                    await email_service.send_lead_reengagement(
                        to_email=lead["email"],
                        name=lead.get("name", ""),
                        course_url=course_url
                    )

                    # Mark re-engagement as sent
                    await self.db.leads.update_one(
                        {"lead_id": lead["lead_id"]},
                        {"$set": {
                            "reengagement_sent_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        }}
                    )

                    # Log activity
                    await self.db.lead_activities.insert_one({
                        "activity_id": f"act_{uuid.uuid4().hex[:12]}",
                        "lead_id": lead["lead_id"],
                        "action_type": "email",
                        "content": "Sent re-engagement email (3+ days, no lessons watched)",
                        "created_at": now.isoformat(),
                    })

                    emails_sent += 1
                    logger.info(f"Sent re-engagement email to {lead['email']}")

                except Exception as e:
                    logger.error(f"Failed to send re-engagement to {lead.get('email')}: {e}")

            logger.info(f"Lead re-engagement complete: {emails_sent} emails sent")
            return emails_sent

        except Exception as e:
            logger.error(f"Error in lead re-engagement: {e}")
            return 0

    async def send_nurture_drip_emails(self) -> int:
        """
        Send nurture sequence emails 2-12 on schedule via MailerCloud Email API.

        Schedule (12-email sequence):
        - Email 1: Sent immediately on lead capture (in leads.py)
        - Email 2: Day 1 after capture
        - Email 3: Day 3
        - Email 4: Day 5
        - Email 5: Day 7
        - Email 6: Day 10
        - Email 7: Day 12
        - Email 8: Day 14
        - Email 9: Day 17
        - Email 10: Day 21
        - Email 11: Day 25
        - Email 12: Day 30

        Runs every 6 hours. Tracks which step each lead has received
        via the `nurture_step_sent` field on the lead record.
        """
        logger.info("Running nurture drip check (12-email MailerCloud sequence)")
        try:
            from mailercloud_service import send_nurture_email_via_mailercloud, MAILERCLOUD_API_KEY

            if not MAILERCLOUD_API_KEY:
                logger.warning("MailerCloud API key not configured, skipping nurture drip")
                return 0

            now = datetime.now(timezone.utc)
            emails_sent = 0

            # 12-email nurture schedule: step -> days after capture
            NURTURE_SCHEDULE = {
                2: 1,   # Day 1
                3: 3,   # Day 3
                4: 5,   # Day 5
                5: 7,   # Day 7
                6: 10,  # Day 10
                7: 12,  # Day 12
                8: 14,  # Day 14
                9: 17,  # Day 17
                10: 21, # Day 21
                11: 25, # Day 25
                12: 30, # Day 30
            }

            # Find leads that have received Email 1 but haven't completed all 12.
            # Leads whose `nurture_step_sent` field is missing/null are treated as
            # step 0 (never received Email 1) so they still enter the drip: the
            # loop sends step 1 first via the `current_step < 1` catch-up branch
            # below, instead of being permanently skipped by the $gte:1 filter.
            leads = await self.db.leads.find({
                "$or": [
                    {"nurture_step_sent": {"$exists": True, "$gte": 1, "$lt": 12}},
                    {"nurture_step_sent": {"$in": [None, False]}},
                ],
                "stage": {"$ne": "converted"},
                # Booked leads are owned by the post-meeting flow (see
                # leads/MEETING-PROCESS.md). Booking is the conversion event:
                # drip emails with booking CTAs are noise for them, and a
                # booked lead whose nurture field was never set must NOT be
                # caught by the step-0 catch-up branch. no_show leads stay in.
                "booked_call": {"$ne": True},
            }, {"_id": 0}).to_list(500)

            for lead in leads:
                try:
                    # Missing/null nurture_step_sent = step 0 (never got Email 1)
                    if not lead.get("nurture_step_sent"):
                        current_step = 0
                    else:
                        current_step = lead.get("nurture_step_sent", 0)

                    # Schedule anchor: prefer the step-1 send timestamp over the
                    # capture timestamp. Catch-up leads (backfill/re-engagement)
                    # were captured long before they entered the sequence —
                    # anchoring on created_at would make every remaining step
                    # instantly due (one email per 6-hourly run until done).
                    # Falls back to created_at for leads that got step 1 before
                    # timestamps were introduced.
                    anchor_raw = (
                        lead.get("nurture_step1_backfill_at")
                        or lead.get("nurture_step1_sent_at")
                        or lead.get("created_at")
                    )
                    if not anchor_raw:
                        continue

                    # Parse anchor timestamp
                    try:
                        if isinstance(anchor_raw, str):
                            if anchor_raw.endswith('Z'):
                                anchor_raw = anchor_raw[:-1] + '+00:00'
                            anchor_dt = datetime.fromisoformat(anchor_raw)
                        else:
                            anchor_dt = anchor_raw
                    except (ValueError, TypeError):
                        continue
                    if anchor_dt.tzinfo is None:
                        anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)

                    days_since = (now - anchor_dt).days

                    # Check which step to send next
                    next_step = current_step + 1
                    # Catch-up: a lead with no nurture_step_sent never got Email 1
                    # (the sequence opener). The schedule below only covers steps
                    # 2-12, so such a lead is due immediately for step 1; the next
                    # drip run (6h later) sends step 2 onward. Normal leads are
                    # due once their Day-N schedule requirement has elapsed.
                    if current_step < 1:
                        due = True
                        sent_step = 1
                    else:
                        due = next_step in NURTURE_SCHEDULE and days_since >= NURTURE_SCHEDULE[next_step]
                        sent_step = next_step

                    if due:
                        # Send via MailerCloud Email API
                        result = await send_nurture_email_via_mailercloud(
                            to_email=lead["email"],
                            name=lead.get("name", ""),
                            step=sent_step,
                        )

                        if result.get("success"):
                            # Update nurture_step_sent (+ step-1 send timestamp so
                            # the schedule anchors on enrollment, not capture)
                            step1_stamp = (
                                {"nurture_step1_sent_at": now.isoformat()}
                                if sent_step == 1
                                else {}
                            )
                            await self.db.leads.update_one(
                                {"lead_id": lead["lead_id"]},
                                {"$set": {
                                    "nurture_step_sent": sent_step,
                                    "updated_at": now.isoformat(),
                                    **step1_stamp,
                                }}
                            )

                            # Log activity
                            await self.db.lead_activities.insert_one({
                                "activity_id": f"act_{uuid.uuid4().hex[:12]}",
                                "lead_id": lead["lead_id"],
                                "action_type": "email",
                                "content": f"Sent nurture email {sent_step}/12 via MailerCloud",
                                "created_at": now.isoformat(),
                            })

                            emails_sent += 1
                            logger.info(
                                f"Sent nurture email {sent_step}/12 to {lead['email']}"
                            )

                except Exception as e:
                    logger.error(
                        f"Failed to send nurture drip to {lead.get('email')}: {e}"
                    )

            logger.info(f"Nurture drip complete: {emails_sent} emails sent")
            return emails_sent

        except Exception as e:
            logger.error(f"Error in nurture drip: {e}")
            return 0

    async def create_daily_health_snapshots(self) -> int:
        """
        Create daily health score snapshots for all trusts.
        This enables historical tracking and trend analysis.
        """
        logger.info("Running daily health snapshot job")
        
        try:
            # Get all trusts
            trusts = await self.db.trusts.find({}, {"_id": 0}).to_list(1000)
            snapshots_created = 0
            
            for trust in trusts:
                trust_id = trust["trust_id"]
                user_id = trust["user_id"]
                
                try:
                    # Calculate health score (this also saves a snapshot)
                    await self._calculate_health_score_internal(trust_id, user_id)
                    snapshots_created += 1
                except Exception as e:
                    logger.error(f"Error creating snapshot for trust {trust_id}: {e}")
            
            logger.info(f"Daily health snapshots complete: {snapshots_created} snapshots created")
            return snapshots_created
            
        except Exception as e:
            logger.error(f"Error creating daily health snapshots: {e}")
            return 0
    
    async def _calculate_health_score_internal(self, trust_id: str, user_id: str) -> dict:
        """Wrapper that calls the real scoring function from governance.py.
        Uses late import to avoid circular dependency."""
        from routers.governance import calculate_health_score

        result = await calculate_health_score(trust_id, user_id, save_snapshot=True)
        return result

    async def send_deadline_reminders(self) -> int:
        """
        Check upcoming deadlines and send reminder emails for any whose
        days_remaining matches one of their reminder_days_before thresholds.

        Sent thresholds are tracked per-deadline in reminder_sent_days so each
        threshold fires at most once per deadline.
        """
        logger.info("Running deadline reminder job")

        try:
            from email_service import email_service

            if not email_service.is_configured:
                logger.warning("Email service not configured — skipping deadline reminders")
                return 0

            today = datetime.now(timezone.utc).date()
            reminders_sent = 0

            # All active deadlines (not completed/waived)
            cursor = self.db.deadlines.find(
                {"status": {"$nin": ["completed", "waived"]}},
                {"_id": 0},
            )
            deadlines = await cursor.to_list(5000)

            # Cache lookups
            trust_cache: dict = {}
            user_cache: dict = {}

            for deadline in deadlines:
                try:
                    due_raw = deadline.get("due_date")
                    if not due_raw:
                        continue
                    try:
                        due = datetime.fromisoformat(str(due_raw).replace("Z", "+00:00")).date()
                    except (ValueError, TypeError):
                        continue

                    days_remaining = (due - today).days
                    if days_remaining < 0:
                        continue  # overdue handled separately

                    thresholds = deadline.get("reminder_days_before") or []
                    already_sent = set(deadline.get("reminder_sent_days") or [])

                    if days_remaining not in thresholds or days_remaining in already_sent:
                        continue

                    # Resolve trust (cached)
                    trust_id = deadline.get("trust_id")
                    if trust_id not in trust_cache:
                        trust_cache[trust_id] = await self.db.trusts.find_one(
                            {"trust_id": trust_id}, {"_id": 0}
                        )
                    trust = trust_cache[trust_id]
                    if not trust:
                        continue

                    # Resolve recipient user (cached)
                    user_id = deadline.get("user_id")
                    if user_id not in user_cache:
                        user_cache[user_id] = await self.db.users.find_one(
                            {"user_id": user_id}, {"_id": 0}
                        )
                    recipient = user_cache[user_id]
                    if not recipient or not recipient.get("email"):
                        continue

                    await email_service.send_templated_email(
                        to_email=recipient["email"],
                        template_name="task_reminder",
                        template_data={
                            "user_name": recipient.get("name") or recipient.get("email").split("@")[0],
                            "trust_name": trust.get("trust_name", "your trust"),
                            "task_type": deadline.get("title", "Compliance Deadline"),
                            "due_date": due.isoformat(),
                            "description": (
                                f"{deadline.get('description', '')} "
                                f"({days_remaining} day{'s' if days_remaining != 1 else ''} remaining)"
                            ).strip(),
                        },
                        to_name=recipient.get("name"),
                        tag="deadline_reminder",
                    )

                    # Mark this threshold as sent
                    await self.db.deadlines.update_one(
                        {"deadline_id": deadline["deadline_id"]},
                        {
                            "$addToSet": {"reminder_sent_days": days_remaining},
                            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                        },
                    )
                    reminders_sent += 1

                except Exception as e:
                    logger.error(
                        f"Failed to send deadline reminder for {deadline.get('deadline_id')}: {e}"
                    )

            logger.info(f"Deadline reminders complete: {reminders_sent} emails sent")
            return reminders_sent

        except Exception as e:
            logger.error(f"Error in deadline reminder job: {e}")
            return 0

    async def _log_audit(
        self,
        user_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        details: dict = None
    ):
        """Log an audit event"""
        import uuid
        
        audit_doc = {
            "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip_address": None  # System action
        }
        
        await self.db.audit_logs.insert_one(audit_doc)


# Singleton instance
background_runner = BackgroundTaskRunner()


# ==================== MANUAL TRIGGER FUNCTIONS ====================

async def run_task_status_update() -> int:
    """Manual trigger for task status update"""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    
    try:
        result = await runner.update_task_statuses()
        return result
    finally:
        runner.client.close()


async def run_daily_reminders() -> int:
    """Manual trigger for daily reminders"""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    
    try:
        result = await runner.send_daily_reminders()
        return result
    finally:
        runner.client.close()


async def run_health_snapshots() -> int:
    """Manual trigger for health snapshots"""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]

    try:
        result = await runner.create_daily_health_snapshots()
        return result
    finally:
        runner.client.close()


async def run_deadline_reminders() -> int:
    """Manual trigger for deadline reminders"""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]

    try:
        result = await runner.send_deadline_reminders()
        return result
    finally:
        runner.client.close()
