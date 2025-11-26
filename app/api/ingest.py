from fastapi import APIRouter
from pydantic import BaseModel
import psycopg
from app.core.config import settings
from app.services.embeddings import chunk_text, embed_text

router = APIRouter()


class IngestRequest(BaseModel):
    org_id: str
    bot_id: str
    doc_id: str | None = None
    text: str


@router.post("/ingest/text")
def ingest_text(body: IngestRequest):
    chunks = chunk_text(body.text)
    conn = psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True)
    try:
        with conn.cursor() as cur:
            for i, c in enumerate(chunks):
                vec = embed_text(c)
                cur.execute(
                    "insert into rag_embeddings (org_id, bot_id, doc_id, chunk_id, content, embedding) values (%s,%s,%s,%s,%s,%s::vector)",
                    (body.org_id, body.bot_id, body.doc_id, i, c, vec),
                )
        return {"inserted": len(chunks)}
    finally:
        conn.close()
