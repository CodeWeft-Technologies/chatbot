from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List
from groq import Groq
from typing import Optional
from starlette.responses import StreamingResponse
from starlette.responses import PlainTextResponse
from fastapi.responses import HTMLResponse

from app.config import settings
from app.rag import search_top_chunks
from app.db import get_conn, normalize_org_id
from collections import defaultdict, deque
import time
import base64, json, hmac, hashlib, uuid, datetime


class ChatBody(BaseModel):
    message: str
    org_id: str

class KeyBody(BaseModel):
    org_id: str

class BotConfigBody(BaseModel):
    org_id: str
    behavior: str
    system_prompt: Optional[str] = None
    website_url: Optional[str] = None
    role: Optional[str] = None
    tone: Optional[str] = None
    welcome_message: Optional[str] = None

class CalendarConfigBody(BaseModel):
    org_id: str
    provider: str = "google"
    calendar_id: str
    timezone: Optional[str] = None

class CreateEventBody(BaseModel):
    org_id: str
    summary: str
    start_iso: str
    end_iso: str
    attendees: Optional[List[str]] = None

class CreateBotBody(BaseModel):
    org_id: str
    behavior: str
    system_prompt: Optional[str] = None
    name: Optional[str] = None
    website_url: Optional[str] = None
    role: Optional[str] = None
    tone: Optional[str] = None
    welcome_message: Optional[str] = None

router = APIRouter()
client = Groq(api_key=settings.GROQ_API_KEY)


def get_bot_meta(conn, bot_id: str, org_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "select behavior, system_prompt, public_api_key from chatbots where id=%s",
            (bot_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bot not found")
        if len(row) >= 3:
            return row[0], row[1], row[2]
        return row[0], row[1], None


_RATE_BUCKETS = defaultdict(deque)


def _rate_limit(bot_id: str, org_id: str, limit: int = 30, window_seconds: int = 60):
    key = f"{org_id}:{bot_id}"
    now = time.time()
    dq = _RATE_BUCKETS[key]
    while dq and now - dq[0] > window_seconds:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    dq.append(now)

def _ensure_usage_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_usage_daily (
              org_id text not null,
              bot_id text not null,
              day date not null,
              chats int not null default 0,
              successes int not null default 0,
              fallbacks int not null default 0,
              sum_similarity double precision not null default 0,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id, day)
            )
            """
        )
        def ensure_col(name: str, ddl: str):
            cur.execute(
                "select count(*) from information_schema.columns where table_name=%s and column_name=%s",
                ("bot_usage_daily", name),
            )
            if int(cur.fetchone()[0]) == 0:
                try:
                    cur.execute(f"alter table bot_usage_daily add column {ddl}")
                except Exception:
                    pass
        ensure_col("successes", "successes int not null default 0")
        ensure_col("fallbacks", "fallbacks int not null default 0")
        ensure_col("sum_similarity", "sum_similarity double precision not null default 0")

def _log_chat_usage(conn, org_id: str, bot_id: str, similarity: float, fallback: bool):
    from app.db import normalize_org_id, normalize_bot_id
    org_n = normalize_org_id(org_id)
    bot_n = normalize_bot_id(bot_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into bot_usage_daily (org_id, bot_id, day, chats, successes, fallbacks, sum_similarity)
            values (%s,%s,current_date,1,%s,%s,%s)
            on conflict (org_id, bot_id, day)
            do update set chats = bot_usage_daily.chats + 1,
                          successes = bot_usage_daily.successes + %s,
                          fallbacks = bot_usage_daily.fallbacks + %s,
                          sum_similarity = bot_usage_daily.sum_similarity + %s,
                          updated_at = now()
            """,
            (org_n, bot_n, 0 if fallback else 1, 1 if fallback else 0, float(similarity), 0 if fallback else 1, 1 if fallback else 0, float(similarity)),
        )


@router.post("/chat/{bot_id}")
def chat(bot_id: str, body: ChatBody, x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, body.org_id)
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        _rate_limit(bot_id, body.org_id)
        msg0 = body.message.strip().lower()
        if msg0 in {"hi", "hello", "hey", "hola", "hii"} or msg0.startswith("hi ") or msg0.startswith("hello ") or msg0.startswith("hey "):
            wm = None
            try:
                with conn.cursor() as cur:
                    import uuid as _u
                    nu2 = str(_u.uuid5(_u.NAMESPACE_URL, body.org_id))
                    cur.execute(
                        "select welcome_message from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                        (bot_id, normalize_org_id(body.org_id), body.org_id, nu2),
                    )
                    rwm = cur.fetchone()
                    wm = rwm[0] if rwm else None
            except Exception:
                wm = None
            _ensure_usage_table(conn)
            _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
            return {"answer": wm or "Hello! How can I help you?", "citations": [], "similarity": 0.0}
        chunks = search_top_chunks(body.org_id, bot_id, body.message, settings.MAX_CONTEXT_CHUNKS)
        if not chunks:
            msg = body.message.strip().lower()
            wm = None
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select welcome_message, behavior, system_prompt from chatbots where id=%s",
                        (bot_id,),
                    )
                    rwm = cur.fetchone()
                    wm = rwm[0] if rwm else None
                    beh = rwm[1] if rwm else None
                    sys = rwm[2] if rwm else None
            except Exception:
                wm = None
                beh = None
                sys = None
            is_greet = bool(msg) and (
                msg in {"hi", "hello", "hey", "hola", "hii"} or
                msg.startswith("hi ") or msg.startswith("hello ") or msg.startswith("hey ")
            )
            if is_greet:
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return {"answer": (wm or "Hello! How can I help you?"), "citations": [], "similarity": 0.0}
            try:
                sysmsg = f"You are a {beh or 'helpful'} assistant. " + (sys or "Answer with general knowledge when needed.")
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    temperature=0.5,
                    messages=[
                        {"role": "system", "content": sysmsg},
                        {"role": "user", "content": body.message},
                    ],
                )
                answer = resp.choices[0].message.content
            except Exception:
                answer = "I don't have that information."
            _ensure_usage_table(conn)
            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
            return {"answer": answer, "citations": [], "similarity": 0.0}

        context = "\n\n".join([c[0] for c in chunks])
        base = f"You are a {behavior} assistant."
        system = (base + " " + system_prompt) if system_prompt else (
            base + " Use only the provided context. If the answer is not in context, say: \"I don't have that information.\""
        )
        user = f"Context:\n{context}\n\nQuestion:\n{body.message}"

        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            answer = resp.choices[0].message.content
        except Exception:
            answer = "I don't have that information."
        import math
        sim = float(chunks[0][2])
        if not math.isfinite(sim):
            sim = 0.0
        _ensure_usage_table(conn)
        _log_chat_usage(conn, body.org_id, bot_id, sim, answer == "I don't have that information.")
        return {
            "answer": answer,
            "citations": [c[0][:120] for c in chunks],
            "similarity": sim,
        }
    finally:
        conn.close()

