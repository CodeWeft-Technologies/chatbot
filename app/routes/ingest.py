from fastapi import APIRouter, HTTPException, Header, File, UploadFile, Form
from typing import Optional
from pydantic import BaseModel
from typing import List
from app.rag import chunk_text, embed_text, store_embedding
from app.config import settings


class IngestBody(BaseModel):
    org_id: str
    content: str


router = APIRouter()


from collections import defaultdict, deque
import time
import base64, json, hmac, hashlib, datetime

_RATE_BUCKETS = defaultdict(deque)


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
    chunks: List[str] = chunk_text(body.content)
    inserted = 0
    for c in chunks:
        emb = embed_text(c)
        store_embedding(body.org_id, bot_id, c, emb, metadata=None)
        inserted += 1
    return {"inserted": inserted}


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

    import requests
    from bs4 import BeautifulSoup

    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        url = "https://" + url
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        r = requests.get(url, timeout=20, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"fetch failed: {str(e)}")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    used_url = r.url
    try:
        amp = soup.find("link", attrs={"rel":"amphtml"})
        amp_href = amp.get("href") if amp else None
        if amp_href:
            try:
                r2 = requests.get(amp_href, timeout=20, headers=headers)
                r2.raise_for_status()
                soup = BeautifulSoup(r2.text, "html.parser")
                used_url = r2.url
            except Exception:
                pass
    except Exception:
        pass
    try:
        for t in soup.find_all(["script","style","noscript","template"]):
            t.decompose()
    except Exception:
        pass
    try:
        for t in soup.find_all(["nav","footer","header","aside"]):
            t.decompose()
    except Exception:
        pass
    title = None
    try:
        title = (soup.title.string or "").strip() if soup.title else None
    except Exception:
        title = None
    desc = None
    try:
        md = soup.find("meta", attrs={"name":"description"})
        desc = (md.get("content") or "").strip() if md else None
    except Exception:
        desc = None
    candidates = []
    try:
        for sel in [
            lambda s: s.find("article"),
            lambda s: s.find(attrs={"role":"main"}),
            lambda s: s.find(id="main"),
            lambda s: s.find(id="content"),
            lambda s: s.find(class_="article"),
            lambda s: s.find(class_="post"),
            lambda s: s.find(class_="content"),
            lambda s: s.find(class_="entry-content"),
        ]:
            try:
                el = sel(soup)
                if el:
                    candidates.append(el.get_text("\n"))
            except Exception:
                pass
    except Exception:
        candidates = []
    body_text = ""
    try:
        from urllib.parse import urlparse
        host = urlparse(used_url).netloc.lower()
    except Exception:
        host = ""
    try:
        if host.find("msn.com") != -1:
            main = None
            for sel in [
                lambda s: s.find("article"),
                lambda s: s.find(attrs={"itemprop":"articleBody"}),
                lambda s: s.find("section", attrs={"itemprop":"articleBody"}),
                lambda s: s.find("div", attrs={"itemprop":"articleBody"}),
                lambda s: s.find("div", class_=lambda c: c and ("article" in c or "entry" in c or "content" in c or "story" in c)),
            ]:
                try:
                    el = sel(soup)
                    if el:
                        main = el
                        break
                except Exception:
                    pass
            if main:
                ps = [p.get_text(" ") for p in main.find_all("p")]
                body_text = "\n".join(ps) or ""
        if not body_text and candidates:
            body_text = max(candidates, key=lambda x: len(x or "")) or ""
        else:
            ps = [p.get_text(" ") for p in soup.find_all("p")]
            body_text = "\n".join(ps)
    except Exception:
        body_text = soup.get_text("\n")
    def _clean(s: str) -> str:
        try:
            lines = [l.strip() for l in (s or "").splitlines()]
            lines = [l for l in lines if l]
            return "\n".join(lines)
        except Exception:
            return s or ""
    text_parts = []
    if title:
        text_parts.append(title)
    if desc:
        text_parts.append(desc)
    text_parts.append(_clean(body_text))
    text = "\n\n".join([t for t in text_parts if t])
    chunks: List[str] = chunk_text(text)
    inserted = 0
    for c in chunks:
        emb = embed_text(c)
        meta = {"source_url": used_url}
        if title:
            meta["page_title"] = title
        try:
            canon = soup.find("link", attrs={"rel":"canonical"})
            ch = canon.get("href") if canon else None
            if ch:
                meta["canonical_url"] = ch
        except Exception:
            pass
        store_embedding(body.org_id, bot_id, c, emb, metadata=meta)
        inserted += 1
    return {"inserted": inserted}


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
    for c in chunks:
        emb = embed_text(c)
        store_embedding(org_id, bot_id, c, emb, metadata={"source_file": file.filename})
        inserted += 1
    return {"inserted": inserted}

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
