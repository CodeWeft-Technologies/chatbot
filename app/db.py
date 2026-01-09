import psycopg
from typing import Any, Sequence
import uuid
from app.config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _ensure_extensions(conn):
    """Ensure vector extension exists on this connection. Called for every connection."""
    try:
        with conn.cursor() as cur:
            # Ensure vector extension exists
            cur.execute('CREATE EXTENSION IF NOT EXISTS vector;')
            cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
            
            # Find which schema vector is in
            cur.execute("""
                SELECT n.nspname 
                FROM pg_extension e 
                JOIN pg_namespace n ON e.extnamespace = n.oid 
                WHERE e.extname = 'vector'
            """)
            vector_schema = cur.fetchone()
            
            if not vector_schema:
                logger.error("Vector extension not found after CREATE EXTENSION IF NOT EXISTS")
                raise Exception("Vector extension not available")
            
            schema_name = vector_schema[0]
            logger.info(f"Vector extension found in schema: {schema_name}")
            
            # Set search path to include vector schema
            if schema_name != 'public':
                cur.execute(f'SET search_path TO public, {schema_name};')
                logger.info(f"Search path set to: public, {schema_name}")
            else:
                cur.execute('SET search_path TO public;')
                logger.info("Search path set to: public")
            
            # Verify vector type is accessible
            cur.execute("SELECT typname FROM pg_type WHERE typname = 'vector'")
            if cur.fetchone():
                logger.info("Vector type confirmed accessible")
            else:
                logger.error("Vector type not accessible after setting search path")
                
    except Exception as e:
        logger.error(f"Failed to ensure extensions: {e}")
        raise


def get_conn():
    """Get database connection with vector extension ensured."""
    dsn = settings.SUPABASE_DB_DSN
    logger.info(f"Connecting to DB: {dsn[:80]}...")
    conn = psycopg.connect(dsn, autocommit=True)
    _ensure_extensions(conn)
    return conn


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
