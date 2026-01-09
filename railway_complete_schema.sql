-- ============================================
-- Complete Schema Dump from Supabase
-- Generated for Railway PostgreSQL Migration
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- Table: app_users
CREATE TABLE IF NOT EXISTS app_users (
  id TEXT NOT NULL,
  email TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  org_id TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (email)
);


-- Table: booking_audit_logs
CREATE TABLE IF NOT EXISTS booking_audit_logs (
  id BIGSERIAL NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  appointment_id BIGINT,
  action TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (id)
);


-- Table: booking_notifications
CREATE TABLE IF NOT EXISTS booking_notifications (
  id BIGSERIAL NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  appointment_id BIGINT,
  type TEXT NOT NULL,
  recipient TEXT,
  payload JSONB,
  status TEXT DEFAULT 'queued',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (id)
);


-- Table: booking_resources
CREATE TABLE IF NOT EXISTS booking_resources (
  id TEXT DEFAULT gen_random_uuid() NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_name TEXT NOT NULL,
  resource_code TEXT,
  description TEXT,
  capacity_per_slot INTEGER DEFAULT 1 NOT NULL,
  metadata JSONB,
  is_active BOOLEAN DEFAULT true NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  department TEXT,
  PRIMARY KEY (id)
);


-- Table: bookings
CREATE TABLE IF NOT EXISTS bookings (
  id BIGSERIAL NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  form_config_id TEXT,
  customer_name TEXT NOT NULL,
  customer_email TEXT NOT NULL,
  customer_phone TEXT,
  booking_date DATE NOT NULL,
  start_time TIME WITHOUT TIME ZONE NOT NULL,
  end_time TIME WITHOUT TIME ZONE NOT NULL,
  resource_id TEXT,
  resource_name TEXT,
  form_data JSONB DEFAULT '{}'::jsonb NOT NULL,
  status TEXT DEFAULT 'pending' NOT NULL,
  cancellation_reason TEXT,
  calendar_event_id TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  confirmed_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  external_event_id TEXT,
  PRIMARY KEY (id)
);


-- Table: bot_appointments
CREATE TABLE IF NOT EXISTS bot_appointments (
  id BIGSERIAL NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  summary TEXT,
  start_iso TEXT,
  end_iso TEXT,
  attendees_json JSONB,
  external_event_id TEXT,
  status TEXT DEFAULT 'scheduled',
  user_contact TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (id)
);


-- Table: bot_booking_settings
CREATE TABLE IF NOT EXISTS bot_booking_settings (
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  timezone TEXT,
  available_windows JSONB,
  slot_duration_minutes INTEGER DEFAULT 30,
  capacity_per_slot INTEGER DEFAULT 1,
  min_notice_minutes INTEGER DEFAULT 60,
  max_future_days INTEGER DEFAULT 60,
  suggest_strategy TEXT DEFAULT 'next_best',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  required_user_fields JSONB,
  PRIMARY KEY (org_id, bot_id)
);


-- Table: bot_calendar_oauth
CREATE TABLE IF NOT EXISTS bot_calendar_oauth (
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  access_token_enc TEXT,
  refresh_token_enc TEXT,
  token_expiry TIMESTAMPTZ,
  calendar_id TEXT,
  watch_channel_id TEXT,
  watch_resource_id TEXT,
  watch_expiration TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  timezone TEXT,
  PRIMARY KEY (org_id, bot_id, provider)
);


-- Table: bot_calendar_settings
CREATE TABLE IF NOT EXISTS bot_calendar_settings (
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  calendar_id TEXT,
  timezone TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (org_id, bot_id, provider)
);


-- Table: bot_usage_daily
CREATE TABLE IF NOT EXISTS bot_usage_daily (
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  day DATE NOT NULL,
  chats INTEGER DEFAULT 0 NOT NULL,
  successes INTEGER DEFAULT 0 NOT NULL,
  fallbacks INTEGER DEFAULT 0 NOT NULL,
  sum_similarity DOUBLE PRECISION DEFAULT 0 NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (org_id, bot_id, day)
);


