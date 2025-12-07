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
_SESSION_STATE = defaultdict(dict)


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
        import re
        msg_raw = (body.message or '').strip()
        low = msg_raw.lower()
        has_time = bool(
            re.search(r"\d{4}-\d{2}-\d{2}", msg_raw) or
            re.search(r"\b(today|tomorrow|mon|tue|wed|thu|fri|sat|sun)\b", low) or
            re.search(r"\b(\d{1,2}:\d{2})\b", msg_raw) or
            re.search(r"\b\d{1,2}\s*(am|pm)\b", low)
        )
        has_action = bool(re.search(r"\b(book|schedule|reschedule|cancel|change)\b", low))
        has_id = bool(re.search(r"\b(?:appointment|id)\s*[:#]?\s*\d+\b", low))
        if (behavior or '').strip().lower() == 'appointment' and (has_time or has_action or has_id):
            import re
            msg = body.message.strip()
            m0lower = msg.lower()
            is_greet = bool(m0lower) and (
                m0lower in {"hi", "hello", "hey", "hola", "hii"} or
                m0lower.startswith("hi ") or m0lower.startswith("hello ") or m0lower.startswith("hey ")
            )
            if is_greet:
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
            base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
            form_url = f"{base}/api/form/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
            def _norm_month(s: str) -> int:
                m = s.lower()
                d = {
                    'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'sept':9,'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12
                }
                return d.get(m,0)
            def _norm_weekday(s: str) -> int:
                m = s.lower()
                d = {'sunday':6,'sun':6,'monday':0,'mon':0,'tuesday':1,'tue':1,'tues':1,'wednesday':2,'wed':2,'thursday':3,'thu':3,'thur':3,'thurs':3,'friday':4,'fri':4,'saturday':5,'sat':5}
                return d.get(m,-1)
            def _parse_natural(s: str):
                from datetime import datetime, timedelta
                now = datetime.now()
                base_date = None
                m = re.search(r"\b(today|tomorrow)\b", s, re.IGNORECASE)
                if m:
                    w = m.group(1).lower()
                    base_date = now.date() if w == 'today' else (now + timedelta(days=1)).date()
                if base_date is None:
                    mwd = re.search(r"\b(next\s+)?(mon(day)?|tue(s|sday)?|wed(nesday)?|thu(rs|rsday)?|fri(day)?|sat(urday)?|sun(day)?)\b", s, re.IGNORECASE)
                    if mwd:
                        is_next = bool(mwd.group(1))
                        wd = _norm_weekday(mwd.group(2))
                        if wd >= 0:
                            cur = now.weekday()
                            delta = (wd - cur) % 7
                            if delta == 0:
                                delta = 7 if is_next else 0
                            elif is_next:
                                delta = delta + 7
                            base_date = (now + timedelta(days=delta)).date()
                if base_date is None:
                    mmd = re.search(r"\b(\d{1,2})\s*(?:/|-)\s*(\d{1,2})(?:\s*(\d{4}))?\b", s)
                    if mmd:
                        d1 = int(mmd.group(1)); d2 = int(mmd.group(2)); y = int(mmd.group(3)) if mmd.group(3) else now.year
                        try:
                            base_date = datetime(y, d1, d2).date()
                        except Exception:
                            try:
                                base_date = datetime(y, d2, d1).date()
                            except Exception:
                                base_date = None
                if base_date is None:
                    mname = re.search(r"\b([A-Za-z]{3,9})\s*(\d{1,2})(?:,?\s*(\d{4}))?\b", s)
                    if mname:
                        mo = _norm_month(mname.group(1)); day = int(mname.group(2)); year = int(mname.group(3)) if mname.group(3) else now.year
                        if mo > 0:
                            try:
                                base_date = datetime(year, mo, day).date()
                            except Exception:
                                base_date = None
                st_h = None; st_m = 0; en_h = None; en_m = 0; dur_min = None
                mt = re.search(r"\b(at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", s, re.IGNORECASE)
                if mt:
                    sh = int(mt.group(2)); sm = int(mt.group(3) or '0'); ap = (mt.group(4) or '').lower()
                    if ap == 'pm' and sh < 12:
                        sh += 12
                    if ap == 'am' and sh == 12:
                        sh = 0
                    st_h, st_m = sh, sm
                mend = re.search(r"\b(to|until)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", s, re.IGNORECASE)
                if mend:
                    eh = int(mend.group(2)); em = int(mend.group(3) or '0'); ap = (mend.group(4) or '').lower()
                    if ap == 'pm' and eh < 12:
                        eh += 12
                    if ap == 'am' and eh == 12:
                        eh = 0
                    en_h, en_m = eh, em
                mdur = re.search(r"\bfor\s*(\d{1,3})\s*(minute|min|mins|hour|hr|hours|h)\b", s, re.IGNORECASE)
                if mdur:
                    val = int(mdur.group(1)); unit = mdur.group(2).lower()
                    dur_min = val * 60 if unit in {'hour','hours','hr','h'} else val
                if base_date and st_h is not None:
                    start_dt = datetime(base_date.year, base_date.month, base_date.day, st_h, st_m)
                    if en_h is not None:
                        end_dt = datetime(base_date.year, base_date.month, base_date.day, en_h, en_m)
                    else:
                        mins = dur_min if dur_min is not None else 30
                        end_dt = start_dt + timedelta(minutes=mins)
                    return start_dt.isoformat(), end_dt.isoformat()
                return None
            # --- Appointment management by ID: cancel/reschedule/status ---
            try:
                m_id = re.search(r"\b(?:appointment|id)\s*[:#]?\s*(\d+)\b", msg, re.IGNORECASE)
                ap_id = int(m_id.group(1)) if m_id else None
            except Exception:
                ap_id = None
            if ap_id:
                lowmsg = msg.lower()
                try:
                    _ensure_oauth_table(conn)
                    _ensure_booking_settings_table(conn)
                    _ensure_audit_logs_table(conn)
                    with conn.cursor() as cur:
                        cur.execute(
                            "select external_event_id, start_iso, end_iso, status from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                            (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                        )
                        row = cur.fetchone()
                    if not row:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": f"Appointment ID {ap_id} not found.", "citations": [], "similarity": 0.0}
                    ev_id, cur_si, cur_ei, cur_st = row[0], row[1], row[2], row[3]
                    with conn.cursor() as cur:
                        cur.execute(
                            "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                            (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                        )
                        c = cur.fetchone()
                    if not c:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Calendar not connected. Or use the [booking form](" + form_url + ")", "citations": [], "similarity": 0.0}
                    cal_id, at_enc, rt_enc, exp = c
                    from app.services.calendar_google import _decrypt, build_service_from_tokens, update_event_oauth, delete_event_oauth
                    at = _decrypt(at_enc) if at_enc else None
                    rt = _decrypt(rt_enc) if rt_enc else None
                    svc = build_service_from_tokens(at or "", rt, exp)
                    if not svc:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Calendar service unavailable.", "citations": [], "similarity": 0.0}
                    if ("cancel" in lowmsg):
                        ok = delete_event_oauth(svc, cal_id or "primary", ev_id)
                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return {"answer": "Cancel failed.", "citations": [], "similarity": 0.0}
                        with conn.cursor() as cur:
                            cur.execute("update bot_appointments set status=%s, updated_at=now() where id=%s", ("cancelled", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "cancel", {})
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return {"answer": f"Cancelled appointment ID: {ap_id}", "citations": [], "similarity": 1.0}
                    if ("reschedule" in lowmsg) or ("change" in lowmsg):
                        si_ei = None
                        m = re.search(r"\bto\b(.+)$", msg, re.IGNORECASE)
                        if m:
                            si_ei = _parse_natural(m.group(1)) or None
                        if not si_ei:
                            si_ei = _parse_natural(msg)
                        if not si_ei:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return {"answer": "Provide new time to reschedule. E.g., 'reschedule id " + str(ap_id) + " to tomorrow 3pm'. Or use the [booking form](" + form_url + ")", "citations": [], "similarity": 0.0}
                        new_si, new_ei = si_ei
                        patch = {"start": {"dateTime": new_si}, "end": {"dateTime": new_ei}}
                        ok = update_event_oauth(svc, cal_id or "primary", ev_id, patch)
                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return {"answer": "Reschedule failed.", "citations": [], "similarity": 0.0}
                        with conn.cursor() as cur:
                            cur.execute("update bot_appointments set start_iso=%s, end_iso=%s, status=%s, updated_at=now() where id=%s", (new_si, new_ei, "booked", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "reschedule", {"new_start_iso": new_si, "new_end_iso": new_ei})
                        try:
                            desc = f"Appointment ID: {ap_id}\nName: {info.get('name') or ''}\nEmail: {info.get('email') or ''}\nPhone: {info.get('phone') or ''}\nNotes: {info.get('notes') or ''}"
                            patch2 = {"summary": "Appointment #"+str(ap_id)+" - "+(info.get('name') or ''), "description": desc}
                            update_event_oauth(svc, cal_id or "primary", ev_id, patch2)
                        except Exception:
                            pass
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return {"answer": f"Rescheduled ID {ap_id} to {new_si} - {new_ei}", "citations": [], "similarity": 1.0}
                    # default: show status/details
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                    return {"answer": f"Appointment {ap_id}: {cur_si} to {cur_ei}. Status: {cur_st}", "citations": [], "similarity": 0.0}
                except Exception:
                    try:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                    except Exception:
                        pass
                    return {"answer": "Error handling appointment.", "citations": [], "similarity": 0.0}
            if not ap_id and "my booking" in msg.lower():
                try:
                    with conn.cursor() as cur:
                        cur.execute("select id, start_iso, end_iso, status from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s order by created_at desc limit 1", (normalize_org_id(body.org_id), body.org_id, bot_id))
                        row = cur.fetchone()
                    if not row:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "No appointments found.", "citations": [], "similarity": 0.0}
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 0.5, False)
                    return {"answer": f"Latest appointment ID {int(row[0])}: {row[1]} to {row[2]}. Status: {row[3]}", "citations": [], "similarity": 0.5}
                except Exception:
                    pass
            # Check if this is a new booking request (not reschedule/cancel) - show form directly
            lowmsg = msg.lower()
            is_new_booking = bool(re.search(r"\b(book|schedule|appointment)\b", lowmsg)) and not bool(re.search(r"\b(cancel|reschedule|change|status)\b", lowmsg))
            if not ap_id and is_new_booking:
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return {"answer": "Please use the [booking form](" + form_url + ") to schedule your appointment. It shows available time slots and you can select a convenient time.", "citations": [], "similarity": 0.0}
            patt = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})(?:[T\s](?P<start>\d{2}:\d{2})(?:\s*(?:to|-|until)\s*(?P<end>\d{2}:\d{2}))?)", re.IGNORECASE)
            m = patt.search(msg)
            if m:
                d = m.group('date')
                st = m.group('start')
                en = m.group('end') or None
                if not en:
                    try:
                        sd = f"{d}T{st}:00"
                        from datetime import datetime, timedelta
                        start_dt = datetime.fromisoformat(sd)
                        end_dt = start_dt + timedelta(minutes=30)
                        ei = end_dt.isoformat()
                    except Exception:
                        ei = f"{d}T{st}:00"
                else:
                    ei = f"{d}T{en}:00"
                si = f"{d}T{st}:00"
            else:
                parsed = _parse_natural(msg)
                if parsed:
                    si, ei = parsed
                else:
                    si = None; ei = None
            try:
                _ensure_oauth_table(conn)
                _ensure_booking_settings_table(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                        (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise Exception("Calendar not connected")
                    cal_id, at_enc, rt_enc = row
                    cur.execute(
                        "select timezone, slot_duration_minutes, capacity_per_slot, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                        (normalize_org_id(body.org_id), body.org_id, bot_id),
                    )
                    bs = cur.fetchone()
                    from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth, create_event_oauth
                    at = _decrypt(at_enc) if at_enc else None
                    rt = _decrypt(rt_enc) if rt_enc else None
                    svc = build_service_from_tokens(at or "", rt, None)
                    tzv = (bs[0] if bs and len(bs) > 0 else None) or None
                    slot_dur = int(bs[1]) if bs and bs[1] else 30
                    capacity = int(bs[2]) if bs and bs[2] else 1
                    import json as _json
                    required_fields = []
                    try:
                        rfraw = (bs[3] if bs and len(bs) > 3 else None)
                        required_fields = rfraw if isinstance(rfraw, list) else (_json.loads(rfraw) if isinstance(rfraw, str) else [])
                    except Exception:
                        required_fields = []
                    import datetime as _dt
                    if not si or not ei:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Could not parse date/time. Try formats like '2025-12-06 15:30' or 'tomorrow at 3pm for 30 minutes'. Or use the [booking form](" + form_url + ")", "citations": [], "similarity": 0.0}
                    tmn = _dt.datetime.fromisoformat(si)
                    tmx = _dt.datetime.fromisoformat(ei)
                    if not svc:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Calendar not connected. Please connect Google Calendar in the dashboard. Or use the [booking form](" + form_url + ")", "citations": [], "similarity": 0.0}
                    items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
                    # extract user info from message
                    info = {}
                    try:
                        em = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", msg)
                        if em:
                            info["email"] = em.group(0)
                        ph = re.search(r"\+?\d[\d \-]{7,}\d", msg)
                        if ph:
                            import re as _re
                            info["phone"] = _re.sub(r"\D", "", ph.group(0))
                        nm = re.search(r"(?:my name is|i am|this is)\s+([A-Za-z][A-Za-z .'-]{1,50})", msg, re.IGNORECASE)
                        if nm:
                            info["name"] = nm.group(1).strip()
                        nt = re.search(r"(?:purpose|note|reason)[:\-]\s*(.+)$", msg, re.IGNORECASE)
                        if nt:
                            info["notes"] = nt.group(1).strip()
                    except Exception:
                        pass
                    missing = [f for f in (required_fields or []) if not info.get(f)]
                    if missing:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": ("Please provide: " + ", ".join(missing) + ". Or use the [booking form](" + form_url + ")"), "citations": [], "similarity": 0.0}
                    occ = len(items) if items else 0
                    with conn.cursor() as cur:
                        cur.execute(
                            "select count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso=%s and end_iso=%s and status in ('scheduled','booked')",
                            (normalize_org_id(body.org_id), body.org_id, bot_id, si, ei),
                        )
                        occ_db = int(cur.fetchone()[0])
                    if max(occ, occ_db) < capacity:
                        apid = None
                        ext_id = None
                        try:
                            attns = ([info.get("email")] if info.get("email") else None)
                            desc = f"Appointment\nName: {info.get('name') or ''}\nEmail: {info.get('email') or ''}\nPhone: {info.get('phone') or ''}\nNotes: {info.get('notes') or ''}"
                            ext_id = create_event_oauth(svc, cal_id or "primary", "Appointment", si, ei, attns, tzv, desc)
                            if not ext_id:
                                _ensure_usage_table(conn)
                                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                                return {"answer": "Calendar booking failed. Please try again after reconnecting Google Calendar. Or use the [booking form](" + form_url + ")", "citations": [], "similarity": 0.0}
                            _ensure_appointments_table(conn)
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json, status, external_event_id)
                                    values (%s,%s,%s,%s,%s,%s,%s,%s)
                                    returning id
                                    """,
                                    (normalize_org_id(body.org_id), bot_id, "Appointment", si, ei, None if not info else __import__("json").dumps(info), "scheduled", ext_id),
                                )
                                apid = int(cur.fetchone()[0])
                            try:
                                from app.services.calendar_google import update_event_oauth
                                desc = f"Appointment ID: {apid}\nName: {info.get('name') or ''}\nEmail: {info.get('email') or ''}\nPhone: {info.get('phone') or ''}\nNotes: {info.get('notes') or ''}"
                                patch = {
                                    "summary": "Appointment #"+str(apid)+" - "+(info.get('name') or ''),
                                    "description": desc,
                                    "extendedProperties": {"private": {"appointment_id": str(apid), "org_id": body.org_id, "bot_id": bot_id}},
                                }
                                update_event_oauth(svc, cal_id or "primary", ext_id, patch)
                            except Exception:
                                _log_audit(conn, body.org_id, bot_id, apid, "calendar_patch_error", {"ext_id": ext_id})
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                            return {"answer": f"Booked. ID: {apid}", "citations": [], "similarity": 1.0}
                        except Exception:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return {"answer": "Booking failed. Please try again or provide a different time. Or use the [booking form](" + form_url + ")", "citations": [], "similarity": 0.0}
                    else:
                        sugg = []
                        cur_t = _dt.datetime.fromisoformat(si)
                        for _ in range(6):
                            cur_t = cur_t + _dt.timedelta(minutes=slot_dur)
                            end_t = cur_t + _dt.timedelta(minutes=slot_dur)
                            evs = list_events_oauth(svc, cal_id or "primary", cur_t.isoformat(), end_t.isoformat())
                            if not evs or len(evs) < capacity:
                                sugg.append(cur_t.isoformat())
                            if len(sugg) >= 3:
                                break
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": ("Unavailable. Alternatives: " + ", ".join(sugg) + ". Or use the [booking form](" + form_url + ")"), "citations": [], "similarity": 0.0}
            except Exception:
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return {"answer": "Could not process booking request. Or use the [booking form](" + form_url + ")", "citations": [], "similarity": 0.0}
        m0 = (body.message or '').strip().lower()
        wm = None
        is_greet = bool(m0) and (m0 in {"hi","hello","hey","hola","hii"} or m0.startswith("hi ") or m0.startswith("hello ") or m0.startswith("hey "))
        if is_greet:
            try:
                with conn.cursor() as cur:
                    cur.execute("select welcome_message from chatbots where id=%s", (bot_id,))
                    rwm = cur.fetchone(); wm = rwm[0] if rwm else None
            except Exception:
                wm = None
            def gen_hi():
                text = wm or "Hello! How can I help you?"
                yield f"data: {text}\n\n"; yield "event: end\n\n"
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
                sysmsg = (
                    f"You are a {beh or 'helpful'} assistant. "
                    + (sys or "Answer with general knowledge when needed.")
                    + " Keep responses short and informative."
                )
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
        system = (
            (base + " " + system_prompt + " Keep responses short and informative.")
            if system_prompt
            else (
                base + " Use only the provided context. If the answer is not in context, say: \"I don't have that information.\" Keep responses short and informative."
            )
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
    if authorization:
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
        import re
        msg_raw = (body.message or '').strip()
        low = msg_raw.lower()
        has_time = bool(
            re.search(r"\d{4}-\d{2}-\d{2}", msg_raw) or
            re.search(r"\b(today|tomorrow|mon|tue|wed|thu|fri|sat|sun)\b", low) or
            re.search(r"\b(\d{1,2}:\d{2})\b", msg_raw) or
            re.search(r"\b\d{1,2}\s*(am|pm)\b", low)
        )
        has_action = bool(re.search(r"\b(book|schedule|reschedule|cancel|change)\b", low))
        has_id = bool(re.search(r"\b(?:appointment|id)\s*[:#]?\s*\d+\b", low))
        if (behavior or '').strip().lower() == 'appointment' and (has_time or has_action or has_id):
            import re
            msg = body.message.strip()
            base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
            form_url = f"{base}/api/form/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
            def _norm_month(s: str) -> int:
                m = s.lower()
                d = {
                    'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'sept':9,'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12
                }
                return d.get(m,0)
            def _norm_weekday(s: str) -> int:
                m = s.lower()
                d = {'sunday':6,'sun':6,'monday':0,'mon':0,'tuesday':1,'tue':1,'tues':1,'wednesday':2,'wed':2,'thursday':3,'thu':3,'thur':3,'thurs':3,'friday':4,'fri':4,'saturday':5,'sat':5}
                return d.get(m,-1)
            def _parse_natural(s: str):
                from datetime import datetime, timedelta
                now = datetime.now()
                base_date = None
                m = re.search(r"\b(today|tomorrow)\b", s, re.IGNORECASE)
                if m:
                    w = m.group(1).lower()
                    base_date = now.date() if w == 'today' else (now + timedelta(days=1)).date()
                if base_date is None:
                    mwd = re.search(r"\b(next\s+)?(mon(day)?|tue(s|sday)?|wed(nesday)?|thu(rs|rsday)?|fri(day)?|sat(urday)?|sun(day)?)\b", s, re.IGNORECASE)
                    if mwd:
                        is_next = bool(mwd.group(1))
                        wd = _norm_weekday(mwd.group(2))
                        if wd >= 0:
                            cur = now.weekday()
                            delta = (wd - cur) % 7
                            if delta == 0:
                                delta = 7 if is_next else 0
                            base_date = (now + timedelta(days=delta)).date()
                tm = re.search(r"\b(\d{1,2})(?:\:(\d{2}))?\s*(am|pm)\b", s, re.IGNORECASE)
                if base_date and tm:
                    hh = int(tm.group(1)) % 12
                    mm = int(tm.group(2) or '00')
                    ap = tm.group(3).lower()
                    if ap == 'pm':
                        hh += 12
                    start_dt = datetime.combine(base_date, datetime.min.time()).replace(hour=hh, minute=mm)
                    end_dt = start_dt + timedelta(minutes=30)
                    return start_dt.isoformat(), end_dt.isoformat()
                return None
            try:
                m_id = re.search(r"\b(?:appointment|id)\s*[:#]?\s*(\d+)\b", msg, re.IGNORECASE)
                ap_id = int(m_id.group(1)) if m_id else None
            except Exception:
                ap_id = None
            if ap_id:
                def gen_status(text):
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                try:
                    _ensure_oauth_table(conn)
                    _ensure_booking_settings_table(conn)
                    _ensure_audit_logs_table(conn)
                    with conn.cursor() as cur:
                        cur.execute(
                            "select external_event_id, start_iso, end_iso, status from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                            (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                        )
                        row = cur.fetchone()
                    if not row:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return StreamingResponse(gen_status(f"Appointment ID {ap_id} not found."), media_type="text/event-stream")
                    ev_id, cur_si, cur_ei, cur_st = row[0], row[1], row[2], row[3]
                    with conn.cursor() as cur:
                        cur.execute(
                            "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                            (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                        )
                        c = cur.fetchone()
                    if not c:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return StreamingResponse(gen_status("Calendar not connected. Or use the [booking form](" + form_url + ")"), media_type="text/event-stream")
                    cal_id, at_enc, rt_enc, exp = c
                    from app.services.calendar_google import _decrypt, build_service_from_tokens, update_event_oauth, delete_event_oauth
                    at = _decrypt(at_enc) if at_enc else None
                    rt = _decrypt(rt_enc) if rt_enc else None
                    svc = build_service_from_tokens(at, rt, exp)
                    if not svc:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return StreamingResponse(gen_status("Calendar service unavailable."), media_type="text/event-stream")
                    lw = msg.lower()
                    if ("cancel" in lw):
                        ok = delete_event_oauth(svc, cal_id or "primary", ev_id)
                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return StreamingResponse(gen_status("Cancel failed."), media_type="text/event-stream")
                        with conn.cursor() as cur:
                            cur.execute("update bot_appointments set status=%s, updated_at=now() where id=%s", ("cancelled", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "cancel", {})
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return StreamingResponse(gen_status(f"Cancelled appointment ID: {ap_id}"), media_type="text/event-stream")
                    if ("reschedule" in lw) or ("change" in lw):
                        seg = None
                        m = re.search(r"\bto\b(.+)$", msg, re.IGNORECASE)
                        if m:
                            seg = _parse_natural(m.group(1)) or None
                        if not seg:
                            seg = _parse_natural(msg)
                        if not seg:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return StreamingResponse(gen_status("Provide new time to reschedule. E.g., 'reschedule id " + str(ap_id) + " to tomorrow 3pm'. Or use the [booking form](" + form_url + ")"), media_type="text/event-stream")
                        new_si, new_ei = seg
                        patch = {"start": {"dateTime": new_si}, "end": {"dateTime": new_ei}}
                        ok = update_event_oauth(svc, cal_id or "primary", ev_id, patch)
                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return StreamingResponse(gen_status("Reschedule failed."), media_type="text/event-stream")
                        with conn.cursor() as cur:
                            cur.execute("update bot_appointments set start_iso=%s, end_iso=%s, status=%s, updated_at=now() where id=%s", (new_si, new_ei, "booked", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "reschedule", {"new_start_iso": new_si, "new_end_iso": new_ei})
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return StreamingResponse(gen_status(f"Rescheduled ID {ap_id} to {new_si} - {new_ei}"), media_type="text/event-stream")
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                    return StreamingResponse(gen_status(f"Appointment {ap_id}: {cur_si} to {cur_ei}. Status: {cur_st}"), media_type="text/event-stream")
                except Exception:
                    def gen_err():
                        yield "data: Error handling appointment\n\n"
                        yield "event: end\n\n"
                    return StreamingResponse(gen_err(), media_type="text/event-stream")
            # Check if this is a new booking request (not reschedule/cancel) - show form directly
            lowmsg = msg.lower()
            is_new_booking = bool(re.search(r"\b(book|schedule|appointment)\b", lowmsg)) and not bool(re.search(r"\b(cancel|reschedule|change|status)\b", lowmsg))
            if not ap_id and is_new_booking:
                def gen_form():
                    yield f"data: Please use the [booking form]({form_url}) to schedule your appointment. It shows available time slots and you can select a convenient time.\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return StreamingResponse(gen_form(), media_type="text/event-stream")
            patt = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})(?:[T\s](?P<start>\d{2}:\d{2})(?:\s*(?:to|-|until)\s*(?P<end>\d{2}:\d{2}))?)", re.IGNORECASE)
            m0 = patt.search(msg)
            si = None
            ei = None
            if m0:
                d = m0.group('date')
                st = m0.group('start')
                en = m0.group('end') or None
                if not en:
                    try:
                        sd = f"{d}T{st}:00"
                        from datetime import datetime, timedelta
                        start_dt = datetime.fromisoformat(sd)
                        end_dt = start_dt + timedelta(minutes=30)
                        ei = end_dt.isoformat()
                    except Exception:
                        ei = f"{d}T{st}:00"
                else:
                    ei = f"{d}T{en}:00"
                si = f"{d}T{st}:00"
            else:
                parsed = _parse_natural(msg)
                if parsed:
                    si, ei = parsed
            key = f"{body.org_id}:{bot_id}"
            st = _SESSION_STATE[key]
            if not si and st.get('start_iso'):
                si = st.get('start_iso')
            if not ei and st.get('end_iso'):
                ei = st.get('end_iso')
            if si:
                st['start_iso'] = si
            if ei:
                st['end_iso'] = ei
            _ensure_oauth_table(conn)
            _ensure_booking_settings_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                    (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                )
                row = cur.fetchone()
                cal_id, at_enc, rt_enc = (row[0] if row else None), (row[1] if row else None), (row[2] if row else None)
                cur.execute(
                    "select timezone, slot_duration_minutes, capacity_per_slot, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                    (normalize_org_id(body.org_id), body.org_id, bot_id),
                )
                bs = cur.fetchone()
            tzv = bs[0] if bs else None
            slotm = int(bs[1]) if bs and bs[1] else 30
            capacity = int(bs[2]) if bs and bs[2] else 1
            aw = None; tzv = None; min_notice=None; max_future=None
            try:
                cur.execute(
                    "select timezone, available_windows, min_notice_minutes, max_future_days from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                    (normalize_org_id(org_id), org_id, bot_id),
                )
                more = cur.fetchone()
                tzv = more[0] if more else None
                import json
                aw = None if (not more or more[1] is None) else (more[1] if isinstance(more[1], list) else json.loads(more[1]) if isinstance(more[1], str) else None)
                min_notice = int(more[2]) if more and more[2] else None
                max_future = int(more[3]) if more and more[3] else None
            except Exception:
                aw = None; tzv = None; min_notice=None; max_future=None
            try:
                rfraw = bs[3] if bs else None
                _json = __import__("json")
                required_fields = rfraw if isinstance(rfraw, list) else (_json.loads(rfraw) if isinstance(rfraw, str) else [])
            except Exception:
                required_fields = []
            svc = None
            try:
                from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth, create_event_oauth
                at = _decrypt(at_enc) if at_enc else None
                rt = _decrypt(rt_enc) if rt_enc else None
                svc = build_service_from_tokens(at, rt, None)
            except Exception:
                svc = None
            if not si or not ei:
                def gen_need_time():
                    text = "Could not parse date/time. Try formats like '2025-12-06 15:30' or 'tomorrow at 3pm for 30 minutes'. Or use the [booking form](" + form_url + ")"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_need_time(), media_type="text/event-stream")
            if not svc:
                def gen_need_cal():
                    text = "Calendar not connected. Please connect Google Calendar in the dashboard. Or use the [booking form](" + form_url + ")"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_need_cal(), media_type="text/event-stream")
            import datetime as _dt
            tmn = _dt.datetime.fromisoformat(si)
            tmx = _dt.datetime.fromisoformat(ei)
            items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
            info = {}
            try:
                em = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", msg)
                if em:
                    info["email"] = em.group(0)
                ph = re.search(r"\+?\d[\d \-]{7,}\d", msg)
                if ph:
                    import re as _re
                    info["phone"] = _re.sub(r"\D", "", ph.group(0))
                nm = re.search(r"(?:my name is|i am|this is)\s+([A-Za-z][A-Za-z .'-]{1,50})", msg, re.IGNORECASE)
                if nm:
                    info["name"] = nm.group(1).strip()
                nt = re.search(r"(?:purpose|note|reason)[:\-]\s*(.+)$", msg, re.IGNORECASE)
                if nt:
                    info["notes"] = nt.group(1).strip()
            except Exception:
                pass
            prev = st.get('info') or {}
            prev.update(info)
            st['info'] = prev
            missing = [f for f in (required_fields or []) if not prev.get(f)]
            if missing:
                def gen_need_fields():
                    text = ("Please provide: " + ", ".join(missing) + ". Or use the [booking form](" + form_url + ")")
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_need_fields(), media_type="text/event-stream")
            occ = len(items) if items else 0
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso=%s and end_iso=%s and status in ('scheduled','booked')",
                    (normalize_org_id(body.org_id), body.org_id, bot_id, si, ei),
                )
                occ_db = int(cur.fetchone()[0])
            if max(occ, occ_db) >= capacity:
                def gen_busy():
                    text = "That time is unavailable. Please suggest another time. Or use the [booking form](" + form_url + ")"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_busy(), media_type="text/event-stream")
            ext_id = None
            try:
                attns = ([prev.get("email")] if prev.get("email") else None)
                ext_id = create_event_oauth(svc, cal_id or "primary", "Appointment", si, ei, attns, tzv)
            except Exception:
                ext_id = None
            if not ext_id:
                def gen_fail():
                    text = "Calendar booking failed. Please try again after reconnecting Google Calendar."
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_fail(), media_type="text/event-stream")
            apid = None
            with conn.cursor() as cur:
                cur.execute(
                    "insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json, status, external_event_id) values (%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                    (normalize_org_id(body.org_id), bot_id, "Appointment", si, ei, (__import__("json").dumps(attns) if attns else None), "booked", ext_id),
                )
                r = cur.fetchone()
                apid = int(r[0]) if r else None
            _SESSION_STATE[key] = {}
            def gen_ok():
                text = f"Booked your appointment for {si} to {ei}. ID: {apid}"
                yield f"data: {text}\n\n"
                yield "event: end\n\n"
            _ensure_usage_table(conn)
            _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
            return StreamingResponse(gen_ok(), media_type="text/event-stream")
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
        system = (
            (system_prompt + " Keep responses short and informative.")
            if system_prompt
            else f"You are a {behavior} assistant. Use only the provided context. If the answer is not in context, say: \"I don't have that information.\" Keep responses short and informative."
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
              status text,
              external_event_id text,
              updated_at timestamptz default now(),
              created_at timestamptz default now()
            )
            """
        )
        try:
            cur.execute("alter table bot_appointments add column if not exists status text")
            cur.execute("alter table bot_appointments add column if not exists external_event_id text")
            cur.execute("alter table bot_appointments add column if not exists updated_at timestamptz default now()")
        except Exception:
            pass

