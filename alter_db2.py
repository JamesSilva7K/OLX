import sqlite3

db = sqlite3.connect(r'd:\OLPG\olpg_logs.db')
c = db.cursor()
try:
    c.execute("ALTER TABLE tenant_products ADD COLUMN product_published_at TEXT")
    print("Added product_published_at")
except sqlite3.OperationalError as e:
    print(f"Skipped: {e}")
db.commit()
db.close()
