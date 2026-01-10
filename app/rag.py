from typing import List, Tuple, Optional
from datetime import datetime
import psycopg
from psycopg.types.json import Json
from openai import OpenAI

from app.config import settings
from app.db import get_conn, vector_search, normalize_org_id, normalize_bot_id

# Initialize OpenAI client
_openai_client = None


def _get_openai_client():
    """Get or create OpenAI client for embeddings"""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _unload_model():
    """No-op for API-based embeddings (kept for backward compatibility)"""
    pass


def _check_and_unload_if_idle():
    """No-op for API-based embeddings (kept for backward compatibility)"""
    return False


def embed_text(text: str) -> List[float]:
    """Generate embeddings using OpenAI API"""
    try:
        client = _get_openai_client()
        response = client.embeddings.create(
            input=text,
            model=settings.EMBEDDING_MODEL_NAME
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"❌ [RAG] Error generating OpenAI embedding: {e}", flush=True)
        raise


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    chunks: List[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += chunk_size - overlap
    return chunks


def store_embedding(org_id: str, bot_id: str, content: str, embedding: List[float], metadata: Optional[dict] = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            oid = normalize_org_id(org_id)
            bid = normalize_bot_id(bot_id)
            try:
                cur.execute("select 1 from organizations where id=%s", (oid,))
                r = cur.fetchone()
                if not r:
                    cur.execute("insert into organizations (id, name) values (%s,%s)", (oid, org_id))
            except Exception:
                pass
            cur.execute(
                "insert into rag_embeddings (org_id, bot_id, content, embedding, metadata, created_at) values (%s,%s,%s,%s::vector,%s,%s)",
                (oid, bid, content, embedding, Json(metadata) if metadata is not None else None, datetime.utcnow()),
            )


def search_top_chunks(org_id: str, bot_id: str, query: str, top_k: int) -> List[Tuple[str, dict, float]]:
    qvec = embed_text(query)
    rows = vector_search(org_id, bot_id, qvec, k=top_k)
    return rows