def _ensure_oauth_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_calendar_oauth (
              org_id text not null,
              bot_id text not null,
              provider text not null,
              access_token_enc text,
              refresh_token_enc text,
              token_expiry timestamptz,
              calendar_id text,
              watch_channel_id text,
              watch_resource_id text,
              watch_expiration timestamptz,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id, provider)
            )
            """
        )

def _ensure_booking_settings_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_booking_settings (
              org_id text not null,
              bot_id text not null,
              timezone text,
              available_windows jsonb,
              slot_duration_minutes int default 30,
              capacity_per_slot int default 1,
              min_notice_minutes int default 60,
              max_future_days int default 60,
              suggest_strategy text default 'next_best',
              required_user_fields jsonb,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id)
            )
            """
        )
        try:
            cur.execute("alter table bot_booking_settings add column if not exists required_user_fields jsonb")
        except Exception:
            pass

def _ensure_audit_logs_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists booking_audit_logs (
              id bigserial primary key,
              org_id text not null,
              bot_id text not null,
              appointment_id bigint,
              action text not null,
              metadata jsonb,
              created_at timestamptz default now()
            )
            """
        )

def _ensure_notifications_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists booking_notifications (
              id bigserial primary key,
              org_id text not null,
              bot_id text not null,
              appointment_id bigint,
              type text not null,
              recipient text,
              payload jsonb,
              status text default 'queued',
              created_at timestamptz default now(),
              updated_at timestamptz default now()
            )
            """
        )

