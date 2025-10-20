
"""Example scheduler glue using APScheduler"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

sched = AsyncIOScheduler()

def start_scheduler():
    if not sched.running:
        sched.start()

def schedule_reminder(reminder_id, when, callback, args=()):
    sched.add_job(callback, 'date', run_date=when, args=args, id=str(reminder_id))
