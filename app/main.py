import sys
import asyncio
from fastapi import FastAPI
import logging

# Reduce logging verbosity to reduce I/O load
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

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


def ensure_auth_schema(conn):
    """Create a minimal auth schema/uid shim for non-Supabase Postgres so RLS policies compile."""
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
            cur.execute(
                """
                CREATE OR REPLACE FUNCTION auth.uid()
                RETURNS uuid
                LANGUAGE sql
                STABLE
                AS $$ SELECT null::uuid $$;
                """
            )
    except Exception:
        pass
from app.routes.chat import router as chat_router
from app.routes.ingest import router as ingest_router
from app.routes.dynamic_forms import router as forms_router

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
app.include_router(forms_router, prefix="/api")


# Health check endpoint for Railway keep-alive
@app.get("/health")
def health_check():
    """Health check endpoint for Railway to keep container warm"""
    return {"status": "ok", "service": "chatbot-api"}


@app.on_event("startup")
async def startup_event():
    """Initialize server: install Playwright, create indexes, setup schema"""
    logger.info("[STARTUP] Starting up chatbot service...")
    
    # Create ingest_jobs table for background processing
    try:
        _create_ingest_jobs_schema()
    except Exception as e:
        logger.warning(f"[STARTUP] Ingest jobs schema creation failed: {e}")
    
    # Update vector dimensions if needed (OpenAI embeddings use 1536)
    try:
        _update_vector_dimensions()
    except Exception as e:
        logger.warning(f"[STARTUP] Vector dimension update failed: {e}")
    
    # Install Playwright browsers at startup (before any requests arrive)
    try:
        _install_playwright_browsers()
    except Exception as e:
        logger.warning(f"[STARTUP] Playwright installation failed (will fall back to requests): {e}")
    
    # Create vector search indexes for performance
    try:
        _init_vector_indexes()
    except Exception as e:
        logger.warning(f"[STARTUP] Failed to create vector indexes: {e}")
    
    logger.info("[STARTUP] Startup complete")


def _create_ingest_jobs_schema():
    """Create ingest_jobs table for background file processing queue"""
    logger.info("[STARTUP] Ensuring ingest_jobs table exists...")
    try:
        with psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ingest_jobs (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        org_id UUID NOT NULL,
                        bot_id UUID NOT NULL,
                        filename TEXT NOT NULL,
                        file_size BIGINT NOT NULL,
                        file_content BYTEA,
                        status TEXT NOT NULL DEFAULT 'pending',
                        progress INT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        error_message TEXT,
                        documents_count INT DEFAULT 0,
                        created_by UUID NOT NULL
                    );
                """)
                
                # Create indexes for efficient querying
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status 
                    ON ingest_jobs(status);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ingest_jobs_org_bot 
                    ON ingest_jobs(org_id, bot_id);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ingest_jobs_created_at 
                    ON ingest_jobs(created_at DESC);
                """)
                
                # Add file_content column if it doesn't exist (for existing databases)
                cur.execute("""
                    ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS file_content BYTEA;
                """)
                
                logger.info("[STARTUP] ✅ ingest_jobs table ready")
    except Exception as e:
        logger.error(f"[STARTUP] Failed to create ingest_jobs table: {e}")
        raise


