
import aiosqlite, os, datetime
DB = "data/pillbot.db"
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    name TEXT,
    timezone TEXT DEFAULT 'Asia/Tashkent',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT,
    time TEXT,
    recurring TEXT,
    created_at TEXT
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

async def ensure_user(telegram_id, name=None):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        if row:
            return row[0]
        now = datetime.datetime.utcnow().isoformat()
        await db.execute("INSERT INTO users (telegram_id,name,created_at) VALUES (?,?,?)", (telegram_id, name or '', now))
        await db.commit()
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return row[0]

async def add_reminder(telegram_id, title, time_str, recurring=None):
    user_id = await ensure_user(telegram_id)
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("INSERT INTO reminders (user_id,title,time,recurring,created_at) VALUES (?,?,?,?,?)", (user_id, title, time_str, recurring, now))
        await db.commit()
        return cur.lastrowid

async def list_reminders_for_chat(telegram_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute('SELECT r.id, r.title, r.time, r.recurring FROM reminders r JOIN users u ON r.user_id=u.id WHERE u.telegram_id=?', (telegram_id,))
        rows = await cur.fetchall()
        return [dict(id=r[0], title=r[1], time=r[2], recurring=r[3]) for r in rows]

async def delete_reminder(reminder_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute('DELETE FROM reminders WHERE id=?', (reminder_id,))
        await db.commit()
