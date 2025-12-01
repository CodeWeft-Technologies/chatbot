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
    except Exception:
        pass

@app.on_event("startup")
def on_startup():
    _init_schema()