def _log_audit(conn, org_id: str, bot_id: str, appointment_id: int, action: str, metadata: dict):
    with conn.cursor() as cur:
        cur.execute(
            "insert into booking_audit_logs (org_id, bot_id, appointment_id, action, metadata) values (%s,%s,%s,%s,%s)",
            (normalize_org_id(org_id), bot_id, appointment_id, action, __import__("json").dumps(metadata or {})),
        )

def _enqueue_notification(conn, org_id: str, bot_id: str, appointment_id: int, typ: str, recipient: str, payload: dict):
    with conn.cursor() as cur:
        cur.execute(
            "insert into booking_notifications (org_id, bot_id, appointment_id, type, recipient, payload) values (%s,%s,%s,%s,%s,%s)",
            (normalize_org_id(org_id), bot_id, appointment_id, typ, recipient, __import__("json").dumps(payload or {})),
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

@router.get("/bots/{bot_id}/calendar/config")
def get_calendar_config(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_calendar_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select provider, calendar_id, timezone from bot_calendar_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(org_id), org_id, bot_id),
            )
            row = cur.fetchone()
        if not row:
            return {"provider": None, "calendar_id": None, "timezone": None}
        return {"provider": row[0], "calendar_id": row[1], "timezone": row[2]}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/calendar/google/oauth/start")