-- Table: chatbots
CREATE TABLE IF NOT EXISTS chatbots (
  id UUID DEFAULT gen_random_uuid() NOT NULL,
  org_id UUID,
  name TEXT NOT NULL,
  description TEXT,
  behavior TEXT DEFAULT 'support' NOT NULL,
  system_prompt TEXT,
  temperature REAL DEFAULT 0.2 NOT NULL,
  created_by UUID,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  public_api_key TEXT,
  website_url TEXT,
  role TEXT,
  tone TEXT,
  welcome_message TEXT,
  public_api_key_rotated_at TIMESTAMPTZ,
  services TEXT[],
  form_config JSONB,
  PRIMARY KEY (id),
  CHECK ((behavior = ANY (ARRAY['support'::text, 'sales'::text, 'appointment'::text, 'qna'::text])))
);


-- Table: conversation_history
CREATE TABLE IF NOT EXISTS conversation_history (
  id BIGSERIAL NOT NULL,
  session_id TEXT NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (id)
);


-- Table: conversations
CREATE TABLE IF NOT EXISTS conversations (
  id UUID DEFAULT gen_random_uuid() NOT NULL,
  org_id UUID,
  bot_id UUID,
  external_user_id TEXT,
  last_user_message TEXT,
  last_bot_message TEXT,
  messages JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id)
);


-- Table: form_configurations
CREATE TABLE IF NOT EXISTS form_configurations (
  id TEXT DEFAULT gen_random_uuid() NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  industry TEXT,
  is_active BOOLEAN DEFAULT true NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (bot_id)
);


-- Table: form_fields
CREATE TABLE IF NOT EXISTS form_fields (
  id TEXT DEFAULT gen_random_uuid() NOT NULL,
  form_config_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  field_label TEXT NOT NULL,
  field_type TEXT NOT NULL,
  field_order INTEGER DEFAULT 0 NOT NULL,
  is_required BOOLEAN DEFAULT false NOT NULL,
  placeholder TEXT,
  help_text TEXT,
  validation_rules JSONB,
  options JSONB,
  default_value TEXT,
  is_active BOOLEAN DEFAULT true NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  PRIMARY KEY (id)
);


-- Table: form_templates
CREATE TABLE IF NOT EXISTS form_templates (
  id TEXT DEFAULT gen_random_uuid() NOT NULL,
  name TEXT NOT NULL,
  industry TEXT NOT NULL,
  description TEXT,
  template_data JSONB NOT NULL,
  is_public BOOLEAN DEFAULT true NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id)
);


-- Table: leads
CREATE TABLE IF NOT EXISTS leads (
  id BIGSERIAL NOT NULL,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  name TEXT,
  email TEXT,
  phone TEXT,
  interest_details TEXT,
  comments TEXT,
  conversation_summary TEXT,
  interest_score INTEGER DEFAULT 0,
  status TEXT DEFAULT 'new',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  session_id TEXT,
  PRIMARY KEY (id)
);


-- Table: organization_users
CREATE TABLE IF NOT EXISTS organization_users (
  org_id UUID NOT NULL,
  user_id UUID NOT NULL,
  role TEXT DEFAULT 'member' NOT NULL,
  PRIMARY KEY (org_id, user_id),
  CHECK ((role = ANY (ARRAY['owner'::text, 'admin'::text, 'member'::text])))
);


-- Table: organizations
CREATE TABLE IF NOT EXISTS organizations (
  id UUID DEFAULT gen_random_uuid() NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id)
);


-- Table: rag_embeddings
CREATE TABLE IF NOT EXISTS rag_embeddings (
  id BIGSERIAL NOT NULL,
  org_id UUID,
  bot_id UUID,
  doc_id UUID,
  chunk_id INTEGER,
  content TEXT NOT NULL,
  embedding EXTENSIONS.VECTOR(1024) NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id)
);


-- Table: resource_schedules
CREATE TABLE IF NOT EXISTS resource_schedules (
  id TEXT DEFAULT gen_random_uuid() NOT NULL,
  resource_id TEXT NOT NULL,
  day_of_week INTEGER,
  specific_date DATE,
  start_time TIME WITHOUT TIME ZONE NOT NULL,
  end_time TIME WITHOUT TIME ZONE NOT NULL,
  slot_duration_minutes INTEGER DEFAULT 30 NOT NULL,
  is_available BOOLEAN DEFAULT true NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id)
);


-- Table: users
CREATE TABLE IF NOT EXISTS users (
  id UUID NOT NULL,
  email TEXT,
  display_name TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (email)
);


