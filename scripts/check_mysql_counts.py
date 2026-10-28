import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.getenv("MYSQL_HOST", "127.0.0.1"),
    user=os.getenv("MYSQL_USER", "rag_user"),
    password=os.getenv("MYSQL_PASSWORD", "").strip(),
    database=os.getenv("MYSQL_DATABASE", "rag_users")
)
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM users;")
    print("Users Count:", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM purchases;")
    print("Purchases Count:", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM past_records;")
    print("Past Records Count:", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM conversation_turns;")
    print("Conversation Turns Count:", cur.fetchone()[0])
    cur.execute("SELECT session_key, role, SUBSTRING(content, 1, 50) FROM conversation_turns ORDER BY id DESC LIMIT 2;")
    print("Latest turns:", cur.fetchall())
conn.close()
