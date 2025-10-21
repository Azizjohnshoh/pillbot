
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

log = logging.getLogger("pillbot.scheduler")
sched = AsyncIOScheduler()

def start_scheduler():
    if not sched.running:
        sched.start()

def schedule_daily(reminder_id, hour, minute, func, args=()):
    try:
        trigger = CronTrigger(hour=hour, minute=minute)
        sched.add_job(func, trigger, args=args, id=str(reminder_id), replace_existing=True)
    except Exception as e:
        log.exception("Failed to schedule: %s", e)

def schedule_ping(interval_minutes, func, args=()):
    try:
        sched.add_job(func, 'interval', minutes=interval_minutes, args=args, id='self_ping', replace_existing=True)
    except Exception as e:
        log.exception("Failed to schedule ping: %s", e)

def remove_job(job_id):
    try:
        sched.remove_job(job_id)
    except Exception:
        pass
