from app.db import get_conn
conn = get_conn()
with conn.cursor() as cur:
    cur.execute("select id, org_id, behavior from chatbots")
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"Bot ID: {row[0]}, Org ID: {row[1]}, Behavior: {row[2]}")
    else:
        print("No bots found")
