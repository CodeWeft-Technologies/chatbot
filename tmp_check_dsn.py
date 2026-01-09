import psycopg
from app.core.config import settings

print('DSN:', settings.SUPABASE_DB_DSN)
with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
    with conn.cursor() as cur:
        cur.execute('select extname from pg_extension order by 1')
        print('Extensions:', [r[0] for r in cur.fetchall()])
