from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse
from app.services.groq_llm import chat_completion
from app.services.rag import rag_query, build_prompt
from app.core.config import settings
import psycopg

router = APIRouter()


def get_bot(conn, bot_id: str, org_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "select behavior, system_prompt from chatbots where id=%s and org_id=%s",
            (bot_id, org_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bot not found")
        return row[0], row[1]


@router.post("/chat/{bot_id}", response_model=ChatResponse)
def chat(bot_id: str, body: ChatRequest):
    org_id = body.org_id
    conn = psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True)
    try:
        behavior, system_prompt = get_bot(conn, bot_id, org_id)
        chunks, qvec, fallback = rag_query(
            org_id,
            bot_id,
            body.query,
            settings.MAX_CONTEXT_CHUNKS,
            settings.MIN_SIMILARITY,
            behavior,
            system_prompt,
        )
        if fallback:
            return ChatResponse(answer=fallback, citations=[], similarity=0.0)
        system, user = build_prompt(chunks, body.query, behavior, system_prompt)
        answer = chat_completion(system, user)
        citations = [c[0][:120] for c in chunks]
        return ChatResponse(answer=answer, citations=citations, similarity=float(chunks[0][2]))
    finally:
        conn.close()