@router.post("/bots")
def create_bot(body: CreateBotBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    import uuid
    bot_id = str(uuid.uuid4())
    allowed = {"sales", "support", "appointment", "qna"}
    beh = (body.behavior or "support").strip().lower()
    if beh in {"appointments", "appointment booking", "bookings"}:
        beh = "appointment"
    if beh in {"sale", "sales bot"}:
        beh = "sales"
    if beh not in allowed:
        raise HTTPException(status_code=400, detail=f"behavior must be one of {sorted(allowed)}")
    nm = (body.name or "").strip() or f"{beh.title()} Bot"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from organizations where id=%s",
                (normalize_org_id(body.org_id),),
            )
            r = cur.fetchone()
            if not r:
                cur.execute(
                    "insert into organizations (id, name) values (%s,%s)",
                    (normalize_org_id(body.org_id), body.org_id),
                )
            def ensure_col(name: str, ddl: str):
                try:
                    cur.execute(ddl)
                except Exception:
                    pass
            ensure_col("name", "alter table chatbots add column if not exists name text")
            ensure_col("website_url", "alter table chatbots add column if not exists website_url text")
            ensure_col("role", "alter table chatbots add column if not exists role text")
            ensure_col("tone", "alter table chatbots add column if not exists tone text")
            ensure_col("welcome_message", "alter table chatbots add column if not exists welcome_message text")
            try:
                cur.execute(
                    """
                    insert into chatbots (id, org_id, behavior, system_prompt, name, website_url, role, tone, welcome_message)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (bot_id, normalize_org_id(body.org_id), beh, body.system_prompt, nm, body.website_url, body.role, body.tone, body.welcome_message),
                )
            except Exception:
                try:
                    cur.execute(
                        "insert into chatbots (id, org_id, behavior, system_prompt, name) values (%s,%s,%s,%s,%s)",
                        (bot_id, normalize_org_id(body.org_id), beh, body.system_prompt, nm),
                    )
                except Exception:
                    cur.execute(
                        "insert into chatbots (id, org_id, behavior, system_prompt, name) values (%s,%s,%s,%s,%s)",
                        (bot_id, normalize_org_id(body.org_id), beh, body.system_prompt, nm),
                    )
        return {"bot_id": bot_id}
    finally:
        conn.close()

@router.get("/bots")
def list_bots(org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        org_n = normalize_org_id(org_id)
        import uuid
        nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select id, name, behavior, system_prompt, public_api_key, website_url, role, tone, welcome_message from chatbots where org_id=%s",
                    (org_n,),
                )
            except Exception:
                cur.execute(
                    "select id, NULL as name, behavior, system_prompt, NULL as public_api_key, NULL as website_url, NULL as role, NULL as tone, NULL as welcome_message from chatbots where org_id=%s",
                    (org_n,),
                )
            rows = cur.fetchall()
        items = []
        for r in rows:
            items.append({
                "bot_id": r[0],
                "name": r[1],
                "behavior": r[2],
                "system_prompt": r[3],
                "has_key": bool(r[4]) if len(r) > 4 else False,
                "website_url": r[5] if len(r) > 5 else None,
                "role": r[6] if len(r) > 6 else None,
                "tone": r[7] if len(r) > 7 else None,
                "welcome_message": r[8] if len(r) > 8 else None,
            })
        return {"bots": items}
    finally:
        conn.close()

@router.options("/bots")
def options_bots():
    return Response(status_code=204)


@router.post("/chat/stream/{bot_id}")
def chat_stream(bot_id: str, body: ChatBody, x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, body.org_id)
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        _rate_limit(bot_id, body.org_id)
        msg0 = body.message.strip().lower()
        if msg0 in {"hi", "hello", "hey", "hola", "hii"} or msg0.startswith("hi ") or msg0.startswith("hello ") or msg0.startswith("hey "):
            wm = None
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select welcome_message from chatbots where id=%s",
                        (bot_id,),
                    )
                    rwm = cur.fetchone()
                    wm = rwm[0] if rwm else None
            except Exception:
                wm = None
            def gen_hi():
                text = wm or "Hello! How can I help you?"
                yield f"data: {text}\n\n"
                yield "event: end\n\n"
            _ensure_usage_table(conn)
            _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
            return StreamingResponse(gen_hi(), media_type="text/event-stream")
        chunks = search_top_chunks(body.org_id, bot_id, body.message, settings.MAX_CONTEXT_CHUNKS)
        if not chunks:
            msg = body.message.strip().lower()
            wm = None
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select welcome_message from chatbots where id=%s",
                        (bot_id,),
                    )
                    rwm = cur.fetchone()
                    wm = rwm[0] if rwm else None
            except Exception:
                wm = None
            is_greet = bool(msg) and (
                msg in {"hi", "hello", "hey", "hola", "hii"} or
                msg.startswith("hi ") or msg.startswith("hello ") or msg.startswith("hey ")
            )
            if is_greet:
                def gen_hi():
                    text = wm or "Hello! How can I help you?"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return StreamingResponse(gen_hi(), media_type="text/event-stream")
            def gen_fb():
                text = "I don't have that information."
                for part in text.split():
                    yield f"data: {part} \n\n"
                yield "event: end\n\n"
                try:
                    cconn = get_conn()
                    try:
                        _ensure_usage_table(cconn)
                        _log_chat_usage(cconn, body.org_id, bot_id, 0.0, True)
                    finally:
                        cconn.close()
                except Exception:
                    pass
            return StreamingResponse(gen_fb(), media_type="text/event-stream")

        context = "\n\n".join([c[0] for c in chunks])
        system = system_prompt or (
            f"You are a {behavior} assistant. Use only the provided context. If the answer is not in context, say: \"I don't have that information.\""
        )
        user = f"Context:\n{context}\n\nQuestion:\n{body.message}"

        def gen():
            try:
                resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                stream=True,
            )
                for evt in resp:
                    try:
                        content = evt.choices[0].delta.content
                    except Exception:
                        content = None
                    if content:
                        yield f"data: {content}\n\n"
                yield "event: end\n\n"
                try:
                    cconn = get_conn()
                    try:
                        _ensure_usage_table(cconn)
                        from math import isfinite
                        simv = float(chunks[0][2])
                        if not isfinite(simv):
                            simv = 0.0
                        _log_chat_usage(cconn, body.org_id, bot_id, simv, False)
                    finally:
                        cconn.close()
                except Exception:
                    pass
            except Exception:
                from math import isfinite
                sim = float(chunks[0][2])
                if not isfinite(sim):
                    sim = 0.0
                text = "I don't have that information."
                for part in text.split():
                    yield f"data: {part} \n\n"
                yield "event: end\n\n"
                try:
                    cconn = get_conn()
                    try:
                        _ensure_usage_table(cconn)
                        _log_chat_usage(cconn, body.org_id, bot_id, 0.0, True)
                    finally:
                        cconn.close()
                except Exception:
                    pass

        return StreamingResponse(gen(), media_type="text/event-stream")
    finally:
        conn.close()

@router.get("/usage/{org_id}/{bot_id}")
def usage(org_id: str, bot_id: str, days: int = 30, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_usage_table(conn)
        from app.db import normalize_org_id, normalize_bot_id
        org_n = normalize_org_id(org_id)
        bot_n = normalize_bot_id(bot_id)
        with conn.cursor() as cur:
            cur.execute(
                "select day, chats, successes, fallbacks, sum_similarity from bot_usage_daily where (org_id=%s or org_id::text=%s) and bot_id=%s and day >= current_date - %s::int order by day asc",
                (org_n, org_id, bot_n, days),
            )
            rows = cur.fetchall()
        return {"daily": [{"day": r[0].isoformat(), "chats": int(r[1]), "successes": int(r[2]), "fallbacks": int(r[3]), "avg_similarity": (float(r[4]) / int(r[1])) if int(r[1]) > 0 else 0.0} for r in rows]}
    finally:
        conn.close()

@router.get("/usage/summary/{org_id}/{bot_id}")
def usage_summary(org_id: str, bot_id: str, days: int = 30, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_usage_table(conn)
        from app.db import normalize_org_id, normalize_bot_id
        org_n = normalize_org_id(org_id)
        bot_n = normalize_bot_id(bot_id)
        with conn.cursor() as cur:
            cur.execute(
                "select coalesce(sum(chats),0), coalesce(sum(successes),0), coalesce(sum(fallbacks),0), coalesce(sum(sum_similarity),0) from bot_usage_daily where (org_id=%s or org_id::text=%s) and bot_id=%s and day >= current_date - %s::int",
                (org_n, org_id, bot_n, days),
            )
            row = cur.fetchone()
            total = int(row[0])
            succ = int(row[1])
            fail = int(row[2])
            sumsim = float(row[3])
        return {"chats": total, "successes": succ, "fallbacks": fail, "avg_similarity": (sumsim / total) if total > 0 else 0.0}
    finally:
        conn.close()

@router.get("/rate/{org_id}/{bot_id}")
def rate_status(org_id: str, bot_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    key = f"{org_id}:{bot_id}"
    dq = _RATE_BUCKETS[key]
    return {"in_window": len(dq), "limit": 30, "window_seconds": 60}

@router.post("/bots/{bot_id}/config")
def update_bot_config(bot_id: str, body: BotConfigBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, body.org_id))
            allowed = {"sales", "support", "appointment", "qna"}
            beh = (body.behavior or "").strip().lower()
            if beh in {"appointments", "appointment booking", "bookings"}:
                beh = "appointment"
            if beh in {"sale", "sales bot"}:
                beh = "sales"
            if beh and beh not in allowed:
                raise HTTPException(status_code=400, detail=f"behavior must be one of {sorted(allowed)}")
            try:
                cur.execute(
                    "update chatbots set behavior=%s, system_prompt=%s, website_url=%s, role=%s, tone=%s, welcome_message=%s where id=%s and org_id::text in (%s,%s,%s)",
                    (beh or body.behavior, body.system_prompt, body.website_url, body.role, body.tone, body.welcome_message, bot_id, normalize_org_id(body.org_id), body.org_id, nu),
                )
            except Exception:
                cur.execute(
                    "update chatbots set behavior=%s, system_prompt=%s where id=%s and org_id::text in (%s,%s,%s)",
                    (beh or body.behavior, body.system_prompt, bot_id, normalize_org_id(body.org_id), body.org_id, nu),
                )
            cur.execute(
                "select behavior, system_prompt, website_url, role, tone, welcome_message from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            return {"behavior": row[0], "system_prompt": row[1], "website_url": row[2], "role": row[3], "tone": row[4], "welcome_message": row[5]}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/config")
def get_bot_config(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
            cur.execute(
                "select behavior, system_prompt, website_url, role, tone, welcome_message from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(org_id), org_id, nu),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            return {"behavior": row[0], "system_prompt": row[1], "website_url": row[2], "role": row[3], "tone": row[4], "welcome_message": row[5]}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/key")
def get_bot_key(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            try:
                import uuid
                nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
                cur.execute(
                    "select public_api_key, public_api_key_rotated_at from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                    (bot_id, normalize_org_id(org_id), org_id, nu),
                )
            except Exception:
                return {"public_api_key": None, "rotated_at": None}
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            return {"public_api_key": row[0], "rotated_at": row[1].isoformat() if row[1] else None}
    finally:
        conn.close()

def _ensure_public_api_key_columns(conn):
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from information_schema.columns where table_name=%s and column_name=%s",
            ("chatbots", "public_api_key"),
        )
        c1 = cur.fetchone()[0]
        if int(c1) == 0:
            try:
                cur.execute("alter table chatbots add column public_api_key text")
            except Exception:
                pass
        cur.execute(
            "select count(*) from information_schema.columns where table_name=%s and column_name=%s",
            ("chatbots", "public_api_key_rotated_at"),
        )
        c2 = cur.fetchone()[0]
        if int(c2) == 0:
            try:
                cur.execute("alter table chatbots add column public_api_key_rotated_at timestamptz")
            except Exception:
                pass

@router.post("/bots/{bot_id}/key/rotate")
def rotate_bot_key(bot_id: str, body: KeyBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    import secrets
    new_key = secrets.token_urlsafe(32)
    conn = get_conn()
    try:
        _ensure_public_api_key_columns(conn)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, body.org_id))
            cur.execute(
                "update chatbots set public_api_key=%s, public_api_key_rotated_at=now() where id=%s and org_id::text in (%s,%s,%s)",
                (new_key, bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
            cur.execute(
                "select public_api_key, public_api_key_rotated_at from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            return {"public_api_key": row[0], "rotated_at": row[1].isoformat() if row[1] else None}
    finally:
        conn.close()

@router.post("/bots/{bot_id}/key/revoke")
def revoke_bot_key(bot_id: str, body: KeyBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_public_api_key_columns(conn)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, body.org_id))
            cur.execute(
                "update chatbots set public_api_key=NULL, public_api_key_rotated_at=NULL where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
        return {"revoked": True}
    finally:
        conn.close()

def _ensure_calendar_settings_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_calendar_settings (
              org_id text not null,
              bot_id text not null,
              provider text not null,
              calendar_id text,
              timezone text,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id, provider)
            )
            """
        )

