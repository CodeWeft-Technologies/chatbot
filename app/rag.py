from typing import List, Tuple, Optional
from datetime import datetime
import psycopg
from psycopg.types.json import Json
import gc

from app.config import settings
from app.db import get_conn, vector_search, normalize_org_id, normalize_bot_id

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

_model = None


def _get_model():
    global _model
    if _model is None and SentenceTransformer is not None:
        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


def _unload_model():
    """Free embedding model from memory to save RAM (~2GB)"""
    global _model
    if _model is not None:
        _model = None
        gc.collect()  # Force garbage collection


def embed_text(text: str) -> List[float]:
    model = _get_model()
    if model is None:
        import re, math
        dims = 1024
        v = [0.0] * dims
        t = (text or "").lower()
        tokens = re.findall(r"[a-z0-9]+", t)
        for tok in tokens:
            h = hash(tok) % dims
            v[h] += 1.0
        s = math.sqrt(sum(x*x for x in v))
        if s > 0:
            v = [x / s for x in v]
        return v
    vec = model.encode([text], normalize_embeddings=True)[0]
    return vec.tolist()


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
