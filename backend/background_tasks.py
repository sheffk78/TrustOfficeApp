"""
Background Tasks for TrustOffice
Scheduled jobs for task reminders, status updates, and maintenance
Uses APScheduler for scheduling background jobs
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from motor.motor_asyncio import AsyncIOMotorClient
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Configuration
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

# Nurture drip throughput cap (item 1): keep a sudden backlog of due sends
# inside MailerCloud rate limits. All due sends still fire across runs.
DRIP_MAX_PER_RUN = 80

# Booking-reminder windows (item 2), mirror leads_monitor.check_leads_pipeline_health.
BOOKING_DAY_BEFORE_LOWER = timedelta(hours=23)
BOOKING_DAY_BEFORE_UPPER = timedelta(hours=25)
BOOKING_ONE_HOUR_LOWER = timedelta(minutes=55)
BOOKING_ONE_HOUR_UPPER = timedelta(minutes=65)
# Default time zone for rendering booked-call times in reminder emails.
BOOKING_TZ = os.environ.get('BOOKING_TZ', 'America/Denver')


def _as_dt(value):
    """Normalize a stored created_at (BSON Date OR ISO string) to a tz-aware UTC datetime.

    Handles the lead_activities.created_at string->Date migration (item 5):
    old docs store an ISO string; new writes store a BSON Date. Returns None
    when unparseable so callers can treat it as 'outside any window'.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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
            name='Send 12-email nurture sequence (MailerCloud)',
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

        # Item 2: booking reminders (day-before + 1h) â hourly check.
        self.scheduler.add_job(
            self.send_booking_reminder_emails,
            trigger=IntervalTrigger(hours=1),
            id='booking_reminders',
            name='Send booking day-before + 1-hour reminders',
            replace_existing=True
        )

        # Item 3: post-drip re-engagement for completed-but-stuck cohort â 6h.
        self.scheduler.add_job(
            self.send_post_drip_reengagement,
            trigger=IntervalTrigger(hours=6),
            id='post_drip_reengagement',
            name='One-time post-drip re-engagement send',
            replace_existing=True
        )

        # Item 4: pipeline health monitor (asserts + RED alert) â 6h.
        self.scheduler.add_job(
            self.check_leads_pipeline_health,
            trigger=IntervalTrigger(hours=6),
            id='leads_pipeline_health',
            name='Leads pipeline health monitor (anti-silent-failure)',
            replace_existing=True
        )

        # State compliance reminder monitor (asserts + RED alert) â 6h (item 4).
        self.scheduler.add_job(
            self.check_compliance_reminder_health,
            trigger=IntervalTrigger(hours=6),
            id='compliance_reminder_health',
            name='State compliance reminder health monitor (anti-silent-failure)',
            replace_existing=True
        )

        # Item 5: backfill lead_activities.created_at strings -> BSON Dates â daily.
        self.scheduler.add_job(
            self.backfill_lead_activities_dates,
            trigger=IntervalTrigger(hours=24),
            id='backfill_activity_dates',
            name='Backfill lead_activities created_at to BSON Date',
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
            # cutoff is a BSON Date used for the in-Python 3-day gate below.
            cutoff = now - timedelta(days=3)

            # Find leads: 0 lessons watched, no re-engagement sent yet, not
            # converted. The "created 3+ days ago" gate is applied in Python
            # (below) via _as_dt so it works whether leads.created_at is stored
            # as a BSON Date or a legacy ISO string (mixed across the codebase).
            # A DB-level `created_at: {$lte: cutoff}` would silently exclude
            # whichever type doesn't match the cutoff type.
            # 2026-09-18 fix: exclude lost leads. Jeff marks bad/wrong-number
            # leads lost from the admin — the re-engagement nudge must not email
            # them (their only contact channel left is email, and Jeff
            # deliberately closed that lane when he marked them lost).
            leads = await self.db.leads.find({
                "lessons_watched": 0,
                "reengagement_sent_at": None,
                "stage": {"$nin": ["converted", "lost"]},
            }, {"_id": 0}).to_list(200)

            eligible = []
            for lead in leads:
                created = _as_dt(lead.get("created_at"))
                if created is not None and created <= cutoff:
                    eligible.append(lead)
            leads = eligible

            emails_sent = 0
            course_url = f"{email_service.app_url}/trustee-101"

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
                        "created_at": now,
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
        Send the 12-email nurture sequence via MailerCloud (steps 2-12 on schedule;
        step 1 fires on capture in leads.py).

        Schedule (12-email sequence, day offsets 0-80):
        - Email 1: Sent immediately on lead capture (in leads.py)
        - Email 2: Day 3 after capture
        - Email 3: Day 8
        - Email 4: Day 12
        - Email 5: Day 18
        - Email 6: Day 25
        - Email 7: Day 35
        - Email 8: Day 42
        - Email 9: Day 50
        - Email 10: Day 60
        - Email 11: Day 70
        - Email 12: Day 80

        Runs every 6 hours. Tracks which step each lead has received
        via the `nurture_step_sent` field on the lead record.

        Throughput (item 1): all eligible due sends fire each run, capped at
        DRIP_MAX_PER_RUN (default 80) to stay inside MailerCloud rate limits.
        A [drip-metric] line logs sends/eligible/cap each run.

        Backward-compat: leads partway through the old sequence may carry
        nurture_step_sent values 1-12. Any lead with nurture_step_sent >= 12 is
        treated as sequence-complete (12 emails total) and is skipped.
        """
        logger.info("Running nurture drip check (7-email MailerCloud sequence)")
        try:
            from mailercloud_service import (
                send_nurture_email_via_mailercloud,
                MAILERCLOUD_API_KEY,
                remove_contact_from_list,
                MAILERCLOUD_LEADS_LIST_ID,
            )

            if not MAILERCLOUD_API_KEY:
                logger.warning("MailerCloud API key not configured, skipping nurture drip")
                return 0

            now = datetime.now(timezone.utc)
            emails_sent = 0

            # 12-email nurture schedule: step -> days after the step-1 anchor.
            # The sequence has exactly 12 emails (steps 1..12, day offsets 0-80);
            # step-13 was a leftover from the old schedule and is not a real
            # email, so it has been removed. Completion is step >= 12.
            NURTURE_SCHEDULE = {
                2: 3,   # Day 3
                3: 8,   # Day 8
                4: 12,  # Day 12
                5: 18,  # Day 18
                6: 25,  # Day 25
                7: 35,  # Day 35
                8: 42,  # Day 42
                9: 50,  # Day 50
                10: 60, # Day 60
                11: 70, # Day 70
                12: 80, # Day 80
            }

            # Find leads that have received Email 1 but haven't completed all 13.
            # Leads whose `nurture_step_sent` field is missing/null are treated as
            # step 0 (never received Email 1) so they still enter the drip: the
            # loop sends step 1 first via the `current_step < 1` catch-up branch
            # below, instead of being permanently skipped by the $gte:1 filter.
            # Leads with nurture_step_sent >= 13 are treated as sequence-complete;
            # treated as sequence-complete and skipped.
            # 2026-09-16 fix: catch-up eligibility must also match leads whose
            # nurture_step_sent is an explicit integer 0 (backfilled/reactivated
            # leads). The old `$in: [None, False]` missed BSON integer 0, so such
            # leads were silently skipped by every drip run forever. `$not: {$gt: 0}`
            # matches missing, null, False, AND integer 0 — superset of the old
            # branch, still excludes 13+ (sequence-complete) via the $or first arm.
            # 2026-09-18 fix: exclude lost leads — Jeff marks bad/wrong-number
            # leads lost from the admin; the drip must not keep emailing them.
            # (Joy Giesen got nurture 4 AFTER being marked lost 2026-09-15.)
            leads = await self.db.leads.find({
                "$or": [
                    {"nurture_step_sent": {"$exists": True, "$gte": 1, "$lt": 13}},
                    {"nurture_step_sent": {"$not": {"$gt": 0}}},
                ],
                "stage": {"$nin": ["converted", "lost"]},
                # Booked leads are owned by the post-meeting flow (see
                # leads/MEETING-PROCESS.md). Booking is the conversion event:
                # drip emails with booking CTAs are noise for them, and a
                # booked lead whose nurture field was never set must NOT be
                # caught by the step-0 catch-up branch. no_show leads are
                # excluded too (they carry booked_call: true) — the no-show
                # flow (reschedule email, 7-day nudge, 14-day DNC) owns them.
                "booked_call": {"$ne": True},
            }, {"_id": 0}).to_list(2000)

            eligible_count = len(leads)
            if eligible_count > DRIP_MAX_PER_RUN:
                logger.info(
                    f"[drip-metric] eligible={eligible_count} exceeds cap "
                    f"{DRIP_MAX_PER_RUN}; remaining due sends fire on subsequent runs"
                )

            for lead in leads:
                # Per-run cap: stop sending once we hit DRIP_MAX_PER_RUN so we
                # stay inside MailerCloud rate limits. Due-but-uncapped leads
                # simply fire on the next 6h run (all due sends still get sent).
                if emails_sent >= DRIP_MAX_PER_RUN:
                    break
                try:
                    # Missing/null nurture_step_sent = step 0 (never got Email 1)
                    if not lead.get("nurture_step_sent"):
                        current_step = 0
                    else:
                        current_step = lead.get("nurture_step_sent", 0)

                    # Backward-compat: legacy leads from the old sequence may
                    # carry nurture_step_sent values 8-12. The schedule tops out
                    # at step 12 (12 emails total), so treat any lead at step
                    # >= 12 as sequence-complete: skip without sending or raising.
                    if current_step >= 12:
                        continue
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
                    # 1 (the sequence opener). The schedule below only covers steps
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
                                "created_at": now,
                            })

                            emails_sent += 1
                            logger.info(
                                f"Sent nurture email {sent_step}/12 to {lead['email']}"
                            )

                except Exception as e:
                    logger.error(
                        f"Failed to send nurture drip to {lead.get('email')}: {e}"
                    )

            # [drip-metric] sends-per-run metric line (item 1). ratio is sends
            # vs. eligible cohort; at 100% all eligible due sends fired this run.
            ratio = (emails_sent / eligible_count) if eligible_count else 0.0
            logger.info(
                f"[drip-metric] emails_sent={emails_sent} eligible={eligible_count} "
                f"cap={DRIP_MAX_PER_RUN} ratio={ratio:.2%} "
                f"sends_per_run={emails_sent}"
            )

            # 2026-09-18 fix: standing lost-lead sweep. Every drip run, drop any
            # lead marked lost from the MailerCloud Leads list so stopped
            # sequence emails (which live on the MC side, outside the code
            # queries above) stop too. Idempotent: a lead is only processed
            # until mailercloud_removed_at is set. Covers manual lost-marks made
            # in the admin (Jeff's wrong-number/bad-number call notes) and the
            # 3 leads already lost before this fix shipped.
            try:
                lost_leads = await self.db.leads.find({
                    "stage": "lost",
                    "mailercloud_removed_at": {"$in": [None, False]},
                    "email": {"$exists": True, "$ne": ""},
                }, {"_id": 0, "lead_id": 1, "email": 1}).to_list(200)
                removed = 0
                for lost in lost_leads:
                    r = await remove_contact_from_list(
                        email=lost["email"],
                        list_id=MAILERCLOUD_LEADS_LIST_ID,
                        list_name="TrustOffice Leads",
                    )
                    if r.get("success"):
                        await self.db.leads.update_one(
                            {"lead_id": lost["lead_id"]},
                            {"$set": {
                                "mailercloud_removed_at": now.isoformat(),
                                "updated_at": now.isoformat(),
                            }}
                        )
                        await self._log_drip_activity(
                            lost["lead_id"], "mailercloud_removed",
                            "Removed from MailerCloud Leads list (lead marked lost)",
                        )
                        removed += 1
                if removed:
                    logger.info(f"[drip-metric] lost-lead sweep removed {removed} from MailerCloud Leads")
            except Exception as e:
                logger.error(f"Lost-lead MailerCloud sweep failed (non-fatal): {e}")

            return emails_sent

        except Exception as e:
            logger.error(f"Error in nurture drip: {e}")
            return 0

    async def _log_drip_activity(self, lead_id, action_type, content):
        """Write a lead_activities row with a BSON Date created_at (item 5)."""
        await self.db.lead_activities.insert_one({
            "activity_id": f"act_{uuid.uuid4().hex[:12]}",
            "lead_id": lead_id,
            "action_type": action_type,
            "content": content,
            "created_at": datetime.now(timezone.utc),
        })

    async def send_booking_reminder_emails(self) -> Dict[str, int]:
        """Send day-before + 1-hour booking reminders for booked calls (item 2).

        Reads booked_call_at from the CRM leads collection (same DB as nurture,
        already synced from TidyCal every 5 min by sync_tidycal_bookings) so there
        is no cross-instance dependency on the booking-trustoffice Mongo.

        Runs hourly. Idempotent via reminder_day_before_sent_at /
        reminder_1h_sent_at flags per lead. Templates are Kenneth-signed and
        consistent with the existing booking_confirmation style.
        """
        logger.info("Running booking reminder check")
        result: Dict[str, int] = {"day_before": 0, "one_hour": 0}
        try:
            from email_service import email_service

            if not email_service.is_configured:
                logger.warning("Email service not configured, skipping booking reminders")
                return result

            now = datetime.now(timezone.utc)
            leads = await self.db.leads.find(
                {"booked_call": True, "booked_call_at": {"$exists": True, "$ne": None}},
                {"_id": 0},
            ).to_list(2000)

            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(BOOKING_TZ)
            except Exception:
                tz = timezone.utc

            for lead in leads:
                try:
                    booked_at = _as_dt(lead.get("booked_call_at"))
                    if booked_at is None:
                        continue
                    lead_id = lead.get("lead_id")
                    email = lead.get("email")
                    if not email:
                        continue

                    local_dt = booked_at.astimezone(tz)
                    data = {
                        "name": lead.get("name", ""),
                        "call_date": local_dt.strftime("%A, %B %d, %Y"),
                        "call_time": local_dt.strftime("%-I:%M %p"),
                        "timezone": BOOKING_TZ.replace("_", " "),
                        "meeting_url": lead.get("meeting_url")
                        or (email_service.app_url + "/meeting"),
                    }

                    if (
                        now + BOOKING_DAY_BEFORE_LOWER <= booked_at <= now + BOOKING_DAY_BEFORE_UPPER
                        and not lead.get("reminder_day_before_sent_at")
                    ):
                        r = await email_service.send_booking_reminder_day_before(
                            to_email=email, **data
                        )
                        if r.get("success"):
                            await self.db.leads.update_one(
                                {"lead_id": lead_id},
                                {"$set": {"reminder_day_before_sent_at": now.isoformat()}},
                            )
                            await self._log_drip_activity(
                                lead_id, "booking_reminder_day_before",
                                "Sent day-before booking reminder",
                            )
                            result["day_before"] += 1

                    if (
                        now + BOOKING_ONE_HOUR_LOWER <= booked_at <= now + BOOKING_ONE_HOUR_UPPER
                        and not lead.get("reminder_1h_sent_at")
                    ):
                        r = await email_service.send_booking_reminder_1h(
                            to_email=email, **data
                        )
                        if r.get("success"):
                            await self.db.leads.update_one(
                                {"lead_id": lead_id},
                                {"$set": {"reminder_1h_sent_at": now.isoformat()}},
                            )
                            await self._log_drip_activity(
                                lead_id, "booking_reminder_1h",
                                "Sent 1-hour booking reminder",
                            )
                            result["one_hour"] += 1
                except Exception as e:
                    logger.error(
                        f"Booking reminder failed for {lead.get('email')}: {e}"
                    )

            logger.info(
                f"[booking-reminder] day_before={result['day_before']} "
                f"one_hour={result['one_hour']} eligible={len(leads)}"
            )
            return result
        except Exception as e:
            logger.error(f"Error in booking reminders: {e}")
            return result

    async def send_post_drip_reengagement(self) -> int:
        """One-time re-engagement for leads that completed the 12-email drip but
        are still stage=new with zero follow-up (item 3). Uses a distinct
        template from the nurture sequence. Idempotent via post_drip_reengaged_at.
        """
        logger.info("Running post-drip re-engagement check")
        try:
            from email_service import email_service

            if not email_service.is_configured:
                logger.warning("Email service not configured, skipping post-drip re-engagement")
                return 0

            now = datetime.now(timezone.utc)
            leads = await self.db.leads.find({
                "nurture_step_sent": {"$gte": 12},
                "stage": "new",
                "post_drip_reengaged_at": {"$in": [None, False]},
            }, {"_id": 0}).to_list(2000)

            sent = 0
            for lead in leads:
                try:
                    r = await email_service.send_post_drip_reengagement(
                        to_email=lead["email"],
                        name=lead.get("name", ""),
                        course_url=f"{email_service.app_url}/trustee-101",
                        booking_url=f"{email_service.app_url}/book",
                    )
                    if r.get("success"):
                        await self.db.leads.update_one(
                            {"lead_id": lead.get("lead_id")},
                            {"$set": {
                                "stage": "post_drip",
                                "post_drip_reengaged_at": now.isoformat(),
                            }},
                        )
                        await self._log_drip_activity(
                            lead.get("lead_id"), "post_drip_reengagement",
                            "Sent one-time post-drip re-engagement email",
                        )
                        sent += 1
                except Exception as e:
                    logger.error(
                        f"Post-drip re-engagement failed for {lead.get('email')}: {e}"
                    )

            logger.info(f"[post-drip] reengaged={sent} eligible={len(leads)}")
            return sent
        except Exception as e:
            logger.error(f"Error in post-drip re-engagement: {e}")
            return 0

    async def backfill_lead_activities_dates(self) -> int:
        """Backfill lead_activities.created_at ISO strings to BSON Dates (item 5).

        New writes use BSON Date; this converts existing string docs. Idempotent:
        only touches docs where created_at is currently a string; once converted
        the $type filter matches nothing.
        """
        try:
            now = datetime.now(timezone.utc)
            try:
                cursor = self.db.lead_activities.find(
                    {"created_at": {"$type": "string"}}, {"_id": 1, "created_at": 1}
                )
                docs = await cursor.to_list(5000)
            except Exception:
                # Fallback for drivers/mocks without $type support: scan + filter.
                cursor = self.db.lead_activities.find(
                    {"created_at": {"$exists": True}}, {"_id": 1, "created_at": 1}
                )
                docs = await cursor.to_list(5000)
                docs = [d for d in docs if isinstance(d.get("created_at"), str)]

            converted = 0
            for doc in docs:
                dt = _as_dt(doc.get("created_at"))
                if dt is None:
                    continue
                await self.db.lead_activities.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "created_at": dt,
                        "created_at_backfilled_at": now.isoformat(),
                    }},
                )
                converted += 1

            logger.info(
                f"[backfill] lead_activities created_at strings->Date: {converted}"
            )
            return converted
        except Exception as e:
            logger.error(f"Error backfilling lead_activities dates: {e}")
            return 0

    async def check_leads_pipeline_health(self) -> dict:
        """Run the leads pipeline monitor asserts and RED-alert on failure (item 4)."""
        from leads_monitor import check_leads_pipeline_health as _run
        return await _run(self.db)

    async def check_compliance_reminder_health(self) -> dict:
        """Run the state-compliance reminder monitor asserts + RED-alert (item 4)."""
        from compliance_monitor import check_compliance_reminder_health as _run
        return await _run(self.db)

    async def create_daily_health_snapshots(self) -> int:
        """
        Create daily health score snapshots for all trusts.
        This enables historical tracking and trend analysis.
        """
        logger.info("Running daily health snapshot job")

        try:
            # Demo trusts go stale at every quarter rollover (their seeded
            # minutes age out of the current quarter and the health score
            # craters — reported by Jeff 2026-09-18). Before scoring, top up
            # demo trusts that have no minutes in the current quarter with a
            # fresh quarterly demo minute. Non-demo trusts are untouched.
            topped_up = await self._top_up_demo_quarterly_minutes()
            if topped_up:
                logger.info(f"[demo-evergreen] inserted {topped_up} quarterly demo minutes")

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

    async def _top_up_demo_quarterly_minutes(self) -> int:
        """Evergreen demo minutes (Jeff approved 2026-09-19).

        Demo trusts otherwise sag every quarter rollover: their seeded minutes
        age out of the current quarter, Quarterly Minutes drops to 0/15 and the
        health score craters — reported by Jeff 2026-09-18 (Smith demo: 16→7).
        For each is_demo trust with zero minutes dated in the current quarter,
        insert one demo quarterly minute dated inside this quarter. Non-demo
        trusts are never touched.
        """
        from routers.governance import get_quarter_start

        now = datetime.now(timezone.utc)
        quarter_start_iso = get_quarter_start(now).isoformat()
        inserted = 0

        try:
            demo_trusts = await self.db.trusts.find(
                {"is_demo": True}, {"_id": 0, "trust_id": 1, "user_id": 1, "name": 1}
            ).to_list(500)

            for trust in demo_trusts:
                trust_id, user_id = trust["trust_id"], trust["user_id"]
                try:
                    in_quarter = await self.db.minutes_records.count_documents({
                        "trust_id": trust_id,
                        "user_id": user_id,
                        "created_at": {"$gte": quarter_start_iso},
                    })
                    if in_quarter > 0:
                        continue

                    await self.db.minutes_records.insert_one({
                        "minutes_id": f"minutes_{uuid.uuid4().hex[:12]}",
                        "trust_id": trust_id,
                        "user_id": user_id,
                        "minutes_type": "quarterly",
                        "meeting_date": now.isoformat(),
                        "participants_text": "Demo Trustee (auto-generated quarterly review)",
                        "decisions_text": (
                            "DEMO RECORD (auto-generated): Quarterly review. Reviewed trust "
                            "performance, Schedule A accuracy, and upcoming governance calendar. "
                            "Demo data — not a real trustee action."
                        ),
                        "created_at": now.isoformat(),
                        "is_demo": True,
                    })
                    inserted += 1
                except Exception as e:
                    logger.error(f"[demo-evergreen] top-up failed for {trust_id}: {e}")

        except Exception as e:
            logger.error(f"[demo-evergreen] top-up sweep failed: {e}")
        return inserted

    async def send_deadline_reminders(self) -> dict:
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
                logger.warning("Email service not configured â skipping deadline + compliance reminders")
                return {"task_deadlines": 0, "compliance": 0}

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

                    # Tax-exempt trusts (benevolence mode, 508, or 501c3) don't
                    # file income tax returns — never remind on those deadlines.
                    from utils.tax_calendar_math import is_tax_exempt
                    if deadline.get("category") in (
                        "tax_filing_1041", "tax_filing_k1", "estimated_tax_payment",
                    ) and is_tax_exempt(trust):
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

            compliance_count = await self.send_compliance_deadline_reminders()
            logger.info(
                f"Deadline reminders complete: task={reminders_sent}, compliance={compliance_count}"
            )
            return {"task_deadlines": reminders_sent, "compliance": compliance_count}

        except Exception as e:
            logger.error(f"Error in deadline reminder job: {e}")
            return {"task_deadlines": 0, "compliance": 0}

    async def send_compliance_deadline_reminders(self) -> int:
        """Scan trust_state_compliance for upcoming/overdue state-compliance
        deadlines (beneficiary notice + annual accounting) and send reminder
        emails. Each (field, episode) reminder fires at most once via a per-field
        sent-marker stored in compliance_reminder_sent (a dict mapping
        'notice'/'accounting' to a list of threshold markers, e.g. 'upcoming'
        and 'overdue'), added with $addToSet so it never repeats daily.

        Returns the number of reminder emails sent.
        """
        logger.info("Running state-compliance deadline reminder job")

        try:
            from email_service import email_service

            if not email_service.is_configured:
                logger.warning("Email service not configured Ã¢ÂÂ skipping compliance reminders")
                return 0

            today = datetime.now(timezone.utc).date()
            reminders_sent = 0

            # All state-compliance records. We filter in Python for transition
            # robustness (mirrors send_deadline_reminders), since the per-field
            # "is this a real date" check is non-trivial.
            cursor = self.db.trust_state_compliance.find({}, {"_id": 0})
            records = await cursor.to_list(5000)

            # Cache lookups (same pattern as send_deadline_reminders).
            trust_cache: dict = {}
            user_cache: dict = {}

            for rec in records:
                try:
                    if not rec.get("trust_id"):
                        continue

                    sent_markers = rec.get("compliance_reminder_sent") or {}
                    compliance_id = rec.get("compliance_id") or (
                        f"sc_{rec.get('trust_id')}_{rec.get('state_code')}"
                    )

                    for field in ("notice", "accounting"):
                        due_raw = rec.get(f"{field}_next_due")
                        # Treat ('null', None, missing, '') as "no deadline".
                        if due_raw in (None, "null", "", "None"):
                            continue
                        try:
                            due = datetime.fromisoformat(str(due_raw)[:10]).date()
                        except (ValueError, TypeError):
                            continue

                        days_remaining = (due - today).days
                        # Remind only inside the 30-day upcoming window, or when
                        # overdue. Later than 30 days out -> not yet in scope.
                        if days_remaining > 30:
                            continue
                        marker = "overdue" if days_remaining < 0 else "upcoming"

                        field_markers = set(sent_markers.get(field, []) or [])
                        if marker in field_markers:
                            continue  # already reminded for this episode

                        # Resolve trust (cached).
                        trust_id = rec.get("trust_id")
                        if trust_id not in trust_cache:
                            trust_cache[trust_id] = await self.db.trusts.find_one(
                                {"trust_id": trust_id}, {"_id": 0}
                            )
                        trust = trust_cache[trust_id]
                        if not trust:
                            continue

                        # Resolve recipient user (cached).
                        user_id = trust.get("user_id")
                        if user_id not in user_cache:
                            user_cache[user_id] = await self.db.users.find_one(
                                {"user_id": user_id}, {"_id": 0}
                            )
                        recipient = user_cache[user_id]
                        if not recipient or not recipient.get("email"):
                            continue

                        act = (
                            "beneficiary notice"
                            if field == "notice"
                            else "annual accounting"
                        )
                        state_code = (
                            rec.get("state_code") or trust.get("state_code") or ""
                        )
                        state_name = (
                            trust.get("state_name")
                            or rec.get("state_name")
                            or ""
                        )

                        template_data = {
                            "user_name": recipient.get("name")
                            or recipient.get("email").split("@")[0],
                            "trust_name": trust.get("trust_name", "your trust"),
                            "state_code": state_code,
                            "state_name": state_name,
                            "act": act,
                            "due_date": due.isoformat(),
                            "is_overdue": days_remaining < 0,
                        }
                        if days_remaining < 0:
                            template_data["days_overdue"] = abs(days_remaining)
                        else:
                            template_data["days_remaining"] = days_remaining

                        await email_service.send_templated_email(
                            to_email=recipient["email"],
                            template_name="compliance_deadline_reminder",
                            template_data=template_data,
                            to_name=recipient.get("name"),
                            tag="compliance_reminder",
                        )

                        # Mark this episode as reminded (idempotent via $addToSet).
                        await self.db.trust_state_compliance.update_one(
                            {"trust_id": trust_id, "state_code": state_code},
                            {
                                "$addToSet": {f"compliance_reminder_sent.{field}": marker},
                                "$set": {
                                    "updated_at": datetime.now(timezone.utc).isoformat()
                                },
                            },
                        )

                        # Audit trail so the health monitor can detect recent sends.
                        try:
                            await self._log_audit(
                                user_id,
                                "compliance_reminder_sent",
                                "trust_state_compliance",
                                compliance_id,
                                {"field": field, "act": act, "due_date": due.isoformat()},
                            )
                        except Exception:
                            pass

                        reminders_sent += 1

                except Exception as e:
                    logger.error(
                        f"Failed to send compliance reminder for {rec.get('trust_id')}: {e}"
                    )

            logger.info(
                f"Compliance deadline reminders complete: {reminders_sent} emails sent"
            )
            return reminders_sent

        except Exception as e:
            logger.error(f"Error in compliance deadline reminder job: {e}")
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


async def run_deadline_reminders() -> dict:
    """Manual trigger for deadline reminders"""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]

    try:
        result = await runner.send_deadline_reminders()
        return result
    finally:
        runner.client.close()


# ---- Item 2/3/4/5 manual triggers ----------------------------------------


async def run_booking_reminders():
    """Manual trigger for booking reminders (item 2)."""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    try:
        return await runner.send_booking_reminder_emails()
    finally:
        runner.client.close()


async def run_post_drip_reengagement() -> int:
    """Manual trigger for post-drip re-engagement (item 3)."""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    try:
        return await runner.send_post_drip_reengagement()
    finally:
        runner.client.close()


async def run_leads_pipeline_health() -> dict:
    """Manual trigger for the pipeline health monitor (item 4)."""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    try:
        return await runner.check_leads_pipeline_health()
    finally:
        runner.client.close()


async def run_compliance_reminder_health() -> dict:
    """Manual trigger for the state-compliance reminder health monitor (item 4)."""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    try:
        return await runner.check_compliance_reminder_health()
    finally:
        runner.client.close()


async def run_backfill_activity_dates() -> int:
    """Manual trigger for the lead_activities date backfill (item 5)."""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    try:
        return await runner.backfill_lead_activities_dates()
    finally:
        runner.client.close()