def _update_vector_dimensions():
    """Update rag_embeddings table to use 1536 dimensions for OpenAI embeddings"""
    logger.info("[STARTUP] Checking vector dimensions...")
    try:
        with psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Check current vector dimensions
                cur.execute("""
                    SELECT 
                        pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type
                    FROM pg_catalog.pg_attribute a
                    WHERE a.attrelid = 'rag_embeddings'::regclass
                    AND a.attname = 'embedding'
                    AND a.attnum > 0 
                    AND NOT a.attisdropped;
                """)
                result = cur.fetchone()
                
                if result and 'vector(1024)' in result[0]:
                    logger.info("[STARTUP] Updating vector dimensions from 1024 to 1536...")
                    
                    # Drop and recreate table with new dimensions
                    cur.execute("DROP TABLE IF EXISTS rag_embeddings CASCADE;")
                    cur.execute("""
                        CREATE TABLE rag_embeddings (
                            id SERIAL PRIMARY KEY,
                            org_id TEXT NOT NULL,
                            bot_id TEXT NOT NULL,
                            content TEXT NOT NULL,
                            embedding EXTENSIONS.vector(1536) NOT NULL,
                            metadata JSONB DEFAULT '{}',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    
                    # Create indexes
                    cur.execute("""
                        CREATE INDEX rag_embeddings_vector_idx 
                        ON rag_embeddings USING ivfflat (embedding)
                        WITH (lists = 100);
                    """)
                    cur.execute("CREATE INDEX rag_embeddings_org_bot_idx ON rag_embeddings(org_id, bot_id);")
                    
                    logger.info("[STARTUP] ✅ Vector dimensions updated to 1536")
                elif result and 'vector(1536)' in result[0]:
                    logger.info("[STARTUP] ✅ Vector dimensions already correct (1536)")
                else:
                    logger.info(f"[STARTUP] Vector column info: {result}")
    except Exception as e:
        logger.error(f"[STARTUP] Failed to update vector dimensions: {e}")
        raise


def _install_playwright_browsers():
    """Install Playwright Chromium at server startup."""
    import subprocess
    logger.info("[STARTUP] Installing Playwright Chromium browsers...")
    try:
        # Dependencies are already in the image; avoid --with-deps to prevent apt failures
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            timeout=300,  # 5 minute timeout
            check=False  # Don't raise on non-zero exit
        )
        if result.returncode == 0:
            logger.info("[STARTUP] Playwright Chromium installed successfully")
        else:
            logger.warning(f"[STARTUP] Playwright install returned code {result.returncode}")
            if result.stderr:
                logger.warning(f"[STARTUP] Stderr: {result.stderr.decode('utf-8', errors='ignore')[:200]}")
    except subprocess.TimeoutExpired:
        logger.warning("[STARTUP] Playwright installation timed out after 5 minutes")
    except Exception as e:
        logger.warning(f"[STARTUP] Failed to install Playwright: {e}")


def _init_vector_indexes():
    """Create efficient indexes on rag_embeddings for faster queries"""
    try:
        with psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Note: Cannot index large vector columns directly
                # pgvector similarity search is fast enough without indexes
                # Vector search uses sequential scan which is optimized for similarity operations
                
                # Create composite index on org_id + bot_id for faster lookups
                try:
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_rag_embeddings_org_bot 
                        ON rag_embeddings (org_id, bot_id)
                    """)
                except Exception:
                    pass
                
                # Analyze for query optimization
                try:
                    cur.execute("ANALYZE rag_embeddings")
                except Exception:
                    pass
    except Exception:
        pass  # Index creation is optional


