import sqlite3
db = sqlite3.connect(r'd:\OLPG\olpg_logs.db')
c = db.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(c.fetchall())