def google_oauth_start(bot_id: str, org_id: str, redirect_uri: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    url = None
    try:
        from app.services.calendar_google import oauth_authorize_url
        url = oauth_authorize_url(org_id, bot_id, redirect_uri)
    except Exception:
        url = None
    if not url:
        raise HTTPException(status_code=500, detail="oauth not configured")
    return {"url": url}

@router.get("/calendar/google/oauth/callback")
def google_oauth_callback(code: str, state: Optional[str] = None, redirect_uri: str = ""):
    try:
        import urllib.parse
        raw = urllib.parse.unquote(state or "")
        qs = urllib.parse.parse_qs(raw)
        org_id = (qs.get("org") or [None])[0]
        bot_id = (qs.get("bot") or [None])[0]
    except Exception:
        org_id = None
        bot_id = None
    if not org_id or not bot_id:
        raise HTTPException(status_code=400, detail="invalid state")
    from app.db import get_conn, normalize_org_id
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        _ensure_calendar_settings_table(conn)
        data = None
        try:
            from app.services.calendar_google import exchange_code_for_tokens, _encrypt
            data = exchange_code_for_tokens(code, redirect_uri)
        except Exception:
            data = None
        if not data or not data.get("access_token"):
            raise HTTPException(status_code=500, detail="oauth exchange failed")
        at = _encrypt(data.get("access_token"))
        rt = _encrypt(data.get("refresh_token")) if data.get("refresh_token") else None
        exp = data.get("expiry")
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot_calendar_oauth (org_id, bot_id, provider, access_token_enc, refresh_token_enc, token_expiry, calendar_id)
                values (%s,%s,%s,%s,%s,%s,%s)
                on conflict (org_id, bot_id, provider)
                do update set access_token_enc=excluded.access_token_enc, refresh_token_enc=excluded.refresh_token_enc, token_expiry=excluded.token_expiry, calendar_id=coalesce(bot_calendar_oauth.calendar_id, excluded.calendar_id), updated_at=now()
                returning calendar_id
                """,
                (normalize_org_id(org_id), bot_id, "google", at, rt, exp, "primary"),
            )
            row = cur.fetchone()
            cal_id = row[0] if row else "primary"
            cur.execute(
                """
                insert into bot_calendar_settings (org_id, bot_id, provider, calendar_id)
                values (%s,%s,%s,%s)
                on conflict (org_id, bot_id, provider)
                do update set calendar_id=excluded.calendar_id, updated_at=now()
                """,
                (normalize_org_id(org_id), bot_id, "google", cal_id or "primary"),
            )
        return {"connected": True, "calendar_id": cal_id or "primary"}
    finally:
        conn.close()

class BookingSettingsBody(BaseModel):
    org_id: str
    timezone: Optional[str] = None
    available_windows: Optional[list] = None
    slot_duration_minutes: Optional[int] = None
    capacity_per_slot: Optional[int] = None
    min_notice_minutes: Optional[int] = None
    max_future_days: Optional[int] = None
    suggest_strategy: Optional[str] = None
    required_user_fields: Optional[list] = None

@router.post("/bots/{bot_id}/booking/settings")
def set_booking_settings(bot_id: str, body: BookingSettingsBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_booking_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot_booking_settings (org_id, bot_id, timezone, available_windows, slot_duration_minutes, capacity_per_slot, min_notice_minutes, max_future_days, suggest_strategy, required_user_fields)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (org_id, bot_id)
                do update set timezone=excluded.timezone, available_windows=excluded.available_windows, slot_duration_minutes=excluded.slot_duration_minutes, capacity_per_slot=excluded.capacity_per_slot, min_notice_minutes=excluded.min_notice_minutes, max_future_days=excluded.max_future_days, suggest_strategy=excluded.suggest_strategy, required_user_fields=excluded.required_user_fields, updated_at=now()
                returning timezone, available_windows, slot_duration_minutes, capacity_per_slot, min_notice_minutes, max_future_days, suggest_strategy, required_user_fields
                """,
                (
                    normalize_org_id(body.org_id),
                    bot_id,
                    body.timezone,
                    None if body.available_windows is None else __import__("json").dumps(body.available_windows),
                    body.slot_duration_minutes,
                    body.capacity_per_slot,
                    body.min_notice_minutes,
                    body.max_future_days,
                    body.suggest_strategy,
                    None if body.required_user_fields is None else __import__("json").dumps(body.required_user_fields),
                ),
            )
            row = cur.fetchone()
        import json
        aw = None
        try:
            if row[1] is None:
                aw = None
            elif isinstance(row[1], (list, dict)):
                aw = row[1]
            else:
                aw = json.loads(row[1])
        except Exception:
            aw = None
        return {
            "timezone": row[0],
            "available_windows": aw,
            "slot_duration_minutes": row[2],
            "capacity_per_slot": row[3],
            "min_notice_minutes": row[4],
            "max_future_days": row[5],
            "suggest_strategy": row[6],
            "required_user_fields": (None if row[7] is None else (row[7] if isinstance(row[7], list) else json.loads(row[7]) if isinstance(row[7], str) else None)),
        }
    finally:
        conn.close()

@router.get("/bots/{bot_id}/booking/settings")
def get_booking_settings(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, org_id)
    finally:
        conn.close()
    if public_api_key:
        if x_bot_key and x_bot_key == public_api_key:
            pass
        elif authorization:
            _require_auth(authorization, org_id)
        elif not x_bot_key:
            pass
        else:
            raise HTTPException(status_code=403, detail="Invalid bot key")
    else:
        _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_booking_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select timezone, available_windows, slot_duration_minutes, capacity_per_slot, min_notice_minutes, max_future_days, suggest_strategy, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(org_id), org_id, bot_id),
            )
            row = cur.fetchone()
        import json
        if not row:
            return {"timezone": None, "available_windows": [], "slot_duration_minutes": 30, "capacity_per_slot": 1, "min_notice_minutes": 60, "max_future_days": 60, "suggest_strategy": "next_best", "required_user_fields": ["name","email"]}
        aw = []
        try:
            if row[1] is None:
                aw = []
            elif isinstance(row[1], (list, dict)):
                aw = row[1] if isinstance(row[1], list) else []
            else:
                aw = json.loads(row[1])
        except Exception:
            aw = []
        ruf = None
        try:
            if row[7] is None:
                ruf = None
            elif isinstance(row[7], (list, dict)):
                ruf = row[7] if isinstance(row[7], list) else None
            else:
                ruf = json.loads(row[7])
        except Exception:
            ruf = None
        return {
            "timezone": row[0],
            "available_windows": aw,
            "slot_duration_minutes": row[2],
            "capacity_per_slot": row[3],
            "min_notice_minutes": row[4],
            "max_future_days": row[5],
            "suggest_strategy": row[6],
            "required_user_fields": ruf,
        }
    finally:
        conn.close()

@router.get("/bots/{bot_id}/booking/availability")
def booking_availability(bot_id: str, org_id: str, time_min_iso: str, time_max_iso: str, authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    try:
        conn = get_conn()
        try:
            _ensure_booking_settings_table(conn)
            _ensure_oauth_table(conn)
            behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, org_id)
            if public_api_key:
                if x_bot_key and x_bot_key == public_api_key:
                    pass
                elif authorization:
                    _require_auth(authorization, org_id)
                elif not x_bot_key:
                    pass
                else:
                    raise HTTPException(status_code=403, detail="Invalid bot key")
            with conn.cursor() as cur:
                cur.execute(
                    "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                    (normalize_org_id(org_id), org_id, bot_id, "google"),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="calendar not connected")
                cal_id, at_enc, rt_enc, exp = row
                cur.execute(
                    "select timezone, slot_duration_minutes, capacity_per_slot, available_windows, min_notice_minutes, max_future_days from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                    (normalize_org_id(org_id), org_id, bot_id),
                )
                bs = cur.fetchone()
            slotm = int(bs[1]) if bs and bs[1] else 30
            capacity = int(bs[2]) if bs and bs[2] else 1
            tzv = bs[0] if bs else None
            import json
            aw = None if (not bs or bs[3] is None) else (bs[3] if isinstance(bs[3], list) else json.loads(bs[3]) if isinstance(bs[3], str) else None)
            min_notice = int(bs[4]) if bs and bs[4] else None
            max_future = int(bs[5]) if bs and bs[5] else None
            from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth
            at = _decrypt(at_enc) if at_enc else None
            rt = _decrypt(rt_enc) if rt_enc else None
            svc = build_service_from_tokens(at, rt, exp)
            if not svc:
                raise HTTPException(status_code=500, detail="calendar service unavailable")
            items = list_events_oauth(svc, cal_id or "primary", time_min_iso, time_max_iso)
            extra = {}
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select start_iso, count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso>=%s and end_iso<=%s and status in ('scheduled','booked') group by start_iso",
                        (normalize_org_id(org_id), org_id, bot_id, time_min_iso, time_max_iso),
                    )
                    rows = cur.fetchall()
                    extra = {r[0]: int(r[1]) for r in rows}
            except Exception:
                extra = {}
            from app.services.booking import compute_availability
            slots = compute_availability(time_min_iso, time_max_iso, slotm, capacity, items, tzv, aw, extra, min_notice, max_future)
            return {"slots": slots}
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class CreateAppointmentBody(BaseModel):
    org_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    start_iso: str
    end_iso: str

