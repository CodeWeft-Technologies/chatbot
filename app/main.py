import sys
import asyncio
from fastapi import FastAPI

# On Windows, ensure the ProactorEventLoop is used so asyncio.create_subprocess_exec
# (required by Playwright) is available. Do this early, before any asyncio usage.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        # If setting the policy fails, continue — code will fallback to requests
        pass
import psycopg
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes.chat import router as chat_router
from app.routes.ingest import router as ingest_router

app = FastAPI(title="Multi-tenant AI Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")

def _init_schema():
    try:
        with psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("create extension if not exists vector;")
                try:
                    cur.execute("create schema if not exists extensions;")
                    cur.execute("alter extension vector set schema extensions;")
                except Exception:
                    pass
                try:
                    cur.execute("set search_path to public, extensions;")
                except Exception:
                    pass
                cur.execute(
                    """
                    create table if not exists chatbots (
                      org_id text not null,
                      id text not null,
                      behavior text not null,
                      system_prompt text,
                      name text,
                      website_url text,
                      role text,
                      tone text,
                      welcome_message text,
                      public_api_key text,
                      public_api_key_rotated_at timestamptz,
                      created_at timestamptz default now(),
                      updated_at timestamptz default now(),
                      primary key (org_id, id)
                    )
                    """
                )
                try:
                    cur.execute("alter table chatbots drop constraint if exists chatbots_behavior_check")
                except Exception:
                    pass
                try:
                    cur.execute("alter table chatbots add constraint chatbots_behavior_check check (behavior in ('support','sales','appointment','qna'))")
                except Exception:
                    pass
                cur.execute(
                    """
                    create table if not exists rag_embeddings (
                      org_id text not null,
                      bot_id text not null,
                      doc_id text,
                      chunk_id int,
                      content text not null,
                      embedding vector not null,
                      metadata jsonb,
                      created_at timestamptz default now()
                    )
                    """
                )
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
                      created_at timestamptz default now(),
                      updated_at timestamptz default now(),
                      primary key (org_id, bot_id)
                    )
                    """
                )
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
                      external_event_id text,
                      status text default 'scheduled',
                      user_contact text,
                      created_at timestamptz default now(),
                      updated_at timestamptz default now()
                    )
                    """
                )
                try:
                    cur.execute("alter table bot_usage_daily enable row level security;")
                    cur.execute("alter table bot_usage_daily force row level security;")
                except Exception:
                    pass
                try:
                    cur.execute("alter table app_users enable row level security;")
                    cur.execute("alter table app_users force row level security;")
                except Exception:
                    pass
                try:
                    cur.execute("alter table bot_calendar_settings enable row level security;")
                    cur.execute("alter table bot_calendar_settings force row level security;")
                except Exception:
                    pass
                try:
                    cur.execute("alter table bot_calendar_oauth enable row level security;")
                    cur.execute("alter table bot_calendar_oauth force row level security;")
                except Exception:
                    pass
                try:
                    cur.execute("alter table bot_booking_settings enable row level security;")
                    cur.execute("alter table bot_booking_settings force row level security;")
                except Exception:
                    pass
                try:
                    cur.execute("alter table bot_appointments enable row level security;")
                    cur.execute("alter table bot_appointments force row level security;")
                except Exception:
                    pass
                
                # Create conversation history table for session-based context
                cur.execute(
                    """
                    create table if not exists conversation_history (
                      id bigserial primary key,
                      session_id text not null,
                      org_id text not null,
                      bot_id text not null,
                      role text not null,
                      content text not null,
                      created_at timestamptz default now()
                    )
                    """
                )
                
                # Create index for fast session lookups
                try:
                    cur.execute(
                        "create index if not exists idx_conversation_session on conversation_history(session_id, created_at)"
                    )
                except Exception:
                    pass
                
                # Enable RLS on conversation_history
                try:
                    cur.execute("alter table conversation_history enable row level security;")
                    cur.execute("alter table conversation_history force row level security;")
                except Exception:
                    pass
                
                # Allow service role full access to conversation history
                try:
                    cur.execute("drop policy if exists service_role_all_conversation on conversation_history;")
                    cur.execute("""
                        create policy service_role_all_conversation on conversation_history
                        for all using (true);
                    """)
                except Exception:
                    pass
                
                # Create booking audit logs table
                cur.execute(
                    """
                    create table if not exists booking_audit_logs (
                      id bigserial primary key,
                      org_id text not null,
                      bot_id text not null,
                      appointment_id bigint,
                      action text not null,
                      details jsonb,
                      created_at timestamptz default now()
                    )
                    """
                )
                
                # Create booking notifications table
                cur.execute(
                    """
                    create table if not exists booking_notifications (
                      id bigserial primary key,
                      org_id text not null,
                      bot_id text not null,
                      appointment_id bigint,
                      notification_type text not null,
                      recipient_email text not null,
                      payload jsonb,
                      sent_at timestamptz,
                      status text default 'pending',
                      created_at timestamptz default now()
                    )
                    """
                )
                
                # Enable RLS on booking_audit_logs
                try:
                    cur.execute("alter table booking_audit_logs enable row level security;")
                    cur.execute("alter table booking_audit_logs force row level security;")
                except Exception:
                    pass
                
                # Enable RLS on booking_notifications
                try:
                    cur.execute("alter table booking_notifications enable row level security;")
                    cur.execute("alter table booking_notifications force row level security;")
                except Exception:
                    pass
                
                # Create RLS policies for booking_audit_logs (allow service role access)
                try:
                    cur.execute("drop policy if exists service_role_all_booking_audit on booking_audit_logs;")
                    cur.execute("""
                        create policy service_role_all_booking_audit on booking_audit_logs
                        for all using (true);
                    """)
                except Exception:
                    pass
                
                # Create RLS policies for booking_notifications (allow service role access)
                try:
                    cur.execute("drop policy if exists service_role_all_booking_notif on booking_notifications;")
                    cur.execute("""
                        create policy service_role_all_booking_notif on booking_notifications
                        for all using (true);
                    """)
                except Exception:
                    pass
    except Exception:
        pass

@app.on_event("startup")
def on_startup():
    _init_schema()
    # Schedule periodic cleanup of old conversations
    import threading
    def cleanup_conversations():
        import time
        while True:
            try:
                time.sleep(3600)  # Run every hour
                conn = psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True)
                try:
                    with conn.cursor() as cur:
                        cur.execute("delete from conversation_history where created_at < now() - interval '24 hours'")
                finally:
                    conn.close()
            except Exception:
                pass
    
    thread = threading.Thread(target=cleanup_conversations, daemon=True)
    thread.start()
