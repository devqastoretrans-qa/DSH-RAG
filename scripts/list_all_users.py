import json
import pymysql

conn = pymysql.connect(
    host="127.0.0.1",
    user="rag_user",
    password="DshRag_MySQL_2026_x8K2q",
    database="rag_users"
)

with conn.cursor() as cur:
    cur.execute("""
        SELECT u.id, u.name, u.email,
               GROUP_CONCAT(DISTINCT p.item_title SEPARATOR ';;;') AS items,
               COUNT(p.id) AS count
        FROM users u
        LEFT JOIN purchases p ON u.id = p.user_id
        GROUP BY u.id, u.name, u.email
        ORDER BY count DESC, u.name ASC;
    """)
    rows = cur.fetchall()

result = []
for r in rows:
    items_list = r[3].split(";;;") if r[3] else []
    result.append({
        "id": r[0],
        "name": r[1],
        "email": r[2],
        "purchases_count": r[4],
        "items": items_list
    })

conn.close()
print(json.dumps(result, indent=2))