@router.post("/bots/{bot_id}/booking/appointment")
def booking_create(bot_id: str, body: CreateAppointmentBody, authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        _ensure_booking_settings_table(conn)
        _ensure_oauth_table(conn)
        _ensure_appointments_table(conn)
        _ensure_audit_logs_table(conn)
        _ensure_notifications_table(conn)
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, body.org_id)
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                if authorization:
                    _require_auth(authorization, body.org_id)
                else:
                    raise HTTPException(status_code=403, detail="Invalid bot key")
        with conn.cursor() as cur:
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc, exp = row
            cur.execute(
                "select timezone, slot_duration_minutes, capacity_per_slot, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            bs = cur.fetchone()
        tzv = bs[0] if bs else None
        slotm = int(bs[1]) if bs and bs[1] else 30
        capacity = int(bs[2]) if bs and bs[2] else 1
        try:
            rfraw = bs[3] if bs else None
            _json = __import__("json")
            required_fields = rfraw if isinstance(rfraw, list) else (_json.loads(rfraw) if isinstance(rfraw, str) else [])
        except Exception:
            required_fields = []
        info = {"name": body.name, "email": body.email, "phone": body.phone, "notes": body.notes}
        missing = [f for f in (required_fields or []) if not info.get(f)]
        if missing:
            raise HTTPException(status_code=400, detail="missing fields: " + ", ".join(missing))
        from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth, create_event_oauth
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        svc = build_service_from_tokens(at, rt, exp)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service unavailable")
        import datetime as _dt
        tmn = _dt.datetime.fromisoformat(body.start_iso)
        tmx = _dt.datetime.fromisoformat(body.end_iso)
        items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
        occ = len(items) if items else 0
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso=%s and end_iso=%s and status in ('scheduled','booked')",
                (normalize_org_id(body.org_id), body.org_id, bot_id, body.start_iso, body.end_iso),
            )
            occ_db = int(cur.fetchone()[0])
        # Business hours enforcement
        try:
            cur.execute(
                "select timezone, available_windows, min_notice_minutes, max_future_days from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            srow = cur.fetchone()
            tzv = srow[0] if srow else None
            import json
            aw = None if (not srow or srow[1] is None) else (srow[1] if isinstance(srow[1], list) else json.loads(srow[1]) if isinstance(srow[1], str) else None)
        except Exception:
            tzv=None; aw=None
        from datetime import datetime
        def _in_hours(si):
            if not aw:
                return True
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(tzv) if tzv else None
                dt = datetime.fromisoformat(si.replace("Z","+00:00"))
                local = dt.astimezone(tz) if tz else dt
                day = ["mon","tue","wed","thu","fri","sat","sun"][local.weekday()]
                minutes = local.hour*60 + local.minute
                for w in aw:
                    d=(w.get("day") or "").strip().lower()[:3]
                    if d!=day: continue
                    sh,sm=[int(x) for x in (w.get("start") or "00:00").split(":",1)]
                    eh,em=[int(x) for x in (w.get("end") or "23:59").split(":",1)]
                    if minutes>=sh*60+sm and minutes<eh*60+em:
                        return True
                return False
            except Exception:
                return True
        if not _in_hours(body.start_iso):
            raise HTTPException(status_code=422, detail="outside business hours")
        if max(occ, occ_db) >= capacity:
            raise HTTPException(status_code=409, detail="slot unavailable")
        attns = ([body.email] if body.email else None)
        desc = f"Appointment\nName: {body.name or ''}\nEmail: {body.email or ''}\nPhone: {body.phone or ''}\nNotes: {body.notes or ''}"
        ext_id = create_event_oauth(svc, cal_id or "primary", "Appointment", body.start_iso, body.end_iso, attns, tzv, desc)
        if not ext_id:
            raise HTTPException(status_code=500, detail="booking failed")
        with conn.cursor() as cur:
            cur.execute(
                "insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json, status, external_event_id) values (%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (normalize_org_id(body.org_id), bot_id, "Appointment", body.start_iso, body.end_iso, (__import__("json").dumps(info) if info else None), "booked", ext_id),
            )
            apid = int(cur.fetchone()[0])
        try:
            from app.services.calendar_google import update_event_oauth
            desc = f"Appointment ID: {apid}\nName: {body.name or ''}\nEmail: {body.email or ''}\nPhone: {body.phone or ''}\nNotes: {body.notes or ''}"
            patch = {
                "summary": "Appointment #"+str(apid)+" - "+(body.name or ""),
                "description": desc,
                "extendedProperties": {"private": {"appointment_id": str(apid), "org_id": body.org_id, "bot_id": bot_id}},
            }
            update_event_oauth(svc, cal_id or "primary", ext_id, patch)
        except Exception:
            _log_audit(conn, body.org_id, bot_id, apid, "calendar_patch_error", {"ext_id": ext_id})
        _log_audit(conn, body.org_id, bot_id, apid, "create", {"start_iso": body.start_iso, "end_iso": body.end_iso})
        if body.email:
            _enqueue_notification(conn, body.org_id, bot_id, apid, "confirmation", body.email, {"appointment_id": apid})
        return {"appointment_id": apid, "external_event_id": ext_id}
    finally:
        conn.close()

class RescheduleBody(BaseModel):
    org_id: str
    new_start_iso: str
    new_end_iso: str

@router.post("/bots/{bot_id}/booking/appointment/{appointment_id}/reschedule")
def booking_reschedule(bot_id: str, appointment_id: int, body: RescheduleBody, authorization: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        _require_auth(authorization, body.org_id)
        _ensure_oauth_table(conn)
        _ensure_audit_logs_table(conn)
        _ensure_notifications_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select external_event_id from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                (appointment_id, normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            ev_id = row[0]
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            c = cur.fetchone()
            if not c:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc, exp = c
            cur.execute(
                "select timezone, slot_duration_minutes, capacity_per_slot from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            bs = cur.fetchone()
        tzv = bs[0] if bs else None
        capacity = int(bs[2]) if bs and bs[2] else 1
        from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth, update_event_oauth
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        svc = build_service_from_tokens(at, rt, exp)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service unavailable")
        import datetime as _dt
        tmn = _dt.datetime.fromisoformat(body.new_start_iso)
        tmx = _dt.datetime.fromisoformat(body.new_end_iso)
        items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso=%s and end_iso=%s and status in ('scheduled','booked')",
                (normalize_org_id(body.org_id), body.org_id, bot_id, body.new_start_iso, body.new_end_iso),
            )
            occ_db = int(cur.fetchone()[0])
        # Business hours enforcement for reschedule
        try:
            cur.execute(
                "select timezone, available_windows from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            srow = cur.fetchone()
            tzv = srow[0] if srow else None
            import json
            aw = None if (not srow or srow[1] is None) else (srow[1] if isinstance(srow[1], list) else json.loads(srow[1]) if isinstance(srow[1], str) else None)
        except Exception:
            tzv=None; aw=None
        from datetime import datetime
        def _in_hours(si):
            if not aw:
                return True
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(tzv) if tzv else None
                dt = datetime.fromisoformat(si.replace("Z","+00:00"))
                local = dt.astimezone(tz) if tz else dt
                day = ["mon","tue","wed","thu","fri","sat","sun"][local.weekday()]
                minutes = local.hour*60 + local.minute
                for w in aw:
                    d=(w.get("day") or "").strip().lower()[:3]
                    if d!=day: continue
                    sh,sm=[int(x) for x in (w.get("start") or "00:00").split(":",1)]
                    eh,em=[int(x) for x in (w.get("end") or "23:59").split(":",1)]
                    if minutes>=sh*60+sm and minutes<eh*60+em:
                        return True
                return False
            except Exception:
                return True
        if not _in_hours(body.new_start_iso):
            raise HTTPException(status_code=422, detail="outside business hours")
        if max(len(items or []), occ_db) >= capacity:
            raise HTTPException(status_code=409, detail="slot unavailable")
        ok = update_event_oauth(svc, cal_id or "primary", ev_id, {"start": {"dateTime": body.new_start_iso, **({"timeZone": tzv} if tzv else {})}, "end": {"dateTime": body.new_end_iso, **({"timeZone": tzv} if tzv else {})}})
        if not ok:
            raise HTTPException(status_code=500, detail="reschedule failed")
        with conn.cursor() as cur:
            cur.execute(
                "update bot_appointments set start_iso=%s, end_iso=%s, updated_at=now() where id=%s",
                (body.new_start_iso, body.new_end_iso, appointment_id),
            )
        _log_audit(conn, body.org_id, bot_id, appointment_id, "reschedule", {"new_start_iso": body.new_start_iso, "new_end_iso": body.new_end_iso})
        return {"rescheduled": True}
    finally:
        conn.close()

class CancelBody(BaseModel):
    org_id: str

@router.post("/bots/{bot_id}/booking/appointment/{appointment_id}/cancel")
def booking_cancel(bot_id: str, appointment_id: int, body: CancelBody, authorization: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        _require_auth(authorization, body.org_id)
        _ensure_oauth_table(conn)
        _ensure_audit_logs_table(conn)
        _ensure_notifications_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select external_event_id from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                (appointment_id, normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            ev_id = row[0]
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            c = cur.fetchone()
            if not c:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc, exp = c
        from app.services.calendar_google import _decrypt, build_service_from_tokens, delete_event_oauth
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        svc = build_service_from_tokens(at, rt, exp)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service unavailable")
        ok = delete_event_oauth(svc, cal_id or "primary", ev_id)
        if not ok:
            raise HTTPException(status_code=500, detail="cancel failed")
        with conn.cursor() as cur:
            cur.execute("update bot_appointments set status=%s, updated_at=now() where id=%s", ("cancelled", appointment_id))
        _log_audit(conn, body.org_id, bot_id, appointment_id, "cancel", {})
        return {"cancelled": True}
    finally:
        conn.close()

@router.get("/form/{bot_id}", response_class=HTMLResponse)
def booking_form(bot_id: str, org_id: str, bot_key: Optional[str] = None):
    base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
    api_url = base.rstrip('/')
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Book Appointment</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1\">"
        "<style>"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:12px}"
        ".container{background:#fff;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);max-width:500px;width:100%;padding:32px}"
        ".header{margin-bottom:28px}"
        ".header h1{font-size:28px;font-weight:700;color:#1a1a1a;margin-bottom:8px}"
        ".header p{font-size:14px;color:#666}"
        ".form-group{margin-bottom:20px}"
        ".form-group label{display:block;font-size:13px;font-weight:600;color:#333;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px}"
        ".form-group input[type='text'],.form-group input[type='email'],.form-group input[type='tel'],.form-group input[type='date']{width:100%;padding:12px 14px;border:2px solid #e0e0e0;border-radius:8px;font-size:14px;transition:all 0.3s ease;font-family:inherit}"
        ".form-group input:focus{outline:none;border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,0.1)}"
        ".form-group input.error{border-color:#dc2626}"
        ".form-group.required label::after{content:' *';color:#dc2626}"
        ".section{margin-bottom:24px;padding-bottom:24px;border-bottom:1px solid #e5e5e5}"
        ".section:last-of-type{border-bottom:none}"
        ".time-slots{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px;margin-top:12px}"
        ".time-slot{padding:10px;border:2px solid #e0e0e0;border-radius:8px;background:#f9f9f9;cursor:pointer;text-align:center;font-size:13px;font-weight:600;color:#333;transition:all 0.2s ease}"
        ".time-slot:hover{border-color:#667eea;background:#f0f4ff}"
        ".time-slot.selected{background:#667eea;color:#fff;border-color:#667eea}"
        ".slot-status{font-size:13px;color:#666;padding:12px;text-align:center;background:#f5f5f5;border-radius:8px;margin-top:12px}"
        ".loading-spinner{display:inline-block;width:14px;height:14px;border:2px solid #e0e0e0;border-top:2px solid #667eea;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:6px}"
        "@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}"
        ".button-group{display:flex;gap:12px;margin-top:28px}"
        "#submit{flex:1;padding:14px 24px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:700;cursor:pointer;transition:all 0.3s ease;text-transform:uppercase;letter-spacing:0.5px}"
        "#submit:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(102,126,234,0.4)}"
        "#submit:active{transform:translateY(0)}"
        "#submit:disabled{opacity:0.6;cursor:not-allowed;transform:none}"
        "#out{margin-top:16px;padding:14px;border-radius:8px;font-size:14px;font-weight:600}"
        "#out.success{background:#d1fae5;color:#065f46;border-left:4px solid #10b981}"
        "#out.error{background:#fee2e2;color:#7f1d1d;border-left:4px solid #dc2626}"
        "#out.info{background:#dbeafe;color:#1e40af;border-left:4px solid #3b82f6}"
        ".required-fields{font-size:12px;color:#999;margin-top:12px}"
        ".success-icon{color:#10b981;margin-right:8px}"
        ".error-icon{color:#dc2626;margin-right:8px}"
        "</style>"
        "</head><body>"
        "<div class=\"container\">"
        "<div class=\"header\"><h1>Book Appointment</h1><p>Select your preferred date and time</p></div>"
        "<div id=\"form\">"
        "<div class=\"section\">"
        "<div class=\"form-group required\"><label>Full Name</label><input id=\"name\" type=\"text\" placeholder=\"John Doe\"></div>"
        "<div class=\"form-group required\"><label>Email</label><input id=\"email\" type=\"email\" placeholder=\"john@example.com\"></div>"
        "<div class=\"form-group\"><label>Phone Number</label><input id=\"phone\" type=\"tel\" placeholder=\"+1 (555) 123-4567\"></div>"
        "<div class=\"form-group\"><label>Notes or Reason</label><input id=\"notes\" type=\"text\" placeholder=\"Brief description...\"></div>"
        "</div>"
        "<div class=\"section\">"
        "<div class=\"form-group required\"><label>Select Date</label><input id=\"date\" type=\"date\"></div>"
        "<div class=\"time-slots\" id=\"slots\"></div>"
        "<div class=\"slot-status\" id=\"slot-status\" style=\"display:none\"></div>"
        "</div>"
        "<div class=\"button-group\"><button id=\"submit\" type=\"button\">Book Appointment</button></div>"
        "<div class=\"required-fields\">* Required fields</div>"
        "</div>"
        "<div id=\"out\"></div>"
        "</div>"
        "<script>"
        "const ORG='" + org_id + "',BOT='" + bot_id + "',BOT_KEY='" + (bot_key or '') + "',API='" + api_url + "';let chosen=null,loading=false;"
        "function showMsg(t,ty){ty=ty||'info';const o=document.getElementById('out');o.textContent=t;o.className=ty;o.style.display='block';}"
        "function setErr(id,e){const el=document.getElementById(id);if(el)el.classList.toggle('error',e);}"
        "async function loadReq(){try{const h={};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;const r=await fetch(API+'/api/bots/'+BOT+'/booking/settings?org_id='+ORG,{headers:h});const d=await r.json();window.REQ=d.required_user_fields||[];}catch(e){console.error('loadReq error:',e);window.REQ=[];}}"
        "async function loadSlots(){const dt=document.getElementById('date').value;if(!dt){showMsg('Please select a date','error');return;}loading=true;const h={};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;const el=document.getElementById('slots'),st=document.getElementById('slot-status');el.innerHTML='';st.innerHTML='<span class=\"loading-spinner\"></span> Loading...';st.style.display='block';"
        "const fetch4=async(day)=>{const tm1=day+'T00:00:00',tm2=day+'T23:59:59';const url=API+'/api/bots/'+BOT+'/booking/availability?org_id='+ORG+'&time_min_iso='+encodeURIComponent(tm1)+'&time_max_iso='+encodeURIComponent(tm2);try{const r=await fetch(url,{headers:h});if(!r.ok){const err=await r.text();console.error('API error for',day,':',r.status,err);return{slots:[]};}const d=await r.json();return d;}catch(e){console.error('Fetch error for',day,':',e);return{slots:[]};}};try{const d=await fetch4(dt);const slots=Array.isArray(d.slots)?d.slots:[];console.log('Slots loaded:',slots);el.innerHTML='';if(slots.length===0){st.textContent='No available slots. Checking next 7 days...';for(let i=1;i<=7;i++){const nxt=new Date(new Date(dt).getTime()+i*86400000);const day2=nxt.toISOString().slice(0,10);const d2=await fetch4(day2);const sl2=Array.isArray(d2.slots)?d2.slots:[];if(sl2.length>0){document.getElementById('date').value=day2;loadSlots();return;}}st.textContent='No available slots in the next 7 days';}else{st.style.display='none';slots.forEach(s=>{const b=document.createElement('button');b.type='button';b.className='time-slot';b.textContent=new Date(s.start).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});b.onclick=()=>{chosen=s;document.querySelectorAll('.time-slot').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');st.style.display='none';};el.appendChild(b);});}}catch(e){console.error('Load error:',e);st.textContent='Error: '+e.message;}finally{loading=false;}}"
        "document.getElementById('date').addEventListener('change',loadSlots);"
        "document.getElementById('submit').addEventListener('click',async()=>{const nm=document.getElementById('name').value.trim(),em=document.getElementById('email').value.trim(),ph=document.getElementById('phone').value.trim(),nt=document.getElementById('notes').value.trim();const req=window.REQ||[];const miss=req.filter(f=>{if(f==='name')return !nm;if(f==='email')return !em;if(f==='phone')return !ph;if(f==='notes')return !nt;return false;});['name','email','phone','notes'].forEach(id=>{setErr(id,miss.includes(id));});if(miss.length>0){showMsg('Fill required: '+miss.join(', '),'error');return;}if(!chosen){showMsg('Select a time slot','error');return;}const pay={org_id:ORG,name:nm,email:em,phone:ph,notes:nt,start_iso:chosen.start,end_iso:chosen.end};const h={'Content-Type':'application/json'};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;const btn=document.getElementById('submit');btn.disabled=true;btn.textContent='Booking...';try{const r=await fetch(API+'/api/bots/'+BOT+'/booking/appointment',{method:'POST',headers:h,body:JSON.stringify(pay)});if(!r.ok){const dat=await r.json().catch(()=>({}));showMsg('Error: '+(dat.detail||'Error '+r.status),'error');btn.disabled=false;btn.textContent='Book Appointment';return;}const dat=await r.json();const startDate=new Date(chosen.start);const timeStr=startDate.toLocaleString();const msg='Appointment booked successfully!\\n\\nBooking ID: '+dat.appointment_id+'\\nName: '+nm+'\\nEmail: '+em+(ph?'\\nPhone: '+ph:'')+'\\nTime: '+timeStr+(nt?'\\nNotes: '+nt:'');showMsg('Booked! ID: '+dat.appointment_id,'success');btn.textContent='Success';document.getElementById('form').style.opacity='0.5';if(window.parent&&window.parent.postMessage){window.parent.postMessage({type:'BOOKING_SUCCESS',message:msg,bookingId:dat.appointment_id,details:{name:nm,email:em,phone:ph,notes:nt,time:timeStr}},'*');}setTimeout(()=>{window.close();},2000);}catch(e){console.error('Submit error:',e);showMsg('Request failed','error');btn.disabled=false;btn.textContent='Book Appointment';}});"
        "loadReq();(function(){const d=document.getElementById('date');if(d){const today=new Date();d.value=today.toISOString().slice(0,10);loadSlots();}})();"
        "</script>"
        "</body></html>"
    )
    return html

@router.get("/bots/{bot_id}/calendar/events")
def list_calendar_events(bot_id: str, org_id: str, time_min_iso: str, time_max_iso: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    _rate_limit(bot_id, org_id)
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(org_id), org_id, bot_id, "google"),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc = row
        from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        svc = build_service_from_tokens(at or "", rt, None)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service error")
        items = list_events_oauth(svc, cal_id or "primary", time_min_iso, time_max_iso)
        # Augment with appointment details from DB so frontend shows clear titles/descriptions
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "select id, external_event_id, attendees_json from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso>=%s and end_iso<=%s",
                    (normalize_org_id(org_id), org_id, bot_id, time_min_iso, time_max_iso),
                )
                rows = cur.fetchall() or []
            amap = {}
            for r in rows:
                ap_id = int(r[0]); ext = r[1]; att = r[2]
                name = ""; email = ""; phone = ""; notes = ""
                try:
                    import json
                    info = json.loads(att) if isinstance(att, str) else (att if isinstance(att, dict) else {})
                    name = info.get("name") or ""
                    email = info.get("email") or ""
                    phone = info.get("phone") or ""
                    notes = info.get("notes") or ""
                except Exception:
                    pass
                amap[ext] = {"summary": f"Appointment #{ap_id} - {name}", "description": f"Appointment ID: {ap_id}\nName: {name}\nEmail: {email}\nPhone: {phone}\nNotes: {notes}"}
            for it in (items or []):
                ext = it.get("id")
                if ext and ext in amap:
                    meta = amap[ext]
                    # Override summary/description for clarity in dashboard modal
                    it["summary"] = meta["summary"]
                    it["description"] = meta["description"]
        except Exception:
            pass
        return {"events": items}
    finally:
        conn.close()

class BookingRequestBody(BaseModel):
    org_id: str
    summary: str
    start_iso: str
    end_iso: str
    attendees: Optional[List[str]] = None

 

@router.post("/bots/{bot_id}/booking/book")
def booking_book(bot_id: str, body: BookingRequestBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    _rate_limit(bot_id, body.org_id)
    from app.db import get_conn, normalize_org_id
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        _ensure_booking_settings_table(conn)
        _ensure_appointments_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc = row
        at = __import__("app.services.calendar_google", fromlist=["_decrypt"])._decrypt(at_enc) if at_enc else None
        rt = __import__("app.services.calendar_google", fromlist=["_decrypt"])._decrypt(rt_enc) if rt_enc else None
        svc = __import__("app.services.calendar_google", fromlist=["build_service_from_tokens"]).build_service_from_tokens(at or "", rt, None)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service error")
        try:
            c2 = psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=False)
        except Exception:
            c2 = conn
        try:
            with c2.cursor() as cur2:
                cur2.execute(
                    """
                    insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json, status)
                    values (%s,%s,%s,%s,%s,%s,%s)
                    returning id
                    """,
                    (
                        normalize_org_id(body.org_id),
                        bot_id,
                        body.summary,
                        body.start_iso,
                        body.end_iso,
                        None if body.attendees is None else __import__("json").dumps(body.attendees),
                        "scheduled",
                    ),
                )
                rid = int(cur2.fetchone()[0])
                ext_id = __import__("app.services.calendar_google", fromlist=["create_event_oauth"]).create_event_oauth(svc, cal_id or "primary", body.summary, body.start_iso, body.end_iso, body.attendees, None)
                if not ext_id:
                    raise Exception("calendar create failed")
                cur2.execute("update bot_appointments set external_event_id=%s, updated_at=now() where id=%s", (ext_id, rid))
            try:
                c2.commit()
            except Exception:
                pass
            return {"scheduled": True, "appointment_id": rid, "external_event_id": ext_id}
        except Exception:
            try:
                c2.rollback()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="booking failed")
        finally:
            try:
                if c2 is not conn:
                    c2.close()
            except Exception:
                pass
    finally:
        conn.close()

class CancelBody(BaseModel):
    org_id: str
    appointment_id: int

@router.post("/bots/{bot_id}/booking/cancel")
def booking_cancel(bot_id: str, body: CancelBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    _rate_limit(bot_id, body.org_id)
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        with conn.cursor() as cur:
            cur.execute("select external_event_id from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s", (body.appointment_id, normalize_org_id(body.org_id), body.org_id, bot_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            ext_id = row[0]
            cur.execute("select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s", (normalize_org_id(body.org_id), body.org_id, bot_id, "google"))
            cr = cur.fetchone()
        from app.services.calendar_google import _decrypt, build_service_from_tokens, delete_event_oauth
        at = _decrypt(cr[1]) if cr and cr[1] else None
        rt = _decrypt(cr[2]) if cr and cr[2] else None
        svc = build_service_from_tokens(at or "", rt, None)
        ok = delete_event_oauth(svc, (cr[0] or "primary"), ext_id) if (svc and ext_id) else True
        with conn.cursor() as cur:
            cur.execute("update bot_appointments set status='cancelled', updated_at=now() where id=%s", (body.appointment_id,))
        return {"cancelled": True}
    finally:
        conn.close()

class RescheduleBody(BaseModel):
    org_id: str
    appointment_id: int
    start_iso: str
    end_iso: str

@router.post("/bots/{bot_id}/booking/reschedule")
def booking_reschedule(bot_id: str, body: RescheduleBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    _rate_limit(bot_id, body.org_id)

@router.get("/bots/{bot_id}/booking/appointments")
def booking_list(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    _rate_limit(bot_id, org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id, summary, start_iso, end_iso, external_event_id, status, attendees_json from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s order by created_at desc",
                (normalize_org_id(org_id), org_id, bot_id),
            )
            rows = cur.fetchall()
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(org_id), org_id, bot_id, "google"),
            )
            oauth_row = cur.fetchone()
        import json
        def _parse_attendees(raw):
            if raw is None:
                return {}
            if isinstance(raw, dict):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return {}
        def _flatten(info: dict):
            return {
                "name": info.get("name"),
                "email": info.get("email"),
                "phone": info.get("phone"),
                "notes": info.get("notes") or info.get("reason") or info.get("note"),
                "info": info,
            }
        svc = None; cal_id = None
        if oauth_row:
            try:
                from app.services.calendar_google import _decrypt, build_service_from_tokens, get_event_oauth
                cal_id = oauth_row[0]
                at = _decrypt(oauth_row[1]) if oauth_row[1] else None
                rt = _decrypt(oauth_row[2]) if oauth_row[2] else None
                svc = build_service_from_tokens(at, rt, oauth_row[3])
            except Exception:
                svc = None
        def _merge_with_desc(info: dict, ev):
            if not ev:
                return info
            desc = ev.get("description") or ""
            lines = desc.splitlines()
            out = dict(info)
            for ln in lines:
                l = ln.strip()
                if l.lower().startswith("name:") and not out.get("name"):
                    out["name"] = l.split(":",1)[1].strip()
                elif l.lower().startswith("email:") and not out.get("email"):
                    out["email"] = l.split(":",1)[1].strip()
                elif l.lower().startswith("phone:") and not out.get("phone"):
                    out["phone"] = l.split(":",1)[1].strip()
                elif l.lower().startswith("notes:") and not out.get("notes"):
                    out["notes"] = l.split(":",1)[1].strip()
            return out
        appts = []
        for r in rows:
            info = _parse_attendees(r[6])
            need_fetch = svc and (not info.get("name") or not info.get("email") or not info.get("phone") or not info.get("notes")) and r[4]
            if need_fetch:
                try:
                    ev = get_event_oauth(svc, cal_id or "primary", r[4]) if svc else None
                except Exception:
                    ev = None
                info = _merge_with_desc(info, ev)
            appts.append({
                "id": int(r[0]),
                "summary": r[1],
                "start_iso": r[2],
                "end_iso": r[3],
                "external_event_id": r[4],
                "status": r[5],
                **_flatten(info),
            })
        return {"appointments": appts}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/booking/appointment/{appointment_id}")
def booking_get(bot_id: str, appointment_id: int, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    _rate_limit(bot_id, org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id, summary, start_iso, end_iso, external_event_id, status, attendees_json from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                (appointment_id, normalize_org_id(org_id), org_id, bot_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(org_id), org_id, bot_id, "google"),
            )
            oauth_row = cur.fetchone()
        import json
        info = {}
        try:
            info = row[6] if isinstance(row[6], dict) else (json.loads(row[6]) if row[6] else {})
        except Exception:
            info = {}
        missing = not info.get("name") or not info.get("email") or not info.get("phone") or not info.get("notes")
        if missing and oauth_row:
            try:
                from app.services.calendar_google import _decrypt, build_service_from_tokens, get_event_oauth
                cal_id = oauth_row[0]
                at = _decrypt(oauth_row[1]) if oauth_row[1] else None
                rt = _decrypt(oauth_row[2]) if oauth_row[2] else None
                svc = build_service_from_tokens(at, rt, oauth_row[3])
                ev = get_event_oauth(svc, cal_id or "primary", row[4]) if svc and row[4] else None
                if ev and (ev.get("description")):
                    desc = ev.get("description") or ""
                    for ln in desc.splitlines():
                        l = ln.strip()
                        if l.lower().startswith("name:") and not info.get("name"):
                            info["name"] = l.split(":",1)[1].strip()
                        elif l.lower().startswith("email:") and not info.get("email"):
                            info["email"] = l.split(":",1)[1].strip()
                        elif l.lower().startswith("phone:") and not info.get("phone"):
                            info["phone"] = l.split(":",1)[1].strip()
                        elif l.lower().startswith("notes:") and not info.get("notes"):
                            info["notes"] = l.split(":",1)[1].strip()
            except Exception:
                pass
        return {
            "id": int(row[0]),
            "summary": row[1],
            "start_iso": row[2],
            "end_iso": row[3],
            "external_event_id": row[4],
            "status": row[5],
            "name": info.get("name"),
            "email": info.get("email"),
            "phone": info.get("phone"),
            "notes": info.get("notes") or info.get("reason") or info.get("note"),
            "info": info,
        }
    finally:
        conn.close()
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        with conn.cursor() as cur:
            cur.execute("select external_event_id from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s", (body.appointment_id, normalize_org_id(body.org_id), body.org_id, bot_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            ext_id = row[0]
            cur.execute("select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s", (normalize_org_id(body.org_id), body.org_id, bot_id, "google"))
            cr = cur.fetchone()
        from app.services.calendar_google import _decrypt, build_service_from_tokens, update_event_oauth
        at = _decrypt(cr[1]) if cr and cr[1] else None
        rt = _decrypt(cr[2]) if cr and cr[2] else None
        svc = build_service_from_tokens(at or "", rt, None)
        ok = update_event_oauth(svc, (cr[0] or "primary"), ext_id, {"start": {"dateTime": body.start_iso}, "end": {"dateTime": body.end_iso}}) if (svc and ext_id) else False
        with conn.cursor() as cur:
            cur.execute("update bot_appointments set start_iso=%s, end_iso=%s, status='scheduled', updated_at=now() where id=%s", (body.start_iso, body.end_iso, body.appointment_id))
        return {"rescheduled": True, "updated_external": bool(ok)}
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
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                "<!-- Optional keys: botName (header/button), icon (emoji/avatar), welcome/greeting (first bot message) -->"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        def bubble():
            js = (
                "<!-- Bubble widget: fixed position bubble -->"
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',mode:'bubble',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        def inline():
            js = (
                "<!-- Inline widget: embedded in page -->"
                "<div id=\"bot-inline\"></div>"
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',mode:'inline',containerId:'bot-inline',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        def iframe():
            js = (
                "<!-- Iframe widget: self-contained script -->"
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                f"<script src='{base}/api/widget.js' async></script>"
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
        "  var W=(C.welcome||C.greeting||'Hello! How can I help you?');"
        "  var N=C.botName||'Chatbot';"
        "  var I=C.icon||'';"
        "  var POS=C.position||'right';"
        "  var AUTO=C.autoOpen||false;"
        "  var MODE=C.mode||'bubble';"
        "  var CONTAINER=C.containerId||'bot-inline';"
        "  var ACC=C.buttonColor||C.accent||'#2563eb';"
        "  // Contrast auto-adjust helper (prevents light accent on light card in dark mode)\n"
        "  try{(function(){function _hexToRgb(h){h=h.replace(/#/,'');if(h.length===3){h=h.split('').map(x=>x+x).join('');}var num=parseInt(h,16);return {r:(num>>16)&255,g:(num>>8)&255,b:num&255};}function _lum(c){var r=c.r/255,g=c.g/255,b=c.b/255;[r,g,b]=[r,g,b].map(v=>{return v<=0.03928? v/12.92: Math.pow((v+0.055)/1.055,2.4);});return 0.2126*r+0.7152*g+0.0722*b;}function _isHex(x){return /^#?[0-9a-f]{3,6}$/i.test(x);}if(T==='dark'){if(_isHex(ACC)){var rgb=_hexToRgb(ACC);if(_lum(rgb)>0.7){ACC='#3b82f6';}}if(_isHex(BG)){var rgbBG=_hexToRgb(BG);if(_lum(rgbBG)>0.2){BG='#0b111a';}}if(_isHex(CARD)){var rgbCARD=_hexToRgb(CARD);var rgbBG2=_hexToRgb(BG.replace('#',''));if(Math.abs(_lum(rgbCARD)-_lum(rgbBG2))<0.04){CARD='#162131';}}}})();}catch(__){}\n"
        "  // Dark / Light palette with stronger dark contrasts\n"
        "  var BG=C.bg||((T==='dark')?'#0b111a':'#ffffff');"
        "  var CARD=C.card||((T==='dark')?'#162131':'#ffffff');"
        "  var TEXT=C.text||((T==='dark')?'#f1f5f9':'#0f1724');"
        "  var MUTED=C.muted||((T==='dark')?'#7a8694':'#64748b');"
        "  var BORDER=C.border||((T==='dark')?'rgba(255,255,255,0.12)':'rgba(16,24,40,0.06)');"
        "  var ME=C.bubbleMe||((T==='dark')?'linear-gradient(180deg,#3b82f6,#1e3a8a)':'linear-gradient(180deg,#2563eb,#1e40af)');"
        "  var BOT=C.bubbleBot||((T==='dark')?'rgba(255,255,255,0.06)':'#ffffff');"
        "  try{ if(T==='dark' && BOT===BG){ BOT='rgba(255,255,255,0.06)'; } }catch(__){}\n"
        "  var SHADOW=C.shadow||((T==='dark')?'0 24px 72px rgba(0,0,0,0.65),0 8px 24px rgba(0,0,0,0.45)':'0 10px 30px rgba(0,0,0,0.15)');"
        "  var RADIUS=(C.radius!==undefined?C.radius+'px':'12px');"
        "  var BN='CodeWeft';"
        "  var BL='https://github.com/CodeWeft-Technologies';\n"
        "  if(!O){console.warn('Chatbot: OrgId missing');return;}\n"
        "  var busy=false;\n"
        "  var SHOW_BADGE=(C.showButtonTyping===undefined)?true:!!C.showButtonTyping;\n"

        "  // --- CSS Injection ---\n"
        "  var __cw_css = `\n"
        "    :root {\n"
        "      --cb-accent: ${ACC};\n"
        "      --cb-bg: ${BG};\n"
        "      --cb-card: ${CARD};\n"
        "      --cb-text: ${TEXT};\n"
        "      --cb-muted: ${MUTED};\n"
        "      --cb-border: ${BORDER};\n"
        "      --cb-bubble-me: ${ME};\n"
        "      --cb-bubble-bot: ${BOT};\n"
        "      --cb-shadow: ${SHADOW};\n"
        "      --cb-radius: ${RADIUS};\n"
        "      --cb-mode: ${T};\n"
        "    }\n"
        "    :root[data-cb-theme='dark'] { color-scheme:dark; }\n"
        "    .cb-btn { position:fixed; bottom:24px; width:60px; height:60px; border-radius:var(--cb-radius); border:none; background:linear-gradient(135deg, var(--cb-accent), color-mix(in srgb, var(--cb-accent) 80%, black)); display:flex; align-items:center; justify-content:center; cursor:pointer; z-index:99999; box-shadow:0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08); transition:all .3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }\n"
        "    .cb-btn:hover { transform:translateY(-4px) scale(1.02); box-shadow:0 16px 48px rgba(0,0,0,0.16), 0 4px 12px rgba(0,0,0,0.12); }\n"
        "    .cb-btn:active { transform:translateY(-2px) scale(0.98); }\n"
        "    .cb-btn svg { width:32px; height:32px; display:block; fill:#fff; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.1)); }\n"
        "    .cb-emoji { font-size:32px; line-height:1; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.1)); }\n"
        "    .cb-badge { position:absolute; top:-4px; right:-4px; min-width:28px; height:20px; padding:0 8px; border-radius:999px; display:none; align-items:center; justify-content:center; background:linear-gradient(135deg, #ef4444, #dc2626); color:#fff; box-shadow:0 4px 12px rgba(239,68,68,0.4); z-index:999999; font-size:11px; font-weight:700; }\n"
        "    .cb-badge .dot { width:5px; height:5px; border-radius:50%; background:#fff; display:inline-block; margin:0 2px; opacity:.6; animation:badge-dot 1.2s ease-in-out infinite; }\n"
        "    .cb-badge .dot:nth-child(2) { animation-delay:.15s; } .cb-badge .dot:nth-child(3) { animation-delay:.3s; }\n"
        "    @keyframes badge-dot { 0%,100%{transform:translateY(0) scale(1);opacity:.6} 50%{transform:translateY(-5px) scale(1.1);opacity:1} }\n"
        "    .cb-panel { position:fixed; bottom:100px; width:400px; max-width:calc(100vw - 32px); border-radius:var(--cb-radius); overflow:hidden; display:none; flex-direction:column; z-index:99998; box-shadow:0 20px 60px rgba(0,0,0,0.2), 0 8px 24px rgba(0,0,0,0.12); background:var(--cb-bg); border:1px solid var(--cb-border); transform-origin:right bottom; opacity:0; transform:translateY(16px) scale(0.95); transition:all .3s cubic-bezier(0.4, 0, 0.2, 1); }\n"
        "    .cb-head { display:flex; align-items:center; justify-content:space-between; padding:16px 20px; border-bottom:1px solid var(--cb-border); background:linear-gradient(135deg, var(--cb-card), color-mix(in srgb, var(--cb-card) 97%, black)); backdrop-filter:blur(10px); }\n"
        "    .cb-title { font-weight:700; font-size:16px; color:var(--cb-text); display:flex; align-items:center; gap:10px; letter-spacing:-0.01em; }\n"
        "    .cb-body { height:420px; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:14px; background:var(--cb-bg); scroll-behavior:smooth; }\n"
        "    .cb-body::-webkit-scrollbar { width:6px; }\n"
        "    .cb-body::-webkit-scrollbar-track { background:transparent; }\n"
        "    .cb-body::-webkit-scrollbar-thumb { background:var(--cb-border); border-radius:999px; }\n"
        "    .cb-body::-webkit-scrollbar-thumb:hover { background:var(--cb-muted); }\n"
        "    .cb-input { display:flex; gap:12px; padding:16px 20px; border-top:1px solid var(--cb-border); background:var(--cb-card); backdrop-filter:blur(10px); }\n"
        "    .cb-input input { flex:1; padding:12px 16px; border-radius:calc(var(--cb-radius) - 4px); border:1.5px solid var(--cb-border); background:var(--cb-bg); color:var(--cb-text); outline:none; font-size:14px; transition:all .2s ease; }\n"
        "    .cb-input input:focus { border-color:var(--cb-accent); box-shadow:0 0 0 3px color-mix(in srgb, var(--cb-accent) 10%, transparent); }\n"
        "    .cb-input input::placeholder { color:var(--cb-muted); }\n"
        "    .cb-send { padding:12px 20px; border-radius:calc(var(--cb-radius) - 4px); border:none; background:linear-gradient(135deg, var(--cb-accent), color-mix(in srgb, var(--cb-accent) 85%, black)); color:#fff; font-weight:600; cursor:pointer; font-size:14px; transition:all .2s ease; box-shadow:0 2px 8px color-mix(in srgb, var(--cb-accent) 30%, transparent); }\n"
        "    .cb-send:hover { transform:translateY(-1px); box-shadow:0 4px 12px color-mix(in srgb, var(--cb-accent) 40%, transparent); }\n"
        "    .cb-send:active { transform:translateY(0); }\n"
        "    .cb-send:disabled { opacity:0.5; cursor:not-allowed; }\n"
        "    .cb-footer { padding:8px 16px; font-size:11px; color:var(--cb-muted); text-align:center; background:var(--cb-card); border-top:1px solid var(--cb-border); }\n"
        "    .cb-footer a { color:var(--cb-accent); text-decoration:none; font-weight:600; transition:opacity .2s; }\n"
        "    .cb-footer a:hover { opacity:0.8; }\n"
        "    .row { display:flex; width:100%; animation:slideUp .3s ease; }\n"
        "    @keyframes slideUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }\n"
        "    .bubble { max-width:82%; padding:12px 16px; border-radius:calc(var(--cb-radius) + 4px); line-height:1.6; font-size:14px; word-break:break-word; box-shadow:0 2px 12px rgba(0,0,0,0.06); position:relative; transition:all .2s ease; }\n"
        "    .bubble:hover { box-shadow:0 4px 16px rgba(0,0,0,0.1); }\n"
        "    .bubble.me { margin-left:auto; background:var(--cb-bubble-me); color:#fff; border-bottom-right-radius:6px; box-shadow:0 2px 12px color-mix(in srgb, var(--cb-accent) 20%, transparent); }\n"
        "    .bubble.bot { margin-right:auto; background:var(--cb-bubble-bot); color:var(--cb-text); border:1.5px solid var(--cb-border); border-bottom-left-radius:6px; }\n"
        "    .bubble pre { background:rgba(0,0,0,0.05); padding:10px 12px; border-radius:8px; overflow-x:auto; margin:8px 0; font-family:'Courier New',monospace; font-size:13px; border:1px solid var(--cb-border); }\n"
        "    .bubble code { background:rgba(0,0,0,0.06); padding:3px 6px; border-radius:6px; font-size:13px; font-family:'Courier New',monospace; }\n"
        "    .bubble.bot pre { background:rgba(0,0,0,0.03); color:var(--cb-text); }\n"
        "    .bubble a { color:inherit; text-decoration:underline; font-weight:600; }\n"
        "    .typing { display:inline-flex; align-items:flex-end; gap:5px; padding:8px 10px; }\n"
        "    .typing .dot { width:7px; height:7px; border-radius:50%; background:var(--cb-muted); animation:dot 1.4s ease-in-out infinite; }\n"
        "    .typing .dot:nth-child(2){animation-delay:.2s} .typing .dot:nth-child(3){animation-delay:.4s}\n"
        "    @keyframes dot{0%,100%{transform:translateY(0) scale(1);opacity:.5}50%{transform:translateY(-8px) scale(1.1);opacity:1}}\n"
        "  `;\n"
        "  try{var s=document.createElement('style');s.innerHTML=__cw_css;document.head.appendChild(s);}catch(_){}\n"

        "  function applyTheme(){\n"
        "    var root=document.documentElement;\n"
        "    try{\n"
        "      root.style.setProperty('--cb-accent', ACC);\n"
        "      root.style.setProperty('--cb-bg', BG);\n"
        "      root.style.setProperty('--cb-card', CARD);\n"
        "      root.style.setProperty('--cb-text', TEXT);\n"
        "      root.style.setProperty('--cb-muted', MUTED);\n"
        "      root.style.setProperty('--cb-border', BORDER);\n"
        "      root.style.setProperty('--cb-bubble-me', ME);\n"
        "      root.style.setProperty('--cb-bubble-bot', BOT);\n"
        "      root.style.setProperty('--cb-shadow', SHADOW);\n"
        "      root.style.setProperty('--cb-radius', RADIUS);\n"
        "      root.setAttribute('data-cb-theme', T);\n"
        "    }catch(__){ }\n"
        "  }\n"
        "  function refreshConfig(){\n"
        "    var C=window.chatbotConfig||{};\n"
        "    N = (C.title||C.name||C.botName||N);\n"
        "    I = (C.icon!==undefined?C.icon:I);\n"
        "    POS = (C.position||POS);\n"
        "    T = (C.theme||T);\n"
        "    ACC=(C.buttonColor||C.accent||ACC); BG=(C.bg||BG); CARD=(C.card||CARD); TEXT=(C.text||TEXT); MUTED=(C.muted||MUTED); BORDER=(C.border||BORDER); ME=(C.bubbleMe||ME); BOT=(C.bubbleBot||BOT); SHADOW=(C.shadow||SHADOW); RADIUS=(C.radius!==undefined?(C.radius+'px'):RADIUS);\n"
        "    applyTheme();\n"
        "    try{ alignPanel(); }catch(__){ }\n"
        "    try{ var t=panel.querySelector('.cb-title'); if(t){ t.textContent=N||'Chatbot'; } }catch(__){ }\n"
        "    if(footer){ footer.style.display='block'; footer.innerHTML='Powered by <a href=\"https://codeweft.in\" target=\"_blank\" style=\"color:inherit;text-decoration:none;font-weight:600;\">CodeWeft</a>'; try{ Object.defineProperty(footer, 'innerHTML', { writable: false, configurable: false }); Object.defineProperty(footer.style, 'display', { value: 'block', writable: false, configurable: false }); }catch(__){ } }\n"
        "  }\n"
        "  try{ window.Chatbot = window.Chatbot || {}; window.Chatbot.updateConfig = function(partial){ var C=window.chatbotConfig||{}; window.chatbotConfig=Object.assign({},C,partial); refreshConfig(); }; }catch(__){ }\n"
        "  applyTheme();\n"
        "  if(footer){ footer.style.display='block'; footer.innerHTML='Powered by <a href=\"https://codeweft.in\" target=\"_blank\" style=\"color:inherit;text-decoration:none;font-weight:600;\">CodeWeft</a>'; try{ Object.defineProperty(footer, 'innerHTML', { writable: false, configurable: false }); Object.defineProperty(footer.style, 'display', { value: 'block', writable: false, configurable: false }); }catch(__){ } }\n"

        "  // --- Markdown Parser ---\n"
        "  function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "  function md(s){\n"
        "     var t=esc(s);\n"
        "     t=t.replace(/```([\\s\\S]*?)```/g,function(_,c){return '<pre><code>'+c+'</code></pre>';});\n"
        "     t=t.replace(/`([^`]+)`/g,'<code>$1</code>');\n"
        "     t=t.replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>');\n"
        "     t=t.replace(/\[(.*?)\]\s*\(([\s\S]*?)\)/g,function(_,txt,url){var u=(url||'').replace(/[\"']/g,'').trim();return '<a href=\"'+u+'\" style=\"color:inherit;text-decoration:underline\">'+txt+'</a>';});\n"
        "     t=t.replace(/https?:\\/\\/[^\s<)]+/g,function(u,idx,s){var pre=s.slice(Math.max(0,idx-12),idx); if(pre.indexOf('href=')>-1) return u; var pre2=pre.replace(/\s+/g,''); if(/\]\($/.test(pre2)) return u; var uu=(u||'').replace(/[\"']/g,'');return '<a href=\"'+uu+'\" style=\"color:inherit;text-decoration:underline\">'+u+'</a>';});\n"
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
        "  if(MODE!=='inline'){ document.body.appendChild(btn); }\n"

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
        "    <div class=\"cb-footer\"></div>\n"
        "  `;\n"
        "  var mount = (MODE==='inline' ? (document.getElementById(CONTAINER)||document.body) : document.body);\n"
        "  mount.appendChild(panel);\n"

        "  var body = panel.querySelector('.cb-body');\n"
        "  var input = panel.querySelector('input');\n"
        "  var sendBtn = panel.querySelector('.cb-send');\n"
        "  var closeBtn = panel.querySelector('.cb-close');\n"
        "  var footer = panel.querySelector('.cb-footer');\n"
        "  if(footer){ footer.style.display='block'; footer.innerHTML='Powered by <a href=\"https://codeweft.in\" target=\"_blank\" style=\"color:var(--cb-accent);text-decoration:none;font-weight:600;transition:opacity .2s;\">CodeWeft</a>'; try{ Object.defineProperty(footer,'innerHTML',{writable:false,configurable:false}); Object.defineProperty(footer.style,'display',{value:'block',writable:false,configurable:false}); }catch(__){} }\n"
        "  var shownWelcome=false;\n"
        "  var opened=false;\n"
        "  function getW(){ var C=window.chatbotConfig||{}; return (C.welcome||C.greeting||''); }\n"

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
        "    var W0=getW(); if(body.childNodes.length===0 && W0){ addMsg('bot', W0); shownWelcome=true; }\n"
        "    opened=true;\n"
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
        "  function openPopup(u){ var ov=document.createElement('div'); ov.className='cb-popup'; ov.style.position='fixed'; ov.style.right='24px'; ov.style.bottom='24px'; ov.style.width='400px'; ov.style.height='560px'; ov.style.background=BG; ov.style.border='1px solid '+BORDER; ov.style.boxShadow=SHADOW; ov.style.borderRadius=RADIUS; ov.style.zIndex='2147483647'; var hd=document.createElement('div'); hd.style.padding='8px 12px'; hd.style.display='flex'; hd.style.justifyContent='space-between'; hd.style.alignItems='center'; hd.style.color=TEXT; var t=document.createElement('div'); t.textContent='Booking Form'; var x=document.createElement('button'); x.textContent='×'; x.style.background='transparent'; x.style.border='none'; x.style.color=TEXT; x.style.fontSize='18px'; x.style.cursor='pointer'; x.onclick=function(){ try{ ov.remove(); }catch(__){} }; hd.appendChild(t); hd.appendChild(x); var fr=document.createElement('iframe'); fr.src=u; fr.style.width='100%'; fr.style.height='calc(100% - 40px)'; fr.style.border='0'; ov.appendChild(hd); ov.appendChild(fr); document.body.appendChild(ov); }\n"
        "  body.addEventListener('click', function(e){ var a=e.target.closest('a'); if(!a) return; var href=a.getAttribute('href')||''; if(href.indexOf('/api/form/')>-1){ e.preventDefault(); openPopup(href); } });\n"
        "  window.addEventListener('message', function(e){ var d=e.data; if(d && (d.type==='appointment-booked'||d.type==='BOOKING_SUCCESS')){ if(d.type==='BOOKING_SUCCESS'&&d.message){ addMsg('bot', d.message); }else{ addMsg('bot', 'Booked your appointment for '+(d.start||'')+' to '+(d.end||'')+'. ID: '+d.id); } try{ var ov=document.querySelector('.cb-popup'); if(ov){ ov.remove(); } }catch(__){} } });\n"
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
        "     var m0 = txt.toLowerCase();\n"
        "     var isGreet = (m0==='hi'||m0==='hello'||m0==='hey'||m0==='hola'||m0==='hii'||m0.startsWith('hi ')||m0.startsWith('hello ')||m0.startsWith('hey '));\n"
        "     var W0=getW(); if(isGreet && W0 && !shownWelcome){ input.value=''; addMsg('me', txt); addMsg('bot', W0); shownWelcome=true; input.focus(); return; }\n"
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

        "  if(MODE!=='inline'){ btn.onclick = function(){ if(panel.style.display!=='none' && panel.style.opacity!=='0') close(); else open(); }; }\n"
        "  closeBtn.onclick = close;\n"
        "  sendBtn.onclick = doSend;\n"
        "  input.onkeydown = function(e){ if(e.key==='Enter' || e.keyCode===13){ e.preventDefault(); doSend(); } };\n"

        "  function isUuid(s){return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);}\n"
        "  function init(){\n"
        "    fetch(A+'/api/bots?org_id='+encodeURIComponent(O))\n"
        "    .then(r=>r.json()).then(d=>{\n"
        "       if(d.bots && d.bots.length > 0) {\n"
        "           var found=null;\n"
        "           if(B && isUuid(B)){ found = d.bots.find(function(x){return x.bot_id===B;}) || d.bots[0]; } else { B=d.bots[0].bot_id; found=d.bots[0]; }\n"
        "           var C=window.chatbotConfig||{};\n"
        "           if(!(C.welcome||C.greeting) && found.welcome_message){ W=found.welcome_message; window.chatbotConfig=Object.assign({},C,{welcome:found.welcome_message}); }\n"
        "           if(AUTO && !opened){ setTimeout(function(){ open(); }, 10); }\n"
        "        }\n"
        "    }).catch(e=>{});\n"
        "  }\n"
        "  init();\n"
        "  if(MODE==='inline'){ AUTO=true; }\n"
        "  if(AUTO){ setTimeout(function(){ open(); }, 100); }\n"
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
        "async function loadSnippet(bot){const d=await api('/api/bots/'+bot+'/embed?org_id='+ORG+'&widget=bubble');const el=document.getElementById('usage');el.innerHTML='';const pre=document.createElement('pre');pre.textContent=d.snippet;el.appendChild(pre);const frame=document.createElement('iframe');frame.style.width='100%';frame.style.height='540px';frame.style.border='1px solid #e5e7eb';const apiBase=location.origin;frame.srcdoc='<!doctype html><html><head><meta charset=\"utf-8\"></head><body><script>window.chatbotConfig={botId:\"'+bot+'\",orgId:\"'+ORG+'\",apiBase:\"'+apiBase+'\",mode:\"bubble\",accent:\"#2563eb\"};<\\/script><script src=\"'+apiBase+'/api/widget.js\" async><\\/script></body></html>';el.appendChild(frame);}\n"
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
