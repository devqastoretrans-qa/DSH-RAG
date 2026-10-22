import pymysql

conn = pymysql.connect(
    host="127.0.0.1",
    user="rag_user",
    password="DshRag_MySQL_2026_x8K2q",
    database="rag_users"
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
