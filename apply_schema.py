import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

dsn = os.getenv("SUPABASE_DB_DSN")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("create extension if not exists vector;")
        print("pgvector enabled")
        with open("../supabase/schema.sql", "r", encoding="utf-8") as f:
            cur.execute(f.read())
            print("schema applied")