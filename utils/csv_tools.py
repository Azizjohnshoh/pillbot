
"""CSV export/import helpers (example)"""
import csv, sqlite3

def export_reminders_csv(db_path, out_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id, user_id, title, note, time, recurring FROM reminders')
    rows = cur.fetchall()
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id','user_id','title','note','time','recurring'])
        writer.writerows(rows)
    conn.close()

def import_reminders_csv(db_path, in_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    with open(in_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            cur.execute('INSERT INTO reminders (user_id,title,note,time,recurring) VALUES (?,?,?,?,?)',
                        (r['user_id'], r['title'], r['note'], r['time'], r.get('recurring')))
    conn.commit()
    conn.close()
