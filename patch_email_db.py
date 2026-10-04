with open(r'd:\OLPG\tg_webhook.py', 'a', encoding='utf8') as f:
    f.write('''

# ─── MÓDULO DE EMAIL (TEMPLATES E LOGS) ──────────────────────────────────────────

def get_email_templates():
    conn = _get_db()
    rows = conn.execute("SELECT * FROM email_templates ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_email_template(title: str, html_content: str):
    conn = _get_db()
    conn.execute("INSERT INTO email_templates (title, html_content, created_at) VALUES (?, ?, ?)", (title, html_content, time.time()))
    conn.commit()
    conn.close()

def delete_email_template(template_id: int):
    conn = _get_db()
    conn.execute("DELETE FROM email_templates WHERE id=?", (template_id,))
    conn.commit()
    conn.close()

def log_email(admin_id: int, to_email: str, subject: str, status: str):
    conn = _get_db()
    conn.execute("INSERT INTO email_logs (admin_id, to_email, subject, status, sent_at) VALUES (?, ?, ?, ?, ?)", (admin_id, to_email, subject, status, time.time()))
    conn.commit()
    conn.close()

def get_email_logs(admin_id: int, limit: int = 50):
    conn = _get_db()
    rows = conn.execute("SELECT * FROM email_logs WHERE admin_id=? ORDER BY id DESC LIMIT ?", (admin_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_email_logs(limit: int = 200):
    conn = _get_db()
    rows = conn.execute("SELECT * FROM email_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
''')
print("Appended successfully.")
