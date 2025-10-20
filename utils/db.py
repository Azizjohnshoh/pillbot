
"""Async DB helpers for PillBot (example schema creation)"""
import aiosqlite, asyncio

DB = "data/pillbot.db"

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    timezone TEXT DEFAULT 'Asia/Tashkent'
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT,
    note TEXT,
    time TEXT,         -- ISO format
    recurring TEXT,    -- 'daily' or NULL
    snooze_until TEXT, -- ISO or NULL
    active INTEGER DEFAULT 1
);
'''.strip()

async def ensure_schema(path=DB):
    async with aiosqlite.connect(path) as db:
        for stmt in SCHEMA.split(';'):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()

if __name__ == '__main__':
    asyncio.run(ensure_schema())
