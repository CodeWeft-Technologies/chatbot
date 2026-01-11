from fastapi import APIRouter, HTTPException, Header, File, UploadFile, Form
from typing import Optional
from pydantic import BaseModel
from typing import List
from app.services.enhanced_rag import chunk_text, embed_text, store_embedding
from app.config import settings


class IngestBody(BaseModel):
    org_id: str
    content: str


router = APIRouter()


from collections import defaultdict, deque
import time
import base64, json, hmac, hashlib, datetime
import threading

_RATE_BUCKETS = defaultdict(deque)
_INGEST_LOCK = threading.Semaphore(1)  # Allow only 1 concurrent ingest to prevent memory spikes


def _rate_limit(bot_id: str, org_id: str, limit: int = 120, window_seconds: int = 60):
    key = f"{org_id}:{bot_id}:ingest"
    now = time.time()
    dq = _RATE_BUCKETS[key]
    while dq and now - dq[0] > window_seconds:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    dq.append(now)


@router.post("/ingest/{bot_id}")
def ingest(bot_id: str, body: IngestBody, x_bot_key: Optional[str] = Header(default=None), authorization: Optional[str] = Header(default=None)):
    from app.db import get_conn, normalize_org_id
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select public_api_key from chatbots where id=%s and org_id=%s",
                    (bot_id, normalize_org_id(body.org_id)),
                )
                row = cur.fetchone()
                public_api_key = row[0] if row else None
            except Exception:
                public_api_key = None
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        else:
            _require_auth(authorization, body.org_id)
    finally:
        conn.close()
    _rate_limit(bot_id, body.org_id)
    
    # Prevent concurrent ingests to avoid memory spikes (max 1 at a time)
    if not _INGEST_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Another ingest is running; please wait")
    
    try:
        chunks: List[str] = chunk_text(body.content)
        inserted = 0
        skipped = 0
        try:
            for c in chunks:
                emb = embed_text(c)
                stored = store_embedding(body.org_id, bot_id, c, emb, metadata=None)
                if stored:
                    inserted += 1
                else:
                    skipped += 1
        finally:
            # Unload embedding model to free ~2GB RAM after ingest completes
            from app.services.enhanced_rag import unload_model
            print(f"[INGEST] Inserted {inserted} chunks - calling unload_model()...", flush=True)
            unload_model()
        return {"inserted": inserted, "skipped_duplicates": skipped}
    finally:
        _INGEST_LOCK.release()


