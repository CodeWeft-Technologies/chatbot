import psycopg
from typing import Any, Sequence
import uuid
from app.config import settings
from typing import Optional


def get_conn():
    return psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True)


def run_query(sql: str, params: Sequence[Any] = ()):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            try:
                return cur.fetchall()
            except psycopg.errors.NoData:  # pragma: no cover
                return []


def vector_search(org_id: str, bot_id: str, query_vec: list[float], k: int):
    org_n = normalize_org_id(org_id)
    bot_n = normalize_bot_id(bot_id)
    sql = (
        """
        select content, metadata, 1 - (embedding <=> %s::vector) as similarity
        from rag_embeddings
        where org_id = %s and bot_id = %s
        order by embedding <-> %s::vector
        limit %s
        """
    )
    return run_query(sql, (query_vec, org_n, bot_n, query_vec, k))


_RAG_ORG_IS_UUID: Optional[bool] = None
_RAG_BOT_IS_UUID: Optional[bool] = None


def _detect_rag_org_type():
    global _RAG_ORG_IS_UUID
    _RAG_ORG_IS_UUID = True


def normalize_org_id(org_id: str) -> str:
    try:
        return str(uuid.UUID(str(org_id)))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, str(org_id)))


def _detect_rag_bot_type():
    global _RAG_BOT_IS_UUID
    _RAG_BOT_IS_UUID = False


def normalize_bot_id(bot_id: str) -> str:
    return str(bot_id)
