from app.db.postgres import embed_search, get_conn
from app.services.embeddings import embed_text


def build_prompt(context_chunks: list[tuple], user_query: str, bot_behavior: str, system_prompt: str | None):
    ctx = "\n\n".join([c[0] for c in context_chunks])
    if system_prompt:
        system = system_prompt + " Keep responses short and informative."
    else:
        system = (
            f"You are a {bot_behavior} assistant. Use only the provided context. If the answer is not in context, say: \"I don't have that information.\" Keep responses short and informative."
        )
    user = f"Context:\n{ctx}\n\nQuestion:\n{user_query}"
    return system, user


def rag_query(org_id: str, bot_id: str, user_query: str, k: int, min_sim: float, bot_behavior: str, system_prompt: str | None):
    conn = get_conn()
    try:
        qvec = embed_text(user_query)
        rows = embed_search(conn, org_id, bot_id, qvec, k=k)
        rows = [r for r in rows if r[2] >= min_sim]
        if not rows:
            return None, None, "I don't have that information."
        return rows, qvec, None
    finally:
        conn.close()