@router.get("/analytics/{org_id}/{bot_id}")
def analytics(org_id: str, bot_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    from app.db import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            from app.db import normalize_bot_id
            cur.execute(
                "select count(*), max(created_at) from rag_embeddings where (org_id=%s or org_id::text=%s) and (bot_id=%s or bot_id::text=%s)",
                (normalize_org_id(org_id), org_id, normalize_bot_id(bot_id), bot_id),
            )
            row = cur.fetchone()
            total = int(row[0]) if row and row[0] is not None else 0
            latest = row[1].isoformat() if row and row[1] is not None else None
        return {"embedding_count": total, "last_ingest_at": latest}
    finally:
        conn.close()

@router.get("/analytics/sources/{org_id}/{bot_id}")
def analytics_sources(org_id: str, bot_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    from app.db import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select coalesce(metadata->>'source_url', metadata->>'source_file', 'text') as source, count(*)
                from rag_embeddings
                where (org_id=%s or org_id::text=%s) and (bot_id=%s or bot_id::text=%s)
                group by source
                order by count(*) desc
                """
                ,
                (normalize_org_id(org_id), org_id, normalize_bot_id(bot_id), bot_id),
            )
            rows = cur.fetchall()
        return {"sources": [{"source": r[0], "count": int(r[1])} for r in rows]}
    finally:
        conn.close()


class UrlBody(BaseModel):
    org_id: str
    url: str


@router.post("/ingest/url/{bot_id}")
def ingest_url(bot_id: str, body: UrlBody, x_bot_key: Optional[str] = Header(default=None), authorization: Optional[str] = Header(default=None)):
    from app.db import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select public_api_key from chatbots where id=%s and org_id=%s",
                    (bot_id, normalize_org_id(body.org_id)),
                )
                row = cur.fetchone()
                public_api_key = row[0] if row else None
            except Exception:
                public_api_key = None
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        else:
            _require_auth(authorization, body.org_id)
    finally:
        conn.close()

    # Prevent concurrent ingests to avoid memory spikes (max 1 at a time)
    if not _INGEST_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Another ingest is running; please wait")
    
    try:
        # Use enhanced scraper with Playwright and Readability (enabled by default)
        from app.services.enhanced_scraper import scrape_url
        from app.services.enhanced_rag import chunk_text, embed_text, store_embedding, remove_boilerplate
        
        print(f"[INGEST-URL] Starting URL ingest for {body.url}", flush=True)
        
        try:
            scraped = scrape_url(body.url, use_playwright=True, timeout=30)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Scraping failed: {str(e)}")
        
        print(f"[INGEST-URL] Scraped content length: {len(scraped.content)} chars", flush=True)
        
        # Remove boilerplate patterns
        cleaned_content = remove_boilerplate(scraped.content)
        
        print(f"[INGEST-URL] Cleaned content length: {len(cleaned_content)} chars", flush=True)
        
        # Chunk with semantic boundaries
        chunks: List[str] = chunk_text(cleaned_content)
        
        inserted = 0
        skipped = 0
        
        chunk_sizes = [len(c) for c in chunks]
        print(f"[INGEST-URL] Processing {len(chunks)} chunks (sizes: {chunk_sizes}), will call embed_text() for each", flush=True)
        
        try:
            for c in chunks:
                emb = embed_text(c)
                
                # Build metadata
                meta = {
                    "source_url": scraped.final_url,
                }
                if scraped.title:
                    meta["page_title"] = scraped.title
                if scraped.description:
                    meta["description"] = scraped.description
                if scraped.canonical_url:
                    meta["canonical_url"] = scraped.canonical_url
                if scraped.language:
                    meta["language"] = scraped.language
                
                # Store with automatic deduplication
                stored = store_embedding(body.org_id, bot_id, c, emb, metadata=meta)
                if stored:
                    inserted += 1
                else:
                    skipped += 1
        finally:
            # Unload embedding model to free ~2GB RAM after ingest completes
            from app.services.enhanced_rag import unload_model
            print(f"[INGEST-URL] Inserted {inserted} chunks - calling unload_model()...", flush=True)
            unload_model()
        
        return {
            "inserted": inserted,
            "skipped_duplicates": skipped,
            "total_chunks": len(chunks),
            "language": scraped.language,
        }
    finally:
        _INGEST_LOCK.release()


@router.post("/ingest/pdf/{bot_id}")
async def ingest_pdf(
    bot_id: str,
    org_id: str = Form(...),
    file: UploadFile = File(...),
    x_bot_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    from app.db import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select public_api_key from chatbots where id=%s and org_id=%s",
                    (bot_id, normalize_org_id(org_id)),
                )
                row = cur.fetchone()
                public_api_key = row[0] if row else None
            except Exception:
                public_api_key = None
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        else:
            _require_auth(authorization, org_id)
    finally:
        conn.close()

    # Prevent concurrent ingests to avoid memory spikes (max 1 at a time)
    if not _INGEST_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Another ingest is running; please wait")
    
    try:
        from io import BytesIO
        from pypdf import PdfReader

        data = await file.read()
        reader = PdfReader(BytesIO(data))
        pages = []
        for p in reader.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pages.append("")
        text = "\n".join(pages)
        chunks: List[str] = chunk_text(text)
        inserted = 0
        skipped = 0
        
        try:
            for c in chunks:
                emb = embed_text(c)
                stored = store_embedding(org_id, bot_id, c, emb, metadata={"source_file": file.filename})
                if stored:
                    inserted += 1
                else:
                    skipped += 1
        finally:
            # Unload embedding model to free ~2GB RAM after ingest completes
            from app.services.enhanced_rag import unload_model
            unload_model()
        
        return {"inserted": inserted, "skipped_duplicates": skipped}
    finally:
        _INGEST_LOCK.release()
    return {"inserted": inserted, "skipped_duplicates": skipped}

@router.options("/ingest/pdf/{bot_id}")
async def ingest_pdf_options(bot_id: str):
    return Response(status_code=204)
from starlette.responses import Response

@router.options("/ingest/{bot_id}")
def ingest_options(bot_id: str):
    return Response(status_code=204)

@router.options("/ingest/url/{bot_id}")
def ingest_url_options(bot_id: str):
    return Response(status_code=204)

class ClearBody(BaseModel):
    org_id: str
    confirm: bool = False

@router.post("/ingest/clear/{bot_id}")
def ingest_clear(bot_id: str, body: ClearBody, x_bot_key: Optional[str] = Header(default=None), authorization: Optional[str] = Header(default=None)):
    from app.db import get_conn, normalize_org_id, normalize_bot_id
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select public_api_key from chatbots where id in (%s,%s) and org_id in (%s,%s)",
                    (normalize_bot_id(bot_id), bot_id, normalize_org_id(body.org_id), body.org_id),
                )
                row = cur.fetchone()
                public_api_key = row[0] if row else None
            except Exception:
                public_api_key = None
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        else:
            _require_auth(authorization, body.org_id)
        deleted = 0
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "delete from rag_embeddings where (org_id=%s or org_id::text=%s) and (bot_id=%s or bot_id::text=%s) returning 1",
                    (normalize_org_id(body.org_id), body.org_id, normalize_bot_id(bot_id), bot_id),
                )
                deleted = cur.rowcount
            except Exception:
                cur.execute(
                    "delete from rag_embeddings where (org_id=%s or org_id::text=%s) and (bot_id=%s or bot_id::text=%s)",
                    (normalize_org_id(body.org_id), body.org_id, normalize_bot_id(bot_id), bot_id),
                )
                deleted = cur.rowcount
        return {"deleted": int(deleted)}
    finally:
        conn.close()
def _jwt_secret():
    return getattr(settings, 'JWT_SECRET', 'dev-secret')

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

def _require_auth(authorization: Optional[str], org_id: str):
    from app.db import normalize_org_id
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="missing bearer token")
    payload = _jwt_decode(authorization.split(' ',1)[1])
    tok_org = payload.get('org_id')
    if normalize_org_id(tok_org or '') != normalize_org_id(org_id):
        raise HTTPException(status_code=403, detail="forbidden for org")
    return payload
