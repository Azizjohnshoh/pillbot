
import aiosqlite, os, datetime, json
DB = "data/pillbot.db"
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    name TEXT,
    language TEXT DEFAULT 'uz',
    voice_enabled INTEGER DEFAULT 1,
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
CREATE TABLE IF NOT EXISTS user_state (
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    temp_data TEXT,
    updated_at TEXT
);
'''.strip()

async def ensure_schema(path=DB):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        for stmt in SCHEMA.split(';'):
            s = stmt.strip()
            if s:
                await db.execute(s)
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

# state helpers
async def set_state(telegram_id, state, temp_data=None):
    now = datetime.datetime.utcnow().isoformat()
    td = json.dumps(temp_data) if temp_data is not None else None
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO user_state (user_id,state,temp_data,updated_at) VALUES ((SELECT id FROM users WHERE telegram_id=?),?,?,?)",
                         (telegram_id, state, td, now))
        await db.commit()

async def get_state(telegram_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT state,temp_data FROM user_state WHERE user_id=(SELECT id FROM users WHERE telegram_id=?)", (telegram_id,))
        row = await cur.fetchone()
        if not row:
            return None, None
        state = row[0]
        td = json.loads(row[1]) if row[1] else None
        return state, td

async def clear_state(telegram_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM user_state WHERE user_id=(SELECT id FROM users WHERE telegram_id=?)", (telegram_id,))
        await db.commit()

async def add_reminder(telegram_id, title, time_str, recurring=None):
    user_id = await ensure_user(telegram_id)
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("INSERT INTO reminders (user_id,title,time,recurring,created_at) VALUES (?,?,?,?,?)", (user_id, title, time_str, recurring, now))
        await db.commit()
        return cur.lastrowid

async def list_reminders_for_chat(telegram_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute('SELECT r.id, r.title, r.time, r.recurring FROM reminders r JOIN users u ON r.user_id=u.id WHERE u.telegram_id=? ORDER BY r.time', (telegram_id,))
        rows = await cur.fetchall()
        return [dict(id=r[0], title=r[1], time=r[2], recurring=r[3]) for r in rows]

async def delete_reminder(reminder_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute('DELETE FROM reminders WHERE id=?', (reminder_id,))
        await db.commit()

async def get_user_prefs(telegram_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT language, voice_enabled FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        if not row:
            return 'uz', 1
        return row[0], row[1]

async def set_user_prefs(telegram_id, language=None, voice_enabled=None):
    async with aiosqlite.connect(DB) as db:
        if language is not None:
            await db.execute("UPDATE users SET language=? WHERE telegram_id=?", (language, telegram_id))
        if voice_enabled is not None:
            await db.execute("UPDATE users SET voice_enabled=? WHERE telegram_id=?", (1 if voice_enabled else 0, telegram_id))
        await db.commit()
