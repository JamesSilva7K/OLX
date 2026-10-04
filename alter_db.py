import sqlite3

db = sqlite3.connect(r'd:\OLPG\olpg_logs.db')
c = db.cursor()

columns = [
    'seller_sales_completed TEXT',
    'seller_sales_canceled TEXT',
    'seller_dispatch_time TEXT',
    'seller_rating TEXT',
    'seller_reviews TEXT',
    'seller_level TEXT',
    'seller_email_verified INTEGER DEFAULT 1',
    'seller_phone_verified INTEGER DEFAULT 1',
    'seller_id_verified INTEGER DEFAULT 1',
    'seller_fb_verified INTEGER DEFAULT 0',
    'seller_fb_url TEXT'
]

for col in columns:
    try:
        c.execute(f"ALTER TABLE tenant_products ADD COLUMN {col}")
        print(f"Added {col}")
    except sqlite3.OperationalError as e:
        print(f"Skipped {col}: {e}")

db.commit()
db.close()
