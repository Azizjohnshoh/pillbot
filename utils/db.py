
import aiosqlite, os
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
    time TEXT,
    recurring TEXT,
    snooze_until TEXT,
    active INTEGER DEFAULT 1
);
'''.strip()

async def ensure_schema(path=DB):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        for stmt in SCHEMA.split(';'):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()

async def list_reminders_for_chat(telegram_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute('SELECT id, title, note, time, recurring FROM reminders WHERE user_id=(SELECT id FROM users WHERE telegram_id=?)', (telegram_id,))
        rows = await cur.fetchall()
        return [dict(id=r[0], title=r[1], note=r[2], time=r[3], recurring=r[4]) for r in rows]
