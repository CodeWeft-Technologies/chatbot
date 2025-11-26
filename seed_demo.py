import psycopg
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

dsn = os.getenv("SUPABASE_DB_DSN")
org_id = str(uuid.uuid4())
user_id = str(uuid.uuid4())
bot_id = str(uuid.uuid4())

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("insert into organizations (id, name) values (%s, %s)", (org_id, "Demo Org"))
        cur.execute("insert into users (id, email, display_name) values (%s, %s, %s)", (user_id, "demo@example.com", "Demo User"))
        cur.execute("insert into organization_users (org_id, user_id, role) values (%s, %s, %s)", (org_id, user_id, "owner"))
        cur.execute(
            "insert into chatbots (id, org_id, name, behavior, system_prompt, created_by) values (%s, %s, %s, %s, %s, %s)",
            (bot_id, org_id, "Support Bot", "support", "You are a helpful support assistant. Only use the provided context.", user_id)
        )
        print(f"org_id={org_id}")
        print(f"user_id={user_id}")
        print(f"bot_id={bot_id}")