def _init_schema():
    try:
        with psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True) as conn:
            ensure_auth_schema(conn)
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
                      timezone text,
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
                cur.execute(
                    """
                    create table if not exists leads (
                      id bigserial primary key,
                      org_id text not null,
                      bot_id text not null,
                      name text,
                      email text,
                      phone text,
                      interest_details text,
                      comments text,
                      conversation_summary text,
                      interest_score int default 0,
                      status text default 'new',
                      created_at timestamptz default now(),
                      updated_at timestamptz default now()
                    )
                    """
                )
                try:
                    cur.execute("alter table leads enable row level security;")
                except Exception:
                    pass
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
                
                # Create RLS Policies (wrapped in DO blocks to avoid "already exists" errors)
                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see their own data" ON app_users
                            FOR SELECT USING (auth.uid()::text = id);
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org booking resources" ON booking_resources
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = booking_resources.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org bookings" ON bookings
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = bookings.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org appointments" ON bot_appointments
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = bot_appointments.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org leads" ON leads
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = leads.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org bot booking settings" ON bot_booking_settings
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = bot_booking_settings.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org bot calendar oauth" ON bot_calendar_oauth
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = bot_calendar_oauth.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org bot calendar settings" ON bot_calendar_settings
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = bot_calendar_settings.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org bot usage daily" ON bot_usage_daily
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = bot_usage_daily.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org form configurations" ON form_configurations
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM app_users
                                    WHERE app_users.id = auth.uid()::text
                                    AND app_users.org_id = form_configurations.org_id
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org form fields" ON form_fields
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM form_configurations fc
                                    WHERE fc.id = form_fields.form_config_id
                                    AND EXISTS (
                                        SELECT 1 FROM app_users
                                        WHERE app_users.id = auth.uid()::text
                                        AND app_users.org_id = fc.org_id
                                    )
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see public form templates" ON form_templates
                            FOR SELECT USING (is_public = true);
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Users can see org resource schedules" ON resource_schedules
                            FOR ALL USING (
                                EXISTS (
                                    SELECT 1 FROM booking_resources br
                                    WHERE br.id = resource_schedules.resource_id
                                    AND EXISTS (
                                        SELECT 1 FROM app_users
                                        WHERE app_users.id = auth.uid()::text
                                        AND app_users.org_id = br.org_id
                                    )
                                )
                            );
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
                except Exception:
                    pass

                # Dev bypass: allow deletes/updates when no auth context (e.g., local testing without JWT)
                try:
                    cur.execute("""
                        DO $$ BEGIN
                            CREATE POLICY "Dev allow resource schedules without auth" ON resource_schedules
                            FOR ALL USING (auth.uid() IS NULL);
                        EXCEPTION WHEN duplicate_object THEN NULL;
                        END $$;
                    """)
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
                
                # Dynamic Forms Tables
                # Form configurations
                cur.execute(
                    """
                    create table if not exists form_configurations (
                      id text primary key default gen_random_uuid()::text,
                      org_id text not null,
                      bot_id text not null,
                      name text not null,
                      description text,
                      industry text,
                      is_active boolean not null default true,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now(),
                      unique(bot_id)
                    )
                    """
                )
                
                # Form fields
                cur.execute(
                    """
                    create table if not exists form_fields (
                      id text primary key default gen_random_uuid()::text,
                      form_config_id text not null,
                      field_name text not null,
                      field_label text not null,
                      field_type text not null,
                      field_order int not null default 0,
                      is_required boolean not null default false,
                      placeholder text,
                      help_text text,
                      validation_rules jsonb,
                      options jsonb,
                      default_value text,
                      is_active boolean not null default true,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now()
                    )
                    """
                )
                
                # Booking resources (doctors, rooms, staff, etc.)
                cur.execute(
                    """
                    create table if not exists booking_resources (
                      id text primary key default gen_random_uuid()::text,
                      org_id text not null,
                      bot_id text not null,
                      resource_type text not null,
                      resource_name text not null,
                      resource_code text,
                      department text,
                      description text,
                      capacity_per_slot int not null default 1,
                      metadata jsonb,
                      is_active boolean not null default true,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now()
                    )
                    """
                )
                try:
                    cur.execute("alter table booking_resources add column if not exists department text")
                except Exception:
                    pass
                
                # Resource schedules
                cur.execute(
                    """
                    create table if not exists resource_schedules (
                      id text primary key default gen_random_uuid()::text,
                      resource_id text not null,
                      day_of_week int,
                      specific_date date,
                      start_time time not null,
                      end_time time not null,
                      slot_duration_minutes int not null default 30,
                      is_available boolean not null default true,
                      metadata jsonb,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now()
                    )
                    """
                )
                
                # Enhanced bookings with dynamic form data
                cur.execute(
                    """
                    create table if not exists bookings (
                      id bigserial primary key,
                      org_id text not null,
                      bot_id text not null,
                      form_config_id text,
                      customer_name text not null,
                      customer_email text not null,
                      customer_phone text,
                      booking_date date not null,
                      start_time time not null,
                      end_time time not null,
                      resource_id text,
                      resource_name text,
                      form_data jsonb not null default '{}'::jsonb,
                      status text not null default 'pending',
                      cancellation_reason text,
                      calendar_event_id text,
                      external_event_id text,
                      notes text,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now(),
                      confirmed_at timestamptz,
                      cancelled_at timestamptz
                    )
                    """
                )
                
                # Add external_event_id column if it doesn't exist (migration)
                try:
                    cur.execute("""
                        ALTER TABLE bookings 
                        ADD COLUMN IF NOT EXISTS external_event_id text
                    """)
                    pass
                except Exception as e:
                    pass
                
                # Form templates
                cur.execute(
                    """
                    create table if not exists form_templates (
                      id text primary key default gen_random_uuid()::text,
                      name text not null,
                      industry text not null,
                      description text,
                      template_data jsonb not null,
                      is_public boolean not null default true,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now()
                    )
                    """
                )
                
                # Create indexes for dynamic forms
                try:
                    cur.execute("create index if not exists idx_form_configs_bot on form_configurations(bot_id)")
                    cur.execute("create index if not exists idx_form_fields_config on form_fields(form_config_id)")
                    cur.execute("create index if not exists idx_booking_resources_bot on booking_resources(bot_id)")
                    cur.execute("create index if not exists idx_resource_schedules_resource on resource_schedules(resource_id)")
                    cur.execute("create index if not exists idx_bookings_bot on bookings(bot_id)")
                    cur.execute("create index if not exists idx_bookings_date on bookings(booking_date)")
                    cur.execute("create index if not exists idx_bookings_resource on bookings(resource_id)")
                except Exception:
                    pass
                
                # Create helper function for resource capacity checking
                try:
                    cur.execute("""
                        create or replace function check_resource_capacity(
                            p_resource_id text,
                            p_booking_date date,
                            p_start_time time,
                            p_end_time time
                        ) returns boolean
                        language plpgsql
                        set search_path = ''
                        as $$
                        declare
                            v_capacity int;
                            v_booked_count int;
                        begin
                            -- Get resource capacity
                            select capacity_per_slot into v_capacity
                            from public.booking_resources
                            where id = p_resource_id and is_active = true;
                            
                            if v_capacity is null then
                                return false;
                            end if;
                            
                            -- Count existing bookings for this slot
                            select count(*) into v_booked_count
                            from public.bookings
                            where resource_id = p_resource_id
                              and booking_date = p_booking_date
                              and status not in ('cancelled', 'rejected')
                              and (
                                (start_time <= p_start_time and end_time > p_start_time) or
                                (start_time < p_end_time and end_time >= p_end_time) or
                                (start_time >= p_start_time and end_time <= p_end_time)
                              );
                            
                            -- Return true if there's capacity available
                            return v_booked_count < v_capacity;
                        end;
                        $$;
                    """)
                    pass
                except Exception as e:
                    pass
                
                # Create helper function for slot capacity checking (bot-level)
                try:
                    cur.execute("""
                        create or replace function check_slot_capacity(
                            p_bot_id text,
                            p_booking_date date,
                            p_start_time time,
                            p_end_time time
                        ) returns boolean
                        language plpgsql
                        set search_path = ''
                        as $$
                        declare
                            v_capacity int;
                            v_booked_count int;
                        begin
                            -- Get bot's capacity per slot setting
                            select capacity_per_slot into v_capacity
                            from public.bot_booking_settings
                            where bot_id = p_bot_id;
                            
                            if v_capacity is null then
                                v_capacity := 1; -- Default capacity
                            end if;
                            
                            -- Count existing bookings for this slot
                            select count(*) into v_booked_count
                            from public.bookings
                            where bot_id = p_bot_id
                              and booking_date = p_booking_date
                              and start_time = p_start_time
                              and end_time = p_end_time
                              and status not in ('cancelled', 'rejected');
                            
                            -- Return true if there's capacity available
                            return v_booked_count < v_capacity;
                        end;
                        $$;
                    """)
                    pass
                except Exception as e:
                    pass
                
                # Create helper function for getting available slots
                try:
                    cur.execute("""
                        -- Note: Time constraints (min_notice, max_future) are now applied in Python layer
                        -- This function returns all available slots based on schedule and capacity only
                        create or replace function get_available_slots(
                            p_resource_id text,
                            p_date date
                        ) returns table(slot_start time, slot_end time, available_capacity int)
                        language plpgsql
                        set search_path = ''
                        as $$
                        declare
                            v_schedule record;
                            v_capacity int;
                            v_booked int;
                            v_current_time time;
                            v_slot_duration int;
                        begin
                            -- Get resource capacity
                            select capacity_per_slot into v_capacity
                            from public.booking_resources
                            where id = p_resource_id and is_active = true;
                            
                            if v_capacity is null then
                                return;
                            end if;
                            
                            -- Get schedule for the day
                            for v_schedule in
                                select start_time, end_time, slot_duration_minutes
                                from public.resource_schedules
                                where resource_id = p_resource_id
                                  and is_available = true
                                  and (
                                    (specific_date = p_date) or
                                    (specific_date is null and day_of_week = extract(dow from p_date))
                                  )
                            loop
                                v_current_time := v_schedule.start_time;
                                v_slot_duration := coalesce(v_schedule.slot_duration_minutes, 30);
                                
                                while v_current_time + (v_slot_duration || ' minutes')::interval <= v_schedule.end_time loop
                                    -- Count overlapping bookings for this slot window
                                    select count(*) into v_booked
                                    from public.bookings
                                    where resource_id = p_resource_id
                                      and booking_date = p_date
                                      and status not in ('cancelled', 'rejected')
                                      and (
                                        (start_time <= v_current_time and end_time > v_current_time) or
                                        (start_time < (v_current_time + (v_slot_duration || ' minutes')::interval) and end_time >= (v_current_time + (v_slot_duration || ' minutes')::interval)) or
                                        (start_time >= v_current_time and end_time <= (v_current_time + (v_slot_duration || ' minutes')::interval))
                                      );
                                    
                                    slot_start := v_current_time;
                                    slot_end := v_current_time + (v_slot_duration || ' minutes')::interval;
                                    available_capacity := v_capacity - coalesce(v_booked, 0);
                                    
                                    if available_capacity > 0 then
                                        return next;
                                    end if;
                                    
                                    v_current_time := v_current_time + (v_slot_duration || ' minutes')::interval;
                                end loop;
                            end loop;
                        end;
                        $$;
                    """)
                    pass
                except Exception as e:
                    pass
                
                # Enable RLS on dynamic forms tables
                try:
                    cur.execute("alter table form_configurations enable row level security;")
                    cur.execute("alter table form_configurations force row level security;")
                    cur.execute("alter table form_fields enable row level security;")
                    cur.execute("alter table form_fields force row level security;")
                    cur.execute("alter table booking_resources enable row level security;")
                    cur.execute("alter table booking_resources force row level security;")
                    cur.execute("alter table resource_schedules enable row level security;")
                    cur.execute("alter table resource_schedules force row level security;")
                    cur.execute("alter table bookings enable row level security;")
                    cur.execute("alter table bookings force row level security;")
                    cur.execute("alter table form_templates enable row level security;")
                    cur.execute("alter table form_templates force row level security;")
                except Exception:
                    pass
                
                # Insert default templates
                try:
                    cur.execute("""
                        insert into form_templates (id, name, industry, description, template_data)
                        values 
                        ('healthcare-template', 'Healthcare - Doctor Appointment', 'healthcare', 
                         'Standard medical appointment booking form', 
                         '{"fields": [{"field_name": "appointment_type", "field_label": "Appointment Type", "field_type": "select", "field_order": 1, "is_required": true, "options": [{"value": "consultation", "label": "General Consultation"}, {"value": "followup", "label": "Follow-up Visit"}, {"value": "emergency", "label": "Emergency"}]}, {"field_name": "department", "field_label": "Department", "field_type": "select", "field_order": 2, "is_required": true, "options": [{"value": "cardiology", "label": "Cardiology"}, {"value": "neurology", "label": "Neurology"}, {"value": "pediatrics", "label": "Pediatrics"}, {"value": "general", "label": "General Medicine"}]}, {"field_name": "symptoms", "field_label": "Symptoms", "field_type": "textarea", "field_order": 3, "is_required": false, "placeholder": "Describe your symptoms"}]}'::jsonb)
                        on conflict (id) do nothing
                    """)
                    
                    cur.execute("""
                        insert into form_templates (id, name, industry, description, template_data)
                        values 
                        ('salon-template', 'Salon - Beauty Appointment', 'salon', 
                         'Beauty salon and spa booking form',
                         '{"fields": [{"field_name": "service", "field_label": "Service Type", "field_type": "select", "field_order": 1, "is_required": true, "options": [{"value": "haircut", "label": "Haircut"}, {"value": "coloring", "label": "Hair Coloring"}, {"value": "manicure", "label": "Manicure"}, {"value": "pedicure", "label": "Pedicure"}]}, {"field_name": "duration", "field_label": "Estimated Duration", "field_type": "select", "field_order": 2, "is_required": true, "options": [{"value": "30", "label": "30 minutes"}, {"value": "60", "label": "1 hour"}, {"value": "90", "label": "1.5 hours"}]}]}'::jsonb)
                        on conflict (id) do nothing
                    """)
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
    
    # Start background worker for ingestion jobs
    import threading
    def run_background_worker():
        """Run the background worker in a separate thread"""
        logger.info("[STARTUP] Starting background worker thread...")
        try:
            from app.services.background_worker import start_background_worker
            asyncio.run(start_background_worker())
        except Exception as e:
            logger.error(f"[STARTUP] Background worker failed: {e}")
    
    worker_thread = threading.Thread(target=run_background_worker, daemon=True)
    worker_thread.start()
    logger.info("[STARTUP] Background worker thread started")
    
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
    
    # Schedule periodic completion of past bookings
    def complete_past_bookings():
        import time
        from datetime import datetime, date
        try:
            from zoneinfo import ZoneInfo
        except Exception:
            ZoneInfo = None
        while True:
            try:
                time.sleep(900)  # Run every 15 minutes
                conn = psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True)
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            select id, bot_id, booking_date, end_time, status
                            from bookings
                            where status not in ('completed','cancelled','rejected')
                              and booking_date <= current_date
                            order by booking_date desc
                            limit 500
                        """)
                        rows = cur.fetchall() or []
                    for r in rows:
                        bid = r[0]; bot_id = r[1]; bdate = r[2]; etime = r[3]; st = (r[4] or '').lower()
                        try:
                            tz = None
                            with conn.cursor() as cur2:
                                cur2.execute("select timezone from bot_booking_settings where bot_id=%s", (bot_id,))
                                s = cur2.fetchone()
                                tz = s[0] if s and s[0] else None
                            now = datetime.now(ZoneInfo(tz)) if (tz and ZoneInfo) else datetime.now()
                            end_dt = datetime.combine(bdate, etime)
                            # Treat stored date/time as local to bot timezone if available
                            if tz and ZoneInfo:
                                end_dt = end_dt.replace(tzinfo=ZoneInfo(tz))
                            if end_dt <= now:
                                with conn.cursor() as cur3:
                                    cur3.execute("update bookings set status='completed', updated_at=now() where id=%s", (bid,))
                        except Exception:
                            pass
                finally:
                    conn.close()
            except Exception:
                pass
    thread2 = threading.Thread(target=complete_past_bookings, daemon=True)
    thread2.start()
