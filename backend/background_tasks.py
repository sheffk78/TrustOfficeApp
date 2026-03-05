"""
Background Tasks for TrustOffice
Scheduled jobs for task reminders, status updates, and maintenance
Uses APScheduler for scheduling background jobs
"""

import asyncio
import logging
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
        
        self.scheduler.start()
        logger.info("Background task runner started with APScheduler")
        
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
                
                # Get user's trusts
                trusts = await self.db.trusts.find(
                    {"user_id": user_id},
                    {"_id": 0}
                ).to_list(100)
                
                for trust in trusts:
                    trust_id = trust["trust_id"]
                    trust_name = trust.get("name", "")
                    
                    # Get incomplete tasks
                    tasks = await self.db.governance_tasks.find({
                        "trust_id": trust_id,
                        "user_id": user_id,
                        "completed_at": None
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
        """Internal method to calculate health score (duplicated from server to avoid circular imports)"""
        import uuid
        
        now = datetime.now(timezone.utc)
        total_score = 0
        
        # 1. Quarterly Minutes (+20)
        quarter = (now.month - 1) // 3
        quarter_start = datetime(now.year, quarter * 3 + 1, 1, tzinfo=timezone.utc)
        quarterly_minutes = await self.db.minutes_records.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "created_at": {"$gte": quarter_start.isoformat()}
        })
        if quarterly_minutes > 0:
            total_score += 20
        
        # 2. Task Compliance (+20)
        overdue_tasks = await self.db.governance_tasks.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "completed_at": None,
            "due_date": {"$lt": now.isoformat()}
        })
        if overdue_tasks == 0:
            total_score += 20
        
        # 3. Compensation Alignment (+20)
        year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        comp_plan = await self.db.compensation_plans.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0},
            sort=[("effective_date", -1)]
        )
        
        if comp_plan:
            ytd_payments = await self.db.compensation_payments.find(
                {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start.isoformat()}},
                {"_id": 0}
            ).to_list(1000)
            ytd_total = sum(p.get("amount", 0) for p in ytd_payments)
            if ytd_total <= comp_plan.get("annual_approved_amount", 0):
                total_score += 20
        else:
            total_score += 20
        
        # 4. Distribution Documentation (+20)
        dist_count = await self.db.distribution_records.count_documents({
            "trust_id": trust_id,
            "user_id": user_id
        })
        if dist_count > 0:
            total_score += 20
        
        # 5. Annual Review (+20)
        one_year_ago = (now - timedelta(days=365)).isoformat()
        annual_review = await self.db.governance_tasks.find_one({
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "annual_review",
            "completed_at": {"$gte": one_year_ago}
        }, {"_id": 0})
        if annual_review:
            total_score += 20
        
        # Determine color
        if total_score >= 80:
            color = "green"
        elif total_score >= 60:
            color = "yellow"
        else:
            color = "red"
        
        # Save snapshot
        snapshot = {
            "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "score_value": total_score,
            "color": color,
            "calculated_at": now.isoformat()
        }
        await self.db.health_score_snapshots.insert_one(snapshot)
        
        return {"total_score": total_score, "color": color}
    
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
