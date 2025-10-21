from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import pytz

scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Tashkent"))

def start_scheduler():
    if not scheduler.running:
        scheduler.start()

def add_task(func, run_time):
    trigger = CronTrigger.from_crontab(run_time)
    scheduler.add_job(func, trigger)

async def restart_scheduler():
    if scheduler.running:
        scheduler.shutdown()
    await asyncio.sleep(1)
    start_scheduler()
