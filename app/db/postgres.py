import psycopg
from app.core.config import settings


def get_conn():
    return psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True)


def embed_search(conn, org_id, bot_id, query_vec, k=4):
    from app.db import normalize_org_id, normalize_bot_id
    org_n = normalize_org_id(org_id)
    bot_n = normalize_bot_id(bot_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            select content, metadata, 1 - (embedding <=> %s::vector) as similarity
            from rag_embeddings
            where org_id = %s and bot_id = %s
            order by embedding <-> %s::vector
            limit %s
            """,
            (query_vec, org_n, bot_n, query_vec, k),
        )
        return cur.fetchall()
