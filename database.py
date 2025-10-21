import aiosqlite

DB_PATH = "pillbot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            time TEXT,
            repeat INTEGER DEFAULT 0
        )
        """)
        await db.commit()

async def add_reminder(user_id, text, time, repeat=0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO reminders (user_id, text, time, repeat) VALUES (?, ?, ?, ?)",
            (user_id, text, time, repeat)
        )
        await db.commit()

async def get_reminders(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, text, time, repeat FROM reminders WHERE user_id=?", (user_id,)) as cursor:
            return await cursor.fetchall()

async def delete_reminder(reminder_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
        await db.commit()
