"""
Background Tasks for TrustOffice
Scheduled jobs for task reminders, status updates, and maintenance
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
import os

logger = logging.getLogger(__name__)

# Configuration
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


class BackgroundTaskRunner:
    """
    Background task runner for scheduled jobs.
    Runs tasks at configurable intervals.
    """
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.running = False
        self._task = None
        
    async def start(self):
        """Start the background task runner"""
        if self.running:
            logger.warning("Background runner already running")
            return
            
        self.client = AsyncIOMotorClient(MONGO_URL)
        self.db = self.client[DB_NAME]
        self.running = True
        
        logger.info("Background task runner started")
        self._task = asyncio.create_task(self._run_loop())
        
    async def stop(self):
        """Stop the background task runner"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.client:
            self.client.close()
        logger.info("Background task runner stopped")
        
    async def _run_loop(self):
        """Main loop that runs scheduled tasks"""
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                
                # Run task status update every hour
                if now.minute == 0:
                    await self.update_task_statuses()
                
                # Run task reminders at 9 AM UTC daily
                if now.hour == 9 and now.minute == 0:
                    await self.send_daily_reminders()
                
                # Sleep for 1 minute before checking again
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background loop: {e}")
                await asyncio.sleep(60)
    
    async def update_task_statuses(self):
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
    
    async def send_daily_reminders(self):
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
                        
                        # Check if overdue
                        if task_due < today.isoformat():
                            try:
                                due_date_obj = datetime.fromisoformat(task_due).date()
                                days_overdue = (today - due_date_obj).days
                            except:
                                days_overdue = 1
                            
                            await email_service.send_task_overdue(
                                to_email=user_email,
                                user_name=user_name,
                                trust_name=trust_name,
                                task_type=task_type,
                                due_date=task_due,
                                days_overdue=days_overdue
                            )
                            emails_sent += 1
                            
                        # Check if upcoming (within 7 days)
                        elif task_due <= upcoming_cutoff:
                            await email_service.send_task_reminder(
                                to_email=user_email,
                                user_name=user_name,
                                trust_name=trust_name,
                                task_type=task_type,
                                due_date=task_due,
                                description=description
                            )
                            emails_sent += 1
            
            logger.info(f"Daily reminders complete: {emails_sent} emails sent")
            return emails_sent
            
        except Exception as e:
            logger.error(f"Error sending daily reminders: {e}")
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


async def run_task_status_update():
    """Manual trigger for task status update"""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    
    try:
        result = await runner.update_task_statuses()
        return result
    finally:
        runner.client.close()


async def run_daily_reminders():
    """Manual trigger for daily reminders"""
    runner = BackgroundTaskRunner()
    runner.client = AsyncIOMotorClient(MONGO_URL)
    runner.db = runner.client[DB_NAME]
    
    try:
        result = await runner.send_daily_reminders()
        return result
    finally:
        runner.client.close()
