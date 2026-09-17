"""
Background Jobs router - Status and manual trigger endpoints for scheduled jobs
Migrated from server.py
"""
from fastapi import APIRouter, HTTPException, Depends
import logging

from dependencies import get_current_user
from background_tasks import (
    background_runner,
    run_task_status_update,
    run_daily_reminders,
    run_health_snapshots,
    run_booking_reminders,
    run_post_drip_reengagement,
    run_leads_pipeline_health,
    run_backfill_activity_dates,
)

router = APIRouter(prefix="/background-jobs", tags=["background-jobs"])
logger = logging.getLogger(__name__)


@router.get("/status")
async def get_background_jobs_status(user: dict = Depends(get_current_user)):
    """Get status of scheduled background jobs"""
    return {
        "running": background_runner.running,
        "jobs": background_runner.get_jobs_info(),
        "scheduler_active": background_runner.scheduler is not None and background_runner.scheduler.running if background_runner.scheduler else False
    }


@router.post("/run/task-status-update")
async def trigger_task_status_update(user: dict = Depends(get_current_user)):
    """Manually trigger task status update job"""
    try:
        updates = await run_task_status_update()
        return {
            "success": True,
            "message": "Task status update complete",
            "tasks_updated": updates
        }
    except Exception as e:
        logger.error(f"Error running task status update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/daily-reminders")
async def trigger_daily_reminders(user: dict = Depends(get_current_user)):
    """Manually trigger daily reminder emails job"""
    try:
        emails_sent = await run_daily_reminders()
        return {
            "success": True,
            "message": "Daily reminders sent",
            "emails_sent": emails_sent
        }
    except Exception as e:
        logger.error(f"Error running daily reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/health-snapshots")
async def trigger_health_snapshots(user: dict = Depends(get_current_user)):
    """Manually trigger health score snapshots job"""
    try:
        snapshots = await run_health_snapshots()
        return {
            "success": True,
            "message": "Health snapshots created",
            "snapshots_created": snapshots
        }
    except Exception as e:
        logger.error(f"Error running health snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/booking-reminders")
async def trigger_booking_reminders(user: dict = Depends(get_current_user)):
    """Manually trigger booking day-before + 1-hour reminders (item 2)."""
    try:
        result = await run_booking_reminders()
        return {"success": True, "message": "Booking reminders run", "result": result}
    except Exception as e:
        logger.error(f"Error running booking reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/post-drip-reengagement")
async def trigger_post_drip_reengagement(user: dict = Depends(get_current_user)):
    """Manually trigger post-drip re-engagement send (item 3)."""
    try:
        sent = await run_post_drip_reengagement()
        return {"success": True, "message": "Post-drip re-engagement run", "emails_sent": sent}
    except Exception as e:
        logger.error(f"Error running post-drip re-engagement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/leads-pipeline-health")
async def trigger_leads_pipeline_health(user: dict = Depends(get_current_user)):
    """Manually trigger the leads pipeline health monitor (item 4)."""
    try:
        result = await run_leads_pipeline_health()
        return {"success": True, "message": "Pipeline health check run", "result": result}
    except Exception as e:
        logger.error(f"Error running pipeline health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/backfill-activity-dates")
async def trigger_backfill_activity_dates(user: dict = Depends(get_current_user)):
    """Manually trigger lead_activities.created_at string->Date backfill (item 5)."""
    try:
        converted = await run_backfill_activity_dates()
        return {"success": True, "message": "Backfill run", "converted": converted}
    except Exception as e:
        logger.error(f"Error running backfill: {e}")
        raise HTTPException(status_code=500, detail=str(e))