def _ensure_appointments_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_appointments (
              id bigserial primary key,
              org_id text not null,
              bot_id text not null,
              summary text,
              start_iso text,
              end_iso text,
              attendees_json jsonb,
              created_at timestamptz default now()
            )
            """
        )

@router.post("/bots/{bot_id}/calendar/config")
def set_calendar_config(bot_id: str, body: CalendarConfigBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_calendar_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot_calendar_settings (org_id, bot_id, provider, calendar_id, timezone)
                values (%s,%s,%s,%s,%s)
                on conflict (org_id, bot_id, provider)
                do update set calendar_id=excluded.calendar_id, timezone=excluded.timezone, updated_at=now()
                returning provider, calendar_id, timezone
                """,
                (normalize_org_id(body.org_id), bot_id, body.provider, body.calendar_id, body.timezone),
            )
            row = cur.fetchone()
            return {"provider": row[0], "calendar_id": row[1], "timezone": row[2]}
    finally:
        conn.close()

@router.post("/bots/{bot_id}/calendar/event")
def create_calendar_event(bot_id: str, body: CreateEventBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_calendar_settings_table(conn)
        _ensure_appointments_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select calendar_id from bot_calendar_settings where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(status_code=400, detail="Calendar not configured")
            cal_id = row[0]
            cur.execute(
                """
                insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json)
                values (%s,%s,%s,%s,%s,%s)
                returning id
                """,
                (normalize_org_id(body.org_id), bot_id, body.summary, body.start_iso, body.end_iso, None if body.attendees is None else __import__("json").dumps(body.attendees)),
            )
            rid = cur.fetchone()[0]
        ext_id = None
        try:
            from app.services.calendar_google import create_event as _g_create
            ext_id = _g_create(cal_id, body.summary, body.start_iso, body.end_iso, body.attendees, None)
        except Exception:
            ext_id = None
        return {"scheduled": True, "appointment_id": int(rid), "calendar_id": cal_id, "external_event_id": ext_id}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/embed")
def get_embed_snippet(bot_id: str, org_id: str, widget: str = "bubble", authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        _ensure_public_api_key_columns(conn)
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select public_api_key, welcome_message from chatbots where id=%s and (org_id=%s or org_id::text=%s)",
                    (bot_id, normalize_org_id(org_id), org_id),
                )
                row = cur.fetchone()
                key = row[0] if row else None
                welcome = row[1] if row else None
            except Exception:
                cur.execute(
                    "select NULL as public_api_key, NULL as welcome_message",
                )
                r2 = cur.fetchone()
                key = r2[0] if r2 else None
                welcome = r2[1] if r2 else None
        # If a public API key exists and X-Bot-Key header is provided, ensure it matches
        if key:
            if x_bot_key and x_bot_key != key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        # If Authorization is provided, validate org access
        if authorization:
            try:
                _require_auth(authorization, org_id)
            except HTTPException as e:
                # Allow unauthenticated retrieval of embed snippet if no Authorization header
                if authorization:
                    raise
        # Bot key optional: if present, widget will use it; otherwise unauthenticated
        base = settings.PUBLIC_API_BASE_URL.rstrip("/")
        url = f"{base}/api/chat/stream/{bot_id}"
        theme = settings.WIDGET_THEME
        wmsg = welcome or ""
        wmsg_js = wmsg.replace("\\", "\\\\").replace("'", "\\'")
        def cdn():
            js = (
                "<!-- Chatbot widget: required botId, orgId, apiBase; optional botKey -->"
                f"<script>window.chatbotConfig={{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',welcome:'{wmsg_js}',botName:'',icon:''}};</script>"
                "<!-- Optional keys: botName (header/button), icon (emoji/avatar), welcome (first bot message) -->"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        def bubble():
            return (
                "<script>"
                + "(function(){"
                + f"var B='{bot_id}',O='{org_id}',K='{key or ''}',U='{url}',T='{theme}',W='{wmsg_js}';"
                + "function s(m,cb){var h={'Content-Type':'application/json','X-Bot-Key':K};var b=JSON.stringify({message:m,org_id:O});fetch(U,{method:'POST',headers:h,body:b}).then(function(r){var rd=r.body.getReader();var d=new TextDecoder();function n(){rd.read().then(function(x){if(x.done){cb(null,true);return;}var t=d.decode(x.value);t.split('\\n\\n').forEach(function(l){if(l.indexOf('data: ')==0){cb(l.slice(6),false);}});n();});}n();});}"
                + "function ui(){var w=document.createElement('div');w.style.position='fixed';w.style.bottom='24px';w.style.right='24px';w.style.zIndex='99999';var b=document.createElement('button');b.textContent='Chat';b.style.padding='12px 16px';b.style.borderRadius='999px';b.style.border='none';b.style.background=T==='dark'?'#333':'#0ea5e9';b.style.color=T==='dark'?'#eee':'#fff';var p=document.createElement('div');p.style.position='fixed';p.style.bottom='96px';p.style.right='24px';p.style.width='360px';p.style.maxHeight='60vh';p.style.display='none';p.style.boxShadow='0 8px 24px rgba(0,0,0,0.15)';p.style.borderRadius='12px';p.style.background=T==='dark'?'#111':'#fff';p.style.color=T==='dark'?'#eee':'#111';p.style.padding='12px';var a=document.createElement('div');a.style.whiteSpace='pre-wrap';a.style.fontFamily='system-ui, sans-serif';a.style.fontSize='14px';a.style.lineHeight='1.4';var i=document.createElement('input');i.type='text';i.placeholder='Ask a question';i.style.width='100%';i.style.marginTop='8px';i.style.padding='10px';i.style.border=T==='dark'?'1px solid #333':'1px solid #e5e7eb';i.style.borderRadius='8px';var go=document.createElement('button');go.textContent='Send';go.style.marginTop='8px';go.style.padding='8px 12px';go.style.borderRadius='8px';go.style.border='none';go.style.background=T==='dark'?'#444':'#0ea5e9';go.style.color=T==='dark'?'#eee':'#fff';p.appendChild(a);p.appendChild(i);p.appendChild(go);w.appendChild(b);document.body.appendChild(w);document.body.appendChild(p);b.onclick=function(){p.style.display=p.style.display==='none'?'block':'none';if(a.textContent===''&&W){a.textContent=W;}};go.onclick=function(){a.textContent='';var q=i.value;i.value='';s(q,function(tok,end){if(end){return;}a.textContent+=tok;});};}ui();"
                + "})();"
                + "</script>"
            )
        def inline():
            return (
                "<div id=\"bot-inline\"></div>"
                + "<script>"
                + "(function(){"
                + f"var O='{org_id}',K='{key or ''}',U='{url}';"
                + "function s(m,cb){var h={'Content-Type':'application/json','X-Bot-Key':K};var b=JSON.stringify({message:m,org_id:O});fetch(U,{method:'POST',headers:h,body:b}).then(function(r){var rd=r.body.getReader();var d=new TextDecoder();function n(){rd.read().then(function(x){if(x.done){cb(null,true);return;}var t=d.decode(x.value);t.split('\n\n').forEach(function(l){if(l.indexOf('data: ')==0){cb(l.slice(6),false);}});n();});}n();});}"
                + "var c=document.getElementById('bot-inline');var a=document.createElement('div');a.style.whiteSpace='pre-wrap';var i=document.createElement('input');i.type='text';i.placeholder='Ask a question';i.style.width='100%';var go=document.createElement('button');go.textContent='Send';c.appendChild(a);c.appendChild(i);c.appendChild(go);go.onclick=function(){a.textContent='';var q=i.value;i.value='';s(q,function(tok,end){if(end){return;}a.textContent+=tok;});};"
                + "})();"
                + "</script>"
            )
        def iframe():
            js = (
                "(function(){\n"
                "var C=window.chatbotConfig||{};var B=C.botId,O=C.orgId;var A=C.apiBase||'"+base+"';var K=C.botKey||null;var T='"+theme+"';var W=C.welcome||'';var N=C.title||C.name||C.botName||'Chatbot';var I=C.icon||'';\n"
                "if(!O){return;}\n"
                "function send(m,onchunk){var h={'Content-Type':'application/json'};if(K){h['X-Bot-Key']=K;}var b=JSON.stringify({message:m,org_id:O});try{fetch(A+'/api/chat/stream/'+B,{method:'POST',headers:h,body:b}).then(function(r){var rd=r.body.getReader();var d=new TextDecoder();function pump(){rd.read().then(function(x){if(x.done){onchunk(null,true);return;}var t=d.decode(x.value);t.split('\\n\\n').forEach(function(l){if(l.indexOf('data: ')==0){onchunk(l.slice(6),false);}});pump();});}pump();});}catch(e){onchunk('Error: streaming not available',true);} }\n"
                "function esc(s){return (s||'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
                "function md(s){return esc(s||'');}\n"
                "function add(parent,type,text){var row=document.createElement('div');row.style.display='flex';row.style.margin='10px 0';row.style.justifyContent=type==='me'?'flex-end':'flex-start';var b=document.createElement('div');b.style.maxWidth='80%';b.style.padding='12px 14px';b.style.borderRadius='16px';b.style.lineHeight='1.6';b.style.fontSize='14px';b.style.whiteSpace='normal';b.style.boxShadow='0 6px 18px rgba(0,0,0,0.08)';if(type==='me'){b.style.background=T==='dark'?'#1f2937':'linear-gradient(135deg,#3b82f6,#2563eb)';b.style.color='#fff';b.style.borderBottomRightRadius='8px';}else{b.style.background=T==='dark'?'#111827':'#ffffff';b.style.color=T==='dark'?'#e5e7eb':'#0f172a';b.style.border='1px solid '+(T==='dark'?'#374151':'#e5e7eb');b.style.borderBottomLeftRadius='8px';}if(text){b.innerHTML=md(text);}row.appendChild(b);parent.appendChild(row);parent.scrollTop=parent.scrollHeight;return b;}\n"
                "function ui(){\n"
                "  var w=document.createElement('div');w.style.position='fixed';w.style.bottom='24px';w.style.right='24px';w.style.zIndex='99999';\n"
                "  var b=document.createElement('button');b.style.width='48px';b.style.height='48px';b.style.display='inline-flex';b.style.alignItems='center';b.style.justifyContent='center';b.style.border='none';b.style.borderRadius='999px';b.style.background='transparent';b.style.cursor='pointer';b.style.boxShadow='0 6px 18px rgba(0,0,0,0.08)';b.style.transition='transform .15s ease';b.innerHTML=(I?I:'<svg width=24 height=24 viewBox=\'0 0 24 24\' fill=\'none\' xmlns=\'http://www.w3.org/2000/svg\'><path d=\'M12 2C6.48 2 2 5.58 2 10c0 2.38 1.4 4.52 3.7 5.94L6 22l5.41-2.77C12.27 19.3 12.63 19.5 13 19.5c5.52 0 10-3.58 10-8.5S17.52 2 12 2z\' fill=\'#2563eb\'></path></svg>');\n"
                "  b.onmouseenter=function(){b.style.transform='translateY(-4px)';};b.onmouseleave=function(){b.style.transform='translateY(0)';};\n"
                "  // typing badge\n"
                "  var btnBadge=document.createElement('span');btnBadge.style.position='absolute';btnBadge.style.top='-6px';btnBadge.style.right='-6px';btnBadge.style.minWidth='18px';btnBadge.style.height='18px';btnBadge.style.padding='0 4px';btnBadge.style.borderRadius='12px';btnBadge.style.display='none';btnBadge.style.alignItems='center';btnBadge.style.justifyContent='center';btnBadge.style.fontSize='12px';btnBadge.style.lineHeight='18px';btnBadge.style.background='rgba(37,99,235,0.95)';btnBadge.style.color='#fff';btnBadge.style.fontWeight='700';btnBadge.textContent='';try{b.style.position='relative';b.appendChild(btnBadge);}catch(_){ }\n"
                "  b._typingInterval=null;function setButtonTyping(on){if(on){b.setAttribute('aria-busy','true');btnBadge.style.display='flex';var i=0;btnBadge.textContent='.';if(b._typingInterval)clearInterval(b._typingInterval);b._typingInterval=setInterval(function(){i=(i+1)%4;btnBadge.textContent=new Array(i+1).join('.');},350);}else{b.removeAttribute('aria-busy');btnBadge.style.display='none';btnBadge.textContent='';if(b._typingInterval){clearInterval(b._typingInterval);b._typingInterval=null;}}}\n"
                "  var p=document.createElement('div');p.style.position='fixed';p.style.bottom='84px';p.style.right='24px';p.style.width='380px';p.style.maxWidth='92vw';p.style.background=T==='dark'?'#0b1220':'#fff';p.style.border='1px solid '+(T==='dark'?'#1f2937':'#e5e7eb');p.style.boxShadow='0 20px 48px rgba(0,0,0,0.12)';p.style.borderRadius='12px';p.style.display='none';p.style.overflow='hidden';\n"
                "  var hd=document.createElement('div');hd.style.padding='12px 14px';hd.style.display='flex';hd.style.alignItems='center';hd.style.gap='10px';var av=document.createElement('div');av.style.width='32px';av.style.height='32px';av.style.borderRadius='8px';av.style.background='#2563eb';av.style.color='#fff';av.style.display='inline-flex';av.style.alignItems='center';av.style.justifyContent='center';av.innerHTML=(I||'🤖');var ttl=document.createElement('div');ttl.style.fontWeight='700';ttl.style.color=T==='dark'?'#e5e7eb':'#0f172a';ttl.textContent=N||'Chatbot';hd.appendChild(av);hd.appendChild(ttl);\n"
                "  var body=document.createElement('div');body.style.height='320px';body.style.overflow='auto';body.style.padding='12px';body.style.background=T==='dark'?'#071021':'#fff';\n"
                "  var inr=document.createElement('div');inr.style.display='flex';inr.style.gap='8px';inr.style.padding='10px';inr.style.borderTop='1px solid '+(T==='dark'?'#111827':'#e5e7eb');var input=document.createElement('input');input.type='text';input.placeholder='Ask a question';input.style.flex='1';input.style.padding='10px';input.style.border='1px solid '+(T==='dark'?'#111827':'#e5e7eb');input.style.borderRadius='10px';var sendBtn=document.createElement('button');sendBtn.textContent='Send';sendBtn.style.padding='10px 12px';sendBtn.style.borderRadius='10px';sendBtn.style.border='none';sendBtn.style.background='#2563eb';sendBtn.style.color='#fff';inr.appendChild(input);inr.appendChild(sendBtn);\n"
                "  p.appendChild(hd);p.appendChild(body);p.appendChild(inr);\n"
                "  document.body.appendChild(w);document.body.appendChild(b);document.body.appendChild(p);\n"
                "  function open(){p.style.display='block';requestAnimationFrame(function(){p.style.opacity='1';p.style.transform='translateY(0) scale(1)';});}function close(){p.style.opacity='0';p.style.transform='translateY(6px) scale(0.98)';setTimeout(function(){p.style.display='none';},160);}b.onclick=function(){if(p.style.display==='none'){open();}else{close();}};\n"
                "  function doSend(){var m=input.value.trim();if(!m){return;}input.value='';var me=add(body,'me',m);var bot=add(body,'bot','');var acc='';try{setButtonTyping(true);}catch(_){ }send(m,function(tok,end){if(end){try{setButtonTyping(false);}catch(_){ }return;}acc+=tok;bot.innerHTML=md(acc);});}\n"
                "  sendBtn.onclick=doSend;input.onkeydown=function(e){if((e.key||e.keyCode)==='Enter'||e.keyCode===13){e.preventDefault();doSend();}}\n"
                "}\n"
                "ui();\n"
                "})();\n"
            )
            return js
        snippet = cdn() if widget == "cdn" else bubble() if widget == "bubble" else inline() if widget == "inline" else iframe()
        return {"snippet": snippet, "widget": widget}
    finally:
        conn.close()

from fastapi.responses import PlainTextResponse
# import settings

@router.get("/widget.js", response_class=PlainTextResponse)
def widget_js():
    base = settings.PUBLIC_API_BASE_URL.rstrip("/")
    theme = settings.WIDGET_THEME
    
    js = (
        "(function(){\n"
        "  var C=window.chatbotConfig||{};"
        "  var B=C.botId,O=C.orgId;"
        "  var A=C.apiBase||'"+base+"';"
        "  var K=C.botKey||null;"
        "  var T='"+theme+"';"
        "  var W=C.welcome||'';"
        "  var N=C.botName||'Chatbot';"
        "  var I=C.icon||'';"
        "  var POS=C.position||'right';"
        "  var BN='CodeWeft';"
        "  var BL='https://github.com/CodeWeft-Technologies';\n"
        "  if(!O){console.warn('Chatbot: OrgId missing');return;}\n"
        "  var busy=false;\n"
        "  var SHOW_BADGE=(C.showButtonTyping===undefined)?true:!!C.showButtonTyping;\n"

        "  // --- CSS Injection ---\n"
        "  var __cw_css = `\n"
        "    :root {\n"
        "      --cb-accent: #2563eb;\n"
        "      --cb-bg: `+(T==='dark'?'#0f1724':'#ffffff')+`;\n"
        "      --cb-card: `+(T==='dark'?'#1e293b':'#ffffff')+`;\n"
        "      --cb-text: `+(T==='dark'?'#f8fafc':'#0f1724')+`;\n"
        "      --cb-muted: `+(T==='dark'?'#94a3b8':'#64748b')+`;\n"
        "      --cb-border: `+(T==='dark'?'rgba(255,255,255,0.1)':'rgba(16,24,40,0.06)')+`;\n"
        "      --cb-bubble-me: linear-gradient(180deg,#2563eb,#1e40af);\n"
        "      --cb-bubble-bot: `+(T==='dark'?'#334155':'#ffffff')+`;\n"
        "      --cb-shadow: 0 10px 30px rgba(0,0,0,0.15);\n"
        "    }\n"
        "    .cb-btn { position:fixed; bottom:24px; width:56px; height:56px; padding:8px; border-radius:12px; border:none; background:var(--cb-card); display:flex; align-items:center; justify-content:center; cursor:pointer; z-index:99999; box-shadow:0 8px 30px rgba(2,6,23,.15); transition:transform .12s ease,box-shadow .12s ease; backdrop-filter:blur(6px); }\n"
        "    .cb-btn:hover { transform:translateY(-4px); box-shadow:0 18px 44px rgba(2,6,23,.2); }\n"
        "    .cb-btn svg { width:32px; height:32px; display:block; fill:var(--cb-accent); }\n"
        "    .cb-emoji { font-size:32px; line-height:1; }\n"
        "    .cb-badge { position:absolute; top:-6px; right:-6px; min-width:24px; height:18px; padding:0 6px; border-radius:12px; display:none; align-items:center; justify-content:center; background:var(--cb-accent); color:#fff; box-shadow:0 4px 12px rgba(2,6,23,.2); z-index:999999; }\n"
        "    .cb-badge .dot { width:4px; height:4px; border-radius:50%; background:#fff; display:inline-block; margin:0 2px; opacity:.4; animation:badge-dot 1s infinite; }\n"
        "    .cb-badge .dot:nth-child(2) { animation-delay:.12s; } .cb-badge .dot:nth-child(3) { animation-delay:.24s; }\n"
        "    @keyframes badge-dot { 0%{transform:translateY(0);opacity:.4} 50%{transform:translateY(-4px);opacity:1} 100%{transform:translateY(0);opacity:.4} }\n"
        "    .cb-panel { position:fixed; bottom:96px; width:380px; max-width:calc(100vw - 32px); border-radius:16px; overflow:hidden; display:none; flex-direction:column; z-index:99998; box-shadow:var(--cb-shadow); background:var(--cb-bg); border:1px solid var(--cb-border); transform-origin:right bottom; opacity:0; transform:translateY(10px) scale(0.98); transition:opacity .2s ease, transform .2s ease; }\n"
        "    .cb-head { display:flex; align-items:center; justify-content:space-between; padding:14px 16px; border-bottom:1px solid var(--cb-border); background:var(--cb-card); }\n"
        "    .cb-title { font-weight:700; font-size:15px; color:var(--cb-text); display:flex; align-items:center; gap:8px; }\n"
        "    .cb-body { height:360px; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:12px; background:var(--cb-bg); scroll-behavior:smooth; }\n"
        "    .cb-input { display:flex; gap:10px; padding:12px; border-top:1px solid var(--cb-border); background:var(--cb-card); }\n"
        "    .cb-input input { flex:1; padding:10px 14px; border-radius:10px; border:1px solid var(--cb-border); background:var(--cb-bg); color:var(--cb-text); outline:none; font-size:14px; }\n"
        "    .cb-input input:focus { border-color:var(--cb-accent); }\n"
        "    .cb-send { padding:10px 16px; border-radius:10px; border:none; background:var(--cb-accent); color:#fff; font-weight:600; cursor:pointer; font-size:13px; }\n"
        "    .cb-footer { padding:4px 12px 8px; font-size:11px; color:var(--cb-muted); text-align:center; background:var(--cb-card); }\n"
        "    .cb-footer a { color:var(--cb-accent); text-decoration:none; }\n"
        "    .row { display:flex; width:100%; }\n"
        "    .bubble { max-width:85%; padding:10px 14px; border-radius:14px; line-height:1.5; font-size:14px; word-break:break-word; box-shadow:0 2px 8px rgba(0,0,0,0.04); position:relative; }\n"
        "    .bubble.me { margin-left:auto; background:var(--cb-bubble-me); color:#fff; border-bottom-right-radius:4px; }\n"
        "    .bubble.bot { margin-right:auto; background:var(--cb-bubble-bot); color:var(--cb-text); border:1px solid var(--cb-border); border-bottom-left-radius:4px; }\n"
        "    .bubble pre { background:rgba(0,0,0,0.2); padding:8px; border-radius:6px; overflow-x:auto; margin:6px 0; font-family:monospace; font-size:12px; }\n"
        "    .bubble code { background:rgba(0,0,0,0.1); padding:2px 4px; border-radius:4px; font-size:12px; }\n"
        "    .bubble.bot pre { background:rgba(0,0,0,0.05); color:var(--cb-text); }\n"
        "    .typing { display:inline-flex; align-items:flex-end; gap:4px; padding:6px 8px; }\n"
        "    .typing .dot { width:6px; height:6px; border-radius:50%; background:var(--cb-muted); animation:dot 1s infinite; }\n"
        "    .typing .dot:nth-child(2){animation-delay:.12s} .typing .dot:nth-child(3){animation-delay:.24s}\n"
        "    @keyframes dot{0%{transform:translateY(0);opacity:.4}50%{transform:translateY(-5px);opacity:1}100%{transform:translateY(0);opacity:.4}}\n"
        "  `;\n"
        "  try{var s=document.createElement('style');s.innerHTML=__cw_css;document.head.appendChild(s);}catch(_){}\n"

        "  // --- Markdown Parser ---\n"
        "  function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "  function md(s){\n"
        "     var t=esc(s);\n"
        "     t=t.replace(/```([\\s\\S]*?)```/g,function(_,c){return '<pre><code>'+c+'</code></pre>';});\n"
        "     t=t.replace(/`([^`]+)`/g,'<code>$1</code>');\n"
        "     t=t.replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>');\n"
        "     t=t.replace(/\\[(.*?)\\]\\((.*?)\\)/g,function(_,txt,url){var u=(url||'').replace(/[\"']/g,'');return '<a href=\"'+u+'\" target=\"_blank\" style=\"color:inherit;text-decoration:underline\">'+txt+'</a>';});\n"
        "     t=t.replace(/(?:^|\\n)[*-]\\s+(.*)/g,'<div style=\"display:flex;gap:6px\"><span>•</span><span>$1</span></div>');\n"
        "     return t;\n"
        "  }\n"

        "  // --- UI Elements ---\n"
        "  var btn = document.createElement('button');\n"
        "  btn.className = 'cb-btn';\n"
        "  btn.setAttribute('aria-label', 'Open chat');\n"
        
        "  // **UPDATED ICON LOGIC**\n"
        "  // 1. Check if Icon is URL (http/data). 2. Check if Icon exists (Emoji/Text). 3. Default SVG.\n"
        "  if(I && (I.indexOf('http')===0 || I.indexOf('data:image')===0)){\n"
        "     var img = document.createElement('img'); img.src=I; img.style.width='32px'; img.style.height='32px'; img.style.borderRadius='50%';\n"
        "     btn.appendChild(img);\n"
        "  } else if (I) {\n"
        "     var spn = document.createElement('span'); spn.className='cb-emoji'; spn.textContent=I;\n"
        "     btn.appendChild(spn);\n"
        "  } else {\n"
        "     btn.innerHTML = '<svg viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12 3C7.03 3 3 6.69 3 11c0 2.5 1.45 4.73 3.8 6.05L6 21l4.3-1.64c.9.2 1.85.31 2.7.31 4.97 0 9-3.69 9-8.01S16.97 3 12 3Z\"/></svg>';\n"
        "  }\n"
        "  document.body.appendChild(btn);\n"

        "  var badge = document.createElement('span');\n"
        "  badge.className='cb-badge';\n"
        "  badge.innerHTML='<span class=\"dot\"></span><span class=\"dot\"></span><span class=\"dot\"></span>';\n"
        "  btn.appendChild(badge);\n"

        "  var panel = document.createElement('div');\n"
        "  panel.className = 'cb-panel';\n"
        "  panel.innerHTML = `\n"
        "    <div class=\"cb-head\">\n"
        "      <div class=\"cb-title\">\n"
        "        `+(I?'<span style=\"font-size:20px;line-height:1\">'+(I.indexOf('http')===0?'<img src=\"'+I+'\" style=\"width:24px;height:24px;border-radius:50%\">':I)+'</span> ':'') + N +`\n"
        "      </div>\n"
        "      <button class=\"cb-close\" style=\"background:transparent;border:none;font-size:20px;color:var(--cb-text);cursor:pointer;line-height:1\">×</button>\n"
        "    </div>\n"
        "    <div class=\"cb-body\"></div>\n"
        "    <div class=\"cb-input\">\n"
        "      <input type=\"text\" placeholder=\"Ask a question...\">\n"
        "      <button class=\"cb-send\">Send</button>\n"
        "    </div>\n"
        "    <div class=\"cb-footer\">Powered by <a href=\"`+BL+`\" target=\"_blank\">`+BN+`</a></div>\n"
        "  `;\n"
        "  document.body.appendChild(panel);\n"

        "  var body = panel.querySelector('.cb-body');\n"
        "  var input = panel.querySelector('input');\n"
        "  var sendBtn = panel.querySelector('.cb-send');\n"
        "  var closeBtn = panel.querySelector('.cb-close');\n"

        "  // --- Logic ---\n"
        "  function alignPanel(){\n"
        "     var br = btn.getBoundingClientRect();\n"
        "     if(POS==='left'){\n"
        "        btn.style.left='24px'; btn.style.right='auto';\n"
        "        panel.style.left=Math.max(8,br.left)+'px'; panel.style.right='auto'; panel.style.transformOrigin='left bottom';\n"
        "     } else {\n"
        "        btn.style.right='24px'; btn.style.left='auto';\n"
        "        panel.style.right=Math.max(8,window.innerWidth-br.right)+'px'; panel.style.left='auto'; panel.style.transformOrigin='right bottom';\n"
        "     }\n"
        "     panel.style.bottom = (window.innerHeight - br.top + 12) + 'px';\n"
        "  }\n"
        "  setTimeout(alignPanel, 100); window.addEventListener('resize', alignPanel);\n"

        "  function open(){\n"
        "    alignPanel();\n"
        "    panel.style.display='flex';\n"
        "    requestAnimationFrame(function(){ panel.style.opacity='1'; panel.style.transform='translateY(0) scale(1)'; });\n"
        "    if(body.childNodes.length===0 && W) addMsg('bot', W);\n"
        "    input.focus();\n"
        "  }\n"
        "  function close(){\n"
        "    panel.style.opacity='0'; panel.style.transform='translateY(10px) scale(0.98)';\n"
        "    setTimeout(function(){ panel.style.display='none'; }, 200);\n"
        "  }\n"

        "  function addMsg(type, text){\n"
        "     var r = document.createElement('div'); r.className='row';\n"
        "     var b = document.createElement('div'); b.className='bubble '+(type==='me'?'me':'bot');\n"
        "     if(text) b.innerHTML = md(text);\n"
        "     r.appendChild(b); body.appendChild(r);\n"
        "     body.scrollTop = body.scrollHeight;\n"
        "     return b;\n"
        "  }\n"
        "  function setBadge(on){\n"
        "    if(!SHOW_BADGE) return;\n"
        "    badge.style.display = on ? 'inline-flex' : 'none';\n"
        "  }\n"

        "  function sendApi(m, onchunk){\n"
        "     var h={'Content-Type':'application/json'};\n"
        "     if(K) h['X-Bot-Key']=K;\n"
        "     var payload=JSON.stringify({message:m, org_id:O});\n"
        "     fetch(A+'/api/chat/stream/'+B, {method:'POST',headers:h,body:payload})\n"
        "     .then(function(r){\n"
        "         var rd=r.body.getReader(); var d=new TextDecoder();\n"
        "         function pump(){\n"
        "            rd.read().then(function(x){\n"
        "               if(x.done){ onchunk(null,true); return; }\n"
        "               var chunk=d.decode(x.value);\n"
        "               chunk.split('\\n\\n').forEach(function(l){\n"
        "                  if(l.indexOf('data: ')===0) onchunk(l.slice(6), false);\n"
        "               });\n"
        "               pump();\n"
        "            });\n"
        "         } pump();\n"
        "     }).catch(function(e){ onchunk('Error connecting.', true); });\n"
        "  }\n"

        "  function doSend(){\n"
        "     if(busy) return;\n"
        "     var txt = input.value.trim(); if(!txt) return;\n"
        "     busy = true; input.value=''; input.disabled=true; sendBtn.disabled=true;\n"
        "     addMsg('me', txt);\n"
        "     var botRow = document.createElement('div'); botRow.className='row';\n"
        "     var botBub = document.createElement('div'); botBub.className='bubble bot';\n"
        "     botBub.innerHTML = '<div class=\"typing\"><span class=\"dot\"></span><span class=\"dot\"></span><span class=\"dot\"></span></div>';\n"
        "     botRow.appendChild(botBub); body.appendChild(botRow); body.scrollTop=body.scrollHeight;\n"
        "     setBadge(true);\n"
        "     var acc = '';\n"
        "     sendApi(txt, function(token, end){\n"
        "        if(end){\n"
        "           busy=false; input.disabled=false; sendBtn.disabled=false; setBadge(false); input.focus();\n"
        "           return;\n"
        "        }\n"
        "        if(acc==='') botBub.innerHTML='';\n"
        "        acc += token;\n"
        "        botBub.innerHTML = md(acc);\n"
        "        body.scrollTop = body.scrollHeight;\n"
        "     });\n"
        "  }\n"

        "  btn.onclick = function(){ if(panel.style.display!=='none' && panel.style.opacity!=='0') close(); else open(); };\n"
        "  closeBtn.onclick = close;\n"
        "  sendBtn.onclick = doSend;\n"
        "  input.onkeydown = function(e){ if(e.key==='Enter' || e.keyCode===13){ e.preventDefault(); doSend(); } };\n"

        "  function isUuid(s){return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);}\n"
        "  function init(){\n"
        "    if(!B||!isUuid(B)){\n"
        "      fetch(A+'/api/bots?org_id='+encodeURIComponent(O))\n"
        "      .then(r=>r.json()).then(d=>{\n"
        "         if(d.bots && d.bots.length > 0) {\n"
        "             B=d.bots[0].bot_id;\n"
        "             if(!W && d.bots[0].welcome_message) W=d.bots[0].welcome_message;\n"
        "         }\n"
        "      }).catch(e=>{});\n"
        "    }\n"
        "  }\n"
        "  init();\n"
        "})();"
    )
    return js

@router.get("/api/widget.js", response_class=PlainTextResponse)
def widget_js_compat():
    return widget_js()

@router.get("/dashboard/{org_id}")
def dashboard(org_id: str):
    conn = get_conn()
    try:
        org_n = normalize_org_id(org_id)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
            try:
                cur.execute(
                    "select id, behavior, system_prompt, public_api_key from chatbots where org_id::text in (%s,%s,%s)",
                    (org_n, org_id, nu),
                )
                bots = cur.fetchall()
            except Exception:
                cur.execute(
                    "select id, behavior, system_prompt from chatbots where org_id::text in (%s,%s,%s)",
                    (org_n, org_id, nu),
                )
                bots = cur.fetchall()
            cur.execute(
                "select bot_id, count(*) from rag_embeddings where (org_id=%s or org_id::text=%s or org_id=%s) group by bot_id",
                (org_n, org_id, nu),
            )
            counts = {r[0]: int(r[1]) for r in cur.fetchall()}
        items = []
        for b in bots:
            bid = b[0]
            beh = b[1]
            sys = b[2]
            k = b[3] if len(b) > 3 else None
            items.append({
                "bot_id": bid,
                "behavior": beh,
                "system_prompt": sys,
                "has_key": bool(k),
                "embedding_count": counts.get(bid, 0),
            })
        return {"bots": items}
    finally:
        conn.close()

@router.get("/dashboard/ui/{org_id}", response_class=HTMLResponse)
def dashboard_ui(org_id: str):
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Dashboard</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<style>body{font-family:system-ui,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #e5e7eb;padding:8px;text-align:left}code{background:#f3f4f6;padding:2px 4px;border-radius:4px}button{background:#0ea5e9;color:#fff;border:none;border-radius:6px;padding:8px 12px}input,select{padding:8px;border:1px solid #e5e7eb;border-radius:6px}#grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.bar{display:flex;gap:8px;align-items:center;margin-bottom:16px}</style></head><body>"
        f"<h1>Org {org_id} Dashboard</h1>"
        "<div class=\"bar\"><input id=\"email\" type=\"email\" placeholder=\"email\"><input id=\"password\" type=\"password\" placeholder=\"password\"><button id=\"login\">Login</button><span id=\"authmsg\" style=\"color:#6b7280;font-size:12px\"></span></div>"
        "<div id=\"grid\">"
        "<div><h2>Bots</h2><div id=\"bots\">Loading...</div></div>"
        "<div><h2>Usage</h2><div id=\"usage\">Select a bot</div><h2 style=\"margin-top:16px\">Test</h2><div id=\"test\">Select a bot</div></div>"
        "</div>"
        "<script>\n"
        "const ORG = '" + org_id + "';\n"
        "let TOKEN = localStorage.getItem('TOKEN') || '';\n"
        "function setToken(t){TOKEN=t||'';if(TOKEN){localStorage.setItem('TOKEN',TOKEN);document.getElementById('authmsg').textContent='Authenticated';}else{localStorage.removeItem('TOKEN');document.getElementById('authmsg').textContent='';}}\n"
        "async function api(path){const h = TOKEN?{Authorization:'Bearer '+TOKEN}:{ };const r=await fetch(path,{headers:h});if(r.status===401){document.getElementById('authmsg').textContent='Login required';throw new Error('unauthorized');}return await r.json();}\n"
        "document.getElementById('login').onclick=async()=>{const e=document.getElementById('email').value.trim();const p=document.getElementById('password').value;try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:e,password:p})});if(!r.ok){document.getElementById('authmsg').textContent='Login failed';return;}const d=await r.json();setToken(d.token);loadBots();}catch(_){document.getElementById('authmsg').textContent='Login error';}};\n"
        "async function loadBots(){const data=await api('/api/bots?org_id='+ORG);const el=document.getElementById('bots');el.innerHTML='';"
        "const tbl=document.createElement('table');tbl.innerHTML='<thead><tr><th>Bot</th><th>Behavior</th><th>Has Key</th><th>Actions</th></tr></thead>';const tb=document.createElement('tbody');tbl.appendChild(tb);"
        "data.bots.forEach(b=>{const tr=document.createElement('tr');tr.innerHTML='<td>'+b.bot_id+'</td><td>'+b.behavior+'</td><td>'+(b.has_key?'yes':'no')+'</td><td></td>';const td=tr.querySelector('td:last-child');const btn=document.createElement('button');btn.textContent='Usage';btn.onclick=()=>loadUsage(b.bot_id);td.appendChild(btn);const snip=document.createElement('button');snip.textContent='Embed';snip.style.marginLeft='8px';snip.onclick=()=>loadSnippet(b.bot_id);td.appendChild(snip);const test=document.createElement('button');test.textContent='Test';test.style.marginLeft='8px';test.onclick=()=>loadTest(b.bot_id);td.appendChild(test);const cfg=document.createElement('button');cfg.textContent='Configure';cfg.style.marginLeft='8px';cfg.onclick=()=>loadConfig(b.bot_id);td.appendChild(cfg);tb.appendChild(tr);});el.appendChild(tbl);}\n"
        "async function loadUsage(bot){const d=await api('/api/usage/summary/'+ORG+'/'+bot+'?days=30');document.getElementById('usage').innerHTML='<p><b>Chats:</b> '+d.chats+' &nbsp; <b>Successes:</b> '+d.successes+' &nbsp; <b>Fallbacks:</b> '+d.fallbacks+' &nbsp; <b>Avg Similarity:</b> '+(Math.round(d.avg_similarity*100)/100)+'</p>'; }\n"
        "async function loadSnippet(bot){const d=await api('/api/bots/'+bot+'/embed?org_id='+ORG+'&widget=bubble');const pre=document.createElement('pre');pre.textContent=d.snippet;document.getElementById('usage').innerHTML='';document.getElementById('usage').appendChild(pre);}\n"
        "async function loadConfig(bot){const el=document.getElementById('usage');el.textContent='Loading config...';const cfg=await api('/api/bots/'+bot+'/config?org_id='+ORG);el.innerHTML='';const wrap=document.createElement('div');const lbl=document.createElement('label');lbl.textContent='Greeting (welcome) message';const br=document.createElement('br');const inp=document.createElement('input');inp.id='wm';inp.style.width='60%';inp.value=(cfg.welcome_message||'');const actions=document.createElement('div');actions.style.marginTop='8px';const save=document.createElement('button');save.id='save';save.textContent='Save';actions.appendChild(save);wrap.appendChild(lbl);wrap.appendChild(br);wrap.appendChild(inp);wrap.appendChild(actions);el.appendChild(wrap);save.onclick=async()=>{const hs={'Content-Type':'application/json'};if(TOKEN){hs.Authorization='Bearer '+TOKEN;}const r=await fetch('/api/bots/'+bot+'/config',{method:'POST',headers:hs,body:JSON.stringify({org_id:ORG,welcome_message:inp.value})});if(!r.ok){el.textContent='Failed to save';return;}const d=await r.json();el.textContent='Saved. New welcome: '+(d.welcome_message||'');};}\n"
        "async function loadTest(bot){const el=document.getElementById('test');el.innerHTML='';const wrap=document.createElement('div');const inp=document.createElement('input');inp.type='text';inp.placeholder='Type a message';inp.style.width='70%';const send=document.createElement('button');send.textContent='Ask';send.style.marginLeft='8px';const out=document.createElement('div');out.style.marginTop='12px';wrap.appendChild(inp);wrap.appendChild(send);wrap.appendChild(out);el.appendChild(wrap);let XBK=null;try{const k=await api('/api/bots/'+bot+'/key?org_id='+ORG);XBK=k.public_api_key||null;}catch(_){XBK=null;}send.onclick=async()=>{const q=inp.value.trim();if(!q){return;}out.textContent='Asking...';try{const hs={ 'Content-Type':'application/json' };if(TOKEN){hs.Authorization='Bearer '+TOKEN;}if(XBK){hs['X-Bot-Key']=XBK;}const r=await fetch('/api/chat/'+bot,{method:'POST',headers:hs,body:JSON.stringify({message:q,org_id:ORG})});if(!r.ok){out.textContent='Error '+r.status;return;}const d=await r.json();out.textContent='Answer: '+d.answer+(d.similarity!==undefined?'\nSimilarity: '+(Math.round(d.similarity*100)/100):'');}catch(e){out.textContent='Error';}};}\n"
        "if(TOKEN){document.getElementById('authmsg').textContent='Authenticated';loadBots();}\n"
        "</script>"
        "</body></html>"
    )
    return html
from starlette.responses import Response
def _ensure_users_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists app_users (
              id text primary key,
              email text unique not null,
              password_hash text not null,
              org_id text not null,
              created_at timestamptz not null default now()
            )
            """
        )

def _hash_password(pw: str) -> str:
    salt = base64.urlsafe_b64encode(hashlib.sha256(uuid.uuid4().bytes).digest())[:16].decode()
    iterations = 150000
    pep = getattr(settings, 'PASSWORD_PEPPER', '') or getattr(settings, 'JWT_SECRET', 'dev-secret')
    dk = hashlib.pbkdf2_hmac('sha256', (pw+pep).encode(), salt.encode(), iterations)
    return f"pbkdf2${iterations}${salt}${base64.urlsafe_b64encode(dk).decode()}"

def _verify_password(pw: str, stored: str) -> bool:
    try:
        _, it_s, salt, hv = stored.split('$')
        it = int(it_s)
        pep = getattr(settings, 'PASSWORD_PEPPER', '') or getattr(settings, 'JWT_SECRET', 'dev-secret')
        dk = hashlib.pbkdf2_hmac('sha256', (pw+pep).encode(), salt.encode(), it)
        return hmac.compare_digest(base64.urlsafe_b64encode(dk).decode(), hv)
    except Exception:
        return False

def _jwt_secret() -> str:
    return getattr(settings, 'JWT_SECRET', 'dev-secret')

def _require_auth(authorization: Optional[str], org_id: str) -> dict:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="missing bearer token")
    payload = _jwt_decode(authorization.split(' ',1)[1])
    tok_org = payload.get('org_id')
    if normalize_org_id(tok_org or '') != normalize_org_id(org_id):
        raise HTTPException(status_code=403, detail="forbidden for org")
    return payload

def _jwt_encode(payload: dict, exp_minutes: int = 120) -> str:
    header = {"alg":"HS256","typ":"JWT"}
    now = int(datetime.datetime.utcnow().timestamp())
    payload = dict(payload)
    payload.setdefault('iat', now)
    payload.setdefault('exp', now + exp_minutes*60)
    def b64(x):
        return base64.urlsafe_b64encode(json.dumps(x, separators=(',',':')).encode()).rstrip(b'=').decode()
    signing_input = f"{b64(header)}.{b64(payload)}"
    sig = hmac.new(_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"

def _jwt_decode(token: str) -> dict:
    try:
        h,p,s = token.split('.')
        signing_input = f"{h}.{p}"
        sig = base64.urlsafe_b64decode(s + '==')
        calc = hmac.new(_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, calc):
            raise HTTPException(status_code=401, detail="Invalid token signature")
        payload = json.loads(base64.urlsafe_b64decode(p + '==').decode())
        exp = int(payload.get('exp', 0))
        if exp and int(datetime.datetime.utcnow().timestamp()) > exp:
            raise HTTPException(status_code=401, detail="Token expired")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

class RegisterBody(BaseModel):
    email: str
    password: str
    org_id: Optional[str] = None
    org_name: Optional[str] = None

class LoginBody(BaseModel):
    email: str
    password: str

@router.post("/auth/register")
def auth_register(body: RegisterBody):
    email = body.email.strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="email and password required")
    conn = get_conn()
    try:
        _ensure_users_table(conn)
        org = body.org_id.strip() if body.org_id else email.split('@')[0]
        with conn.cursor() as cur:
            try:
                cur.execute("select 1 from organizations where id=%s", (normalize_org_id(org),))
                r = cur.fetchone()
                if not r:
                    cur.execute("insert into organizations (id, name) values (%s,%s)", (normalize_org_id(org), body.org_name or org))
            except Exception:
                pass
            cur.execute("select id from app_users where email=%s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="email already registered")
            uid = str(uuid.uuid4())
            ph = _hash_password(body.password)
            cur.execute("insert into app_users (id, email, password_hash, org_id) values (%s,%s,%s,%s)", (uid, email, ph, normalize_org_id(org)))
        token = _jwt_encode({"sub": email, "org_id": normalize_org_id(org)})
        return {"token": token, "org_id": normalize_org_id(org)}
    finally:
        conn.close()

@router.post("/auth/login")
def auth_login(body: LoginBody):
    email = body.email.strip().lower()
    conn = get_conn()
    try:
        _ensure_users_table(conn)
        with conn.cursor() as cur:
            cur.execute("select password_hash, org_id from app_users where email=%s", (email,))
            row = cur.fetchone()
            if not row or not _verify_password(body.password, row[0]):
                raise HTTPException(status_code=401, detail="invalid credentials")
            org = row[1]
        token = _jwt_encode({"sub": email, "org_id": normalize_org_id(org)})
        return {"token": token, "org_id": normalize_org_id(org)}
    finally:
        conn.close()

@router.get("/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="missing bearer token")
    payload = _jwt_decode(authorization.split(' ',1)[1])
    return {"email": payload.get('sub'), "org_id": payload.get('org_id')}

class CleanupBody(BaseModel):
    org_id: Optional[str] = None
    confirm: bool = False

@router.post("/admin/cleanup")
def admin_cleanup(body: CleanupBody, authorization: Optional[str] = Header(default=None)):
    payload = _require_auth(authorization, body.org_id or _jwt_decode(authorization.split(' ',1)[1]).get('org_id'))
    org = body.org_id or payload.get('org_id')
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    conn = get_conn()
    try:
        org_n = normalize_org_id(org)
        counts = {}
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org))
            for name, sql in [
                ("rag_embeddings", "delete from rag_embeddings where org_id::text in (%s,%s,%s)"),
                ("bot_usage_daily", "delete from bot_usage_daily where org_id::text in (%s,%s,%s)"),
                ("bot_calendar_settings", "delete from bot_calendar_settings where org_id::text in (%s,%s,%s)"),
                ("bot_appointments", "delete from bot_appointments where org_id::text in (%s,%s,%s)"),
                ("chatbots", "delete from chatbots where org_id::text in (%s,%s,%s)"),
            ]:
                try:
                    cur.execute(sql + " returning 1", (org_n, org, nu))
                    counts[name] = cur.rowcount
                except Exception:
                    try:
                        cur.execute(sql, (org_n, org, nu))
                        counts[name] = cur.rowcount
                    except Exception:
                        counts[name] = 0
        return {"deleted": counts, "org_id": org}
    finally:
        conn.close()

class AllCleanupBody(BaseModel):
    confirm: bool = False
    preserve_users: bool = True

@router.post("/admin/cleanup_all")
def admin_cleanup_all(body: AllCleanupBody, authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="missing bearer token")
    _jwt_decode(authorization.split(' ',1)[1])
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    conn = get_conn()
    try:
        counts = {}
        with conn.cursor() as cur:
            for name, sql in [
                ("rag_embeddings", "delete from rag_embeddings"),
                ("bot_usage_daily", "delete from bot_usage_daily"),
                ("bot_calendar_settings", "delete from bot_calendar_settings"),
                ("bot_appointments", "delete from bot_appointments"),
                ("chatbots", "delete from chatbots"),
            ]:
                try:
                    cur.execute(sql)
                    counts[name] = cur.rowcount
                except Exception:
                    counts[name] = 0
            if body.preserve_users:
                try:
                    cur.execute("delete from organizations o where not exists (select 1 from app_users u where u.org_id=o.id)")
                    counts["organizations"] = cur.rowcount
                except Exception:
                    counts["organizations"] = 0
            else:
                try:
                    cur.execute("delete from organizations")
                    counts["organizations"] = cur.rowcount
                except Exception:
                    counts["organizations"] = 0
        return {"deleted": counts}
    finally:
        conn.close()

# Delete a single bot and all of its related data within an org
class DeleteBotBody(BaseModel):
    org_id: str
    confirm: bool = False

@router.post("/bots/{bot_id}/delete")
def delete_bot(bot_id: str, body: DeleteBotBody, authorization: Optional[str] = Header(default=None)):
    from app.db import get_conn, normalize_org_id, normalize_bot_id
    _require_auth(authorization, body.org_id)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    conn = get_conn()
    try:
        org_n = normalize_org_id(body.org_id)
        bot_n = normalize_bot_id(bot_id)
        counts = {}
        with conn.cursor() as cur:
            for name, sql in [
                ("rag_embeddings", "delete from rag_embeddings where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("bot_usage_daily", "delete from bot_usage_daily where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("bot_calendar_settings", "delete from bot_calendar_settings where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("bot_appointments", "delete from bot_appointments where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("chatbots", "delete from chatbots where org_id::text in (%s,%s) and id::text in (%s,%s)"),
            ]:
                try:
                    cur.execute(sql + " returning 1", (org_n, body.org_id, bot_n, bot_id))
                    counts[name] = cur.rowcount
                except Exception:
                    try:
                        cur.execute(sql, (org_n, body.org_id, bot_n, bot_id))
                        counts[name] = cur.rowcount
                    except Exception:
                        counts[name] = 0
        return {"deleted": counts, "bot_id": bot_n, "org_id": org_n}
    finally:
        conn.close()