-- ============================================
-- Indexes
-- ============================================

CREATE UNIQUE INDEX IF NOT EXISTS app_users_email_key ON public.app_users USING btree (email);
CREATE INDEX IF NOT EXISTS idx_booking_resources_bot ON public.booking_resources USING btree (bot_id);
CREATE INDEX IF NOT EXISTS idx_bookings_bot ON public.bookings USING btree (bot_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON public.bookings USING btree (booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_resource ON public.bookings USING btree (resource_id);
CREATE INDEX IF NOT EXISTS idx_conversation_session ON public.conversation_history USING btree (session_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS form_configurations_bot_id_key ON public.form_configurations USING btree (bot_id);
CREATE INDEX IF NOT EXISTS idx_form_configs_bot ON public.form_configurations USING btree (bot_id);
CREATE INDEX IF NOT EXISTS idx_form_fields_config ON public.form_fields USING btree (form_config_id);
CREATE INDEX IF NOT EXISTS rag_embeddings_bot_idx ON public.rag_embeddings USING btree (bot_id);
CREATE INDEX IF NOT EXISTS rag_embeddings_ivf_idx ON public.rag_embeddings USING ivfflat (embedding extensions.vector_cosine_ops) WITH (lists='100');
CREATE INDEX IF NOT EXISTS rag_embeddings_org_bot_idx ON public.rag_embeddings USING btree (org_id, bot_id);
CREATE INDEX IF NOT EXISTS idx_resource_schedules_resource ON public.resource_schedules USING btree (resource_id);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_key ON public.users USING btree (email);

-- ============================================
-- Functions
-- ============================================


-- Function: check_resource_capacity
CREATE OR REPLACE FUNCTION public.check_resource_capacity(p_resource_id text, p_booking_date date, p_start_time time without time zone, p_end_time time without time zone)
 RETURNS boolean
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
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
                        $function$
;

-- Function: check_slot_capacity
CREATE OR REPLACE FUNCTION public.check_slot_capacity(p_bot_id text, p_booking_date date, p_start_time time without time zone, p_end_time time without time zone)
 RETURNS boolean
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
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
                        $function$
;

-- Function: get_available_slots
CREATE OR REPLACE FUNCTION public.get_available_slots(p_resource_id text, p_date date)
 RETURNS TABLE(slot_start time without time zone, slot_end time without time zone, available_capacity integer)
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
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
                        $function$
;

-- Function: uuid_generate_v1
CREATE OR REPLACE FUNCTION public.uuid_generate_v1()
 RETURNS uuid
 LANGUAGE c
 PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_generate_v1$function$
;

-- Function: uuid_generate_v1mc
CREATE OR REPLACE FUNCTION public.uuid_generate_v1mc()
 RETURNS uuid
 LANGUAGE c
 PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_generate_v1mc$function$
;

-- Function: uuid_generate_v3
CREATE OR REPLACE FUNCTION public.uuid_generate_v3(namespace uuid, name text)
 RETURNS uuid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_generate_v3$function$
;

-- Function: uuid_generate_v4
CREATE OR REPLACE FUNCTION public.uuid_generate_v4()
 RETURNS uuid
 LANGUAGE c
 PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_generate_v4$function$
;

-- Function: uuid_generate_v5
CREATE OR REPLACE FUNCTION public.uuid_generate_v5(namespace uuid, name text)
 RETURNS uuid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_generate_v5$function$
;

-- Function: uuid_nil
CREATE OR REPLACE FUNCTION public.uuid_nil()
 RETURNS uuid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_nil$function$
;

-- Function: uuid_ns_dns
CREATE OR REPLACE FUNCTION public.uuid_ns_dns()
 RETURNS uuid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_ns_dns$function$
;

-- Function: uuid_ns_oid
CREATE OR REPLACE FUNCTION public.uuid_ns_oid()
 RETURNS uuid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_ns_oid$function$
;

-- Function: uuid_ns_url
CREATE OR REPLACE FUNCTION public.uuid_ns_url()
 RETURNS uuid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_ns_url$function$
;

-- Function: uuid_ns_x500
CREATE OR REPLACE FUNCTION public.uuid_ns_x500()
 RETURNS uuid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/uuid-ossp', $function$uuid_ns_x500$function$
;