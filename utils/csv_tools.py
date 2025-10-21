
import csv, sqlite3
def export_reminders_csv(db_path, out_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id, user_id, title, time, recurring FROM reminders')
    rows = cur.fetchall()
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id','user_id','title','time','recurring'])
        writer.writerows(rows)
    conn.close()
