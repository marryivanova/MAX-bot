import atexit
import sys
import time

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.services.monitoring import run_pull_report
from db.crud_db import sync_templates_from_google_to_db
from db.crud_db.update_lms_id import update_lms_id_max_orm

scheduler = BackgroundScheduler(job_defaults=dict(coalesce=True, misfire_grace_time=3600, max_instances=1))


def job_listener(event):
    if event.exception:
        logger.error(f"Job {event.job_id} failed: {event.exception}")
    else:
        logger.info(f"Job {event.job_id} executed successfully at {event.scheduled_run_time}")


scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

try:
    scheduler.add_job(
        func=update_lms_id_max_orm,
        trigger=IntervalTrigger(hours=1),
        id="update_lms_id_max",
        name="Update LMS ID Max every hour",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        func=sync_templates_from_google_to_db,
        trigger=CronTrigger(hour=7, minute=0),
        id="update_templates_from_google_to_db",
        name="Update SID 7 am",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        func=run_pull_report,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="run_pull_report",
        name="Pull Report Max ID discrepancies to chat",
        replace_existing=True,
        max_instances=1,
    )
    logger.success("Job 'update_lms_id_max' added successfully. Will run every hour.")

except Exception as e:
    logger.error(f"Failed to add job: {e}", exc_info=True)
    raise

try:
    scheduler.start()
    logger.success("BackgroundScheduler started successfully")

    for job_id in ["update_lms_id_max", "update_templates_from_google_to_db", "run_pull_report"]:
        job = scheduler.get_job(job_id)
        if job and job.next_run_time:
            logger.info(f"Job '{job_id}' next execution at: {job.next_run_time}")
        else:
            logger.warning(f"Job '{job_id}' exists but next run time is not available")

except Exception as e:
    logger.error(f"Failed to start scheduler: {e}", exc_info=True)
    raise


def shutdown_scheduler():
    if scheduler.running:
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown complete")


atexit.register(shutdown_scheduler)
logger.debug("atexit handler registered for scheduler shutdown")

logger.debug(f"Scheduler running: {scheduler.running}")
logger.debug(f"Registered jobs: {len(scheduler.get_jobs())}")


if __name__ == "__main__":
    logger.info("🔄 Scheduler is now running and will keep the container alive")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("⚠️ Received shutdown signal")
        shutdown_scheduler()
        sys.exit(0)
