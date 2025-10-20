
from apscheduler.schedulers.asyncio import AsyncIOScheduler
sched = AsyncIOScheduler()
def start_scheduler():
    if not sched.running:
        sched.start()
def schedule_reminder(reminder_id, when, callback, args=()):
    try:
        sched.add_job(callback, 'date', run_date=when, args=args, id=str(reminder_id))
    except Exception:
        pass
