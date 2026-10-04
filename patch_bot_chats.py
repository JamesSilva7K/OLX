import sqlite3
import os

DB_PATH = r"d:\OLPG\olpg_logs.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS bot_chats (
    chat_id TEXT PRIMARY KEY,
    title TEXT,
    type TEXT,
    is_forum INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS bot_topics (
    chat_id TEXT,
    thread_id TEXT,
    title TEXT,
    PRIMARY KEY(chat_id, thread_id)
)
""")
conn.commit()
conn.close()
print("Tables created.")
