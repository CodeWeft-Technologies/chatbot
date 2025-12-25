
-- Safety cleanup for Supabase restores
DROP VIEW IF EXISTS public.users CASCADE;
DROP TABLE IF EXISTS public.users CASCADE;
--
-- PostgreSQL database dump
--

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.5

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP POLICY IF EXISTS users_self_select ON public.users;
DROP POLICY IF EXISTS service_role_all_conversation ON public.conversation_history;
DROP POLICY IF EXISTS service_role_all_booking_notif ON public.booking_notifications;
DROP POLICY IF EXISTS service_role_all_booking_audit ON public.booking_audit_logs;
DROP POLICY IF EXISTS org_membership_select ON public.organization_users;
DROP POLICY IF EXISTS org_members_select_embeddings ON public.rag_embeddings;
DROP POLICY IF EXISTS org_members_select_conversations ON public.conversations;
DROP POLICY IF EXISTS org_members_select_chatbots ON public.chatbots;
DROP POLICY IF EXISTS org_members_select ON public.organizations;
DROP POLICY IF EXISTS "Users can see their own data" ON public.app_users;
DROP POLICY IF EXISTS "Users can see public form templates" ON public.form_templates;
DROP POLICY IF EXISTS "Users can see org resource schedules" ON public.resource_schedules;
DROP POLICY IF EXISTS "Users can see org leads" ON public.leads;
DROP POLICY IF EXISTS "Users can see org form fields" ON public.form_fields;
DROP POLICY IF EXISTS "Users can see org form configurations" ON public.form_configurations;
DROP POLICY IF EXISTS "Users can see org bot usage daily" ON public.bot_usage_daily;
DROP POLICY IF EXISTS "Users can see org bot calendar settings" ON public.bot_calendar_settings;
DROP POLICY IF EXISTS "Users can see org bot calendar oauth" ON public.bot_calendar_oauth;
DROP POLICY IF EXISTS "Users can see org bot booking settings" ON public.bot_booking_settings;
DROP POLICY IF EXISTS "Users can see org bookings" ON public.bookings;
DROP POLICY IF EXISTS "Users can see org booking resources" ON public.booking_resources;
DROP POLICY IF EXISTS "Users can see org appointments" ON public.bot_appointments;
ALTER TABLE IF EXISTS ONLY public.rag_embeddings DROP CONSTRAINT IF EXISTS rag_embeddings_org_id_fkey;
ALTER TABLE IF EXISTS ONLY public.rag_embeddings DROP CONSTRAINT IF EXISTS rag_embeddings_bot_id_fkey;
ALTER TABLE IF EXISTS ONLY public.organization_users DROP CONSTRAINT IF EXISTS organization_users_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.organization_users DROP CONSTRAINT IF EXISTS organization_users_org_id_fkey;
ALTER TABLE IF EXISTS ONLY public.conversations DROP CONSTRAINT IF EXISTS conversations_org_id_fkey;
ALTER TABLE IF EXISTS ONLY public.conversations DROP CONSTRAINT IF EXISTS conversations_bot_id_fkey;
ALTER TABLE IF EXISTS ONLY public.chatbots DROP CONSTRAINT IF EXISTS chatbots_org_id_fkey;
ALTER TABLE IF EXISTS ONLY public.chatbots DROP CONSTRAINT IF EXISTS chatbots_created_by_fkey;
DROP INDEX IF EXISTS public.rag_embeddings_org_bot_idx;
DROP INDEX IF EXISTS public.rag_embeddings_ivf_idx;
DROP INDEX IF EXISTS public.rag_embeddings_bot_idx;
DROP INDEX IF EXISTS public.idx_resource_schedules_resource;
DROP INDEX IF EXISTS public.idx_form_fields_config;
DROP INDEX IF EXISTS public.idx_form_configs_bot;
DROP INDEX IF EXISTS public.idx_conversation_session;
DROP INDEX IF EXISTS public.idx_bookings_resource;
DROP INDEX IF EXISTS public.idx_bookings_date;
DROP INDEX IF EXISTS public.idx_bookings_bot;
DROP INDEX IF EXISTS public.idx_booking_resources_bot;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_email_key;
ALTER TABLE IF EXISTS ONLY public.resource_schedules DROP CONSTRAINT IF EXISTS resource_schedules_pkey;
ALTER TABLE IF EXISTS ONLY public.rag_embeddings DROP CONSTRAINT IF EXISTS rag_embeddings_pkey;
ALTER TABLE IF EXISTS ONLY public.organizations DROP CONSTRAINT IF EXISTS organizations_pkey;
ALTER TABLE IF EXISTS ONLY public.organization_users DROP CONSTRAINT IF EXISTS organization_users_pkey;
ALTER TABLE IF EXISTS ONLY public.leads DROP CONSTRAINT IF EXISTS leads_pkey;
ALTER TABLE IF EXISTS ONLY public.form_templates DROP CONSTRAINT IF EXISTS form_templates_pkey;
ALTER TABLE IF EXISTS ONLY public.form_fields DROP CONSTRAINT IF EXISTS form_fields_pkey;
ALTER TABLE IF EXISTS ONLY public.form_configurations DROP CONSTRAINT IF EXISTS form_configurations_pkey;
ALTER TABLE IF EXISTS ONLY public.form_configurations DROP CONSTRAINT IF EXISTS form_configurations_bot_id_key;
ALTER TABLE IF EXISTS ONLY public.conversations DROP CONSTRAINT IF EXISTS conversations_pkey;
ALTER TABLE IF EXISTS ONLY public.conversation_history DROP CONSTRAINT IF EXISTS conversation_history_pkey;
ALTER TABLE IF EXISTS ONLY public.chatbots DROP CONSTRAINT IF EXISTS chatbots_pkey;
ALTER TABLE IF EXISTS ONLY public.bot_usage_daily DROP CONSTRAINT IF EXISTS bot_usage_daily_pkey;
ALTER TABLE IF EXISTS ONLY public.bot_calendar_settings DROP CONSTRAINT IF EXISTS bot_calendar_settings_pkey;
ALTER TABLE IF EXISTS ONLY public.bot_calendar_oauth DROP CONSTRAINT IF EXISTS bot_calendar_oauth_pkey;
ALTER TABLE IF EXISTS ONLY public.bot_booking_settings DROP CONSTRAINT IF EXISTS bot_booking_settings_pkey;
ALTER TABLE IF EXISTS ONLY public.bot_appointments DROP CONSTRAINT IF EXISTS bot_appointments_pkey;
ALTER TABLE IF EXISTS ONLY public.bookings DROP CONSTRAINT IF EXISTS bookings_pkey;
ALTER TABLE IF EXISTS ONLY public.booking_resources DROP CONSTRAINT IF EXISTS booking_resources_pkey;
ALTER TABLE IF EXISTS ONLY public.booking_notifications DROP CONSTRAINT IF EXISTS booking_notifications_pkey;
ALTER TABLE IF EXISTS ONLY public.booking_audit_logs DROP CONSTRAINT IF EXISTS booking_audit_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.app_users DROP CONSTRAINT IF EXISTS app_users_pkey;
ALTER TABLE IF EXISTS ONLY public.app_users DROP CONSTRAINT IF EXISTS app_users_email_key;
ALTER TABLE IF EXISTS public.rag_embeddings ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.leads ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.conversation_history ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.bot_appointments ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.bookings ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.booking_notifications ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.booking_audit_logs ALTER COLUMN id DROP DEFAULT;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.resource_schedules;
DROP SEQUENCE IF EXISTS public.rag_embeddings_id_seq;
DROP TABLE IF EXISTS public.rag_embeddings;
DROP TABLE IF EXISTS public.organizations;
DROP TABLE IF EXISTS public.organization_users;
DROP SEQUENCE IF EXISTS public.leads_id_seq;
DROP TABLE IF EXISTS public.leads;
DROP TABLE IF EXISTS public.form_templates;
DROP TABLE IF EXISTS public.form_fields;
DROP TABLE IF EXISTS public.form_configurations;
DROP TABLE IF EXISTS public.conversations;
DROP SEQUENCE IF EXISTS public.conversation_history_id_seq;
DROP TABLE IF EXISTS public.conversation_history;
DROP TABLE IF EXISTS public.chatbots;
DROP TABLE IF EXISTS public.bot_usage_daily;
DROP TABLE IF EXISTS public.bot_calendar_settings;
DROP TABLE IF EXISTS public.bot_calendar_oauth;
DROP TABLE IF EXISTS public.bot_booking_settings;
DROP SEQUENCE IF EXISTS public.bot_appointments_id_seq;
DROP TABLE IF EXISTS public.bot_appointments;
DROP SEQUENCE IF EXISTS public.bookings_id_seq;
DROP TABLE IF EXISTS public.bookings;
DROP TABLE IF EXISTS public.booking_resources;
DROP SEQUENCE IF EXISTS public.booking_notifications_id_seq;
DROP TABLE IF EXISTS public.booking_notifications;
DROP SEQUENCE IF EXISTS public.booking_audit_logs_id_seq;
DROP TABLE IF EXISTS public.booking_audit_logs;
DROP TABLE IF EXISTS public.app_users;
DROP FUNCTION IF EXISTS public.get_available_slots(p_resource_id text, p_date date);
DROP FUNCTION IF EXISTS public.check_slot_capacity(p_bot_id text, p_booking_date date, p_start_time time without time zone, p_end_time time without time zone);
DROP FUNCTION IF EXISTS public.check_resource_capacity(p_resource_id text, p_booking_date date, p_start_time time without time zone, p_end_time time without time zone);
DROP SCHEMA IF EXISTS public;
--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: check_resource_capacity(text, date, time without time zone, time without time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_resource_capacity(p_resource_id text, p_booking_date date, p_start_time time without time zone, p_end_time time without time zone) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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
                              and start_time = p_start_time
                              and end_time = p_end_time
                              and status not in ('cancelled', 'rejected');
                            
                            -- Return true if there's capacity available
                            return v_booked_count < v_capacity;
                        end;
                        $$;


--
-- Name: check_slot_capacity(text, date, time without time zone, time without time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_slot_capacity(p_bot_id text, p_booking_date date, p_start_time time without time zone, p_end_time time without time zone) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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


--
-- Name: get_available_slots(text, date); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_available_slots(p_resource_id text, p_date date) RETURNS TABLE(slot_start time without time zone, slot_end time without time zone, available_capacity integer)
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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
                                    -- Count bookings for this slot
                                    select count(*) into v_booked
                                    from public.bookings
                                    where resource_id = p_resource_id
                                      and booking_date = p_date
                                      and start_time = v_current_time
                                      and status not in ('cancelled', 'rejected');
                                    
                                    slot_start := v_current_time;
                                    slot_end := v_current_time + (v_slot_duration || ' minutes')::interval;
                                    available_capacity := v_capacity - coalesce(v_booked, 0);
                                    
                                    return next;
                                    
                                    v_current_time := v_current_time + (v_slot_duration || ' minutes')::interval;
                                end loop;
                            end loop;
                        end;
                        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: app_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_users (
    id text NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    org_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.app_users FORCE ROW LEVEL SECURITY;


--
-- Name: booking_audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.booking_audit_logs (
    id bigint NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    appointment_id bigint,
    action text NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY public.booking_audit_logs FORCE ROW LEVEL SECURITY;


--
-- Name: booking_audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.booking_audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: booking_audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.booking_audit_logs_id_seq OWNED BY public.booking_audit_logs.id;


--
-- Name: booking_notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.booking_notifications (
    id bigint NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    appointment_id bigint,
    type text NOT NULL,
    recipient text,
    payload jsonb,
    status text DEFAULT 'queued'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY public.booking_notifications FORCE ROW LEVEL SECURITY;


--
-- Name: booking_notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.booking_notifications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: booking_notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.booking_notifications_id_seq OWNED BY public.booking_notifications.id;


--
-- Name: booking_resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.booking_resources (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    resource_type text NOT NULL,
    resource_name text NOT NULL,
    resource_code text,
    description text,
    capacity_per_slot integer DEFAULT 1 NOT NULL,
    metadata jsonb,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    department text
);

ALTER TABLE ONLY public.booking_resources FORCE ROW LEVEL SECURITY;


--
-- Name: bookings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bookings (
    id bigint NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    form_config_id text,
    customer_name text NOT NULL,
    customer_email text NOT NULL,
    customer_phone text,
    booking_date date NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    resource_id text,
    resource_name text,
    form_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    cancellation_reason text,
    calendar_event_id text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    confirmed_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    external_event_id text
);

ALTER TABLE ONLY public.bookings FORCE ROW LEVEL SECURITY;


--
-- Name: bookings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bookings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bookings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bookings_id_seq OWNED BY public.bookings.id;


--
-- Name: bot_appointments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_appointments (
    id bigint NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    summary text,
    start_iso text,
    end_iso text,
    attendees_json jsonb,
    external_event_id text,
    status text DEFAULT 'scheduled'::text,
    user_contact text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY public.bot_appointments FORCE ROW LEVEL SECURITY;


--
-- Name: bot_appointments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bot_appointments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bot_appointments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bot_appointments_id_seq OWNED BY public.bot_appointments.id;


--
-- Name: bot_booking_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_booking_settings (
    org_id text NOT NULL,
    bot_id text NOT NULL,
    timezone text,
    available_windows jsonb,
    slot_duration_minutes integer DEFAULT 30,
    capacity_per_slot integer DEFAULT 1,
    min_notice_minutes integer DEFAULT 60,
    max_future_days integer DEFAULT 60,
    suggest_strategy text DEFAULT 'next_best'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    required_user_fields jsonb
);

ALTER TABLE ONLY public.bot_booking_settings FORCE ROW LEVEL SECURITY;


--
-- Name: bot_calendar_oauth; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_calendar_oauth (
    org_id text NOT NULL,
    bot_id text NOT NULL,
    provider text NOT NULL,
    access_token_enc text,
    refresh_token_enc text,
    token_expiry timestamp with time zone,
    calendar_id text,
    watch_channel_id text,
    watch_resource_id text,
    watch_expiration timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    timezone text
);

ALTER TABLE ONLY public.bot_calendar_oauth FORCE ROW LEVEL SECURITY;


--
-- Name: bot_calendar_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_calendar_settings (
    org_id text NOT NULL,
    bot_id text NOT NULL,
    provider text NOT NULL,
    calendar_id text,
    timezone text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY public.bot_calendar_settings FORCE ROW LEVEL SECURITY;


--
-- Name: bot_usage_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_usage_daily (
    org_id text NOT NULL,
    bot_id text NOT NULL,
    day date NOT NULL,
    chats integer DEFAULT 0 NOT NULL,
    successes integer DEFAULT 0 NOT NULL,
    fallbacks integer DEFAULT 0 NOT NULL,
    sum_similarity double precision DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY public.bot_usage_daily FORCE ROW LEVEL SECURITY;


--
-- Name: chatbots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chatbots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    name text NOT NULL,
    description text,
    behavior text DEFAULT 'support'::text NOT NULL,
    system_prompt text,
    temperature real DEFAULT 0.2 NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    public_api_key text,
    website_url text,
    role text,
    tone text,
    welcome_message text,
    public_api_key_rotated_at timestamp with time zone,
    services text[],
    form_config jsonb,
    CONSTRAINT chatbots_behavior_check CHECK ((behavior = ANY (ARRAY['support'::text, 'sales'::text, 'appointment'::text, 'qna'::text])))
);


--
-- Name: conversation_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_history (
    id bigint NOT NULL,
    session_id text NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY public.conversation_history FORCE ROW LEVEL SECURITY;


--
-- Name: conversation_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversation_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversation_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversation_history_id_seq OWNED BY public.conversation_history.id;


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    bot_id uuid,
    external_user_id text,
    last_user_message text,
    last_bot_message text,
    messages jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: form_configurations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form_configurations (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    name text NOT NULL,
    description text,
    industry text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.form_configurations FORCE ROW LEVEL SECURITY;


--
-- Name: form_fields; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form_fields (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    form_config_id text NOT NULL,
    field_name text NOT NULL,
    field_label text NOT NULL,
    field_type text NOT NULL,
    field_order integer DEFAULT 0 NOT NULL,
    is_required boolean DEFAULT false NOT NULL,
    placeholder text,
    help_text text,
    validation_rules jsonb,
    options jsonb,
    default_value text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb
);

ALTER TABLE ONLY public.form_fields FORCE ROW LEVEL SECURITY;


--
-- Name: form_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form_templates (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    industry text NOT NULL,
    description text,
    template_data jsonb NOT NULL,
    is_public boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.form_templates FORCE ROW LEVEL SECURITY;


--
-- Name: leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leads (
    id bigint NOT NULL,
    org_id text NOT NULL,
    bot_id text NOT NULL,
    name text,
    email text,
    phone text,
    interest_details text,
    comments text,
    conversation_summary text,
    interest_score integer DEFAULT 0,
    status text DEFAULT 'new'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    session_id text
);


--
-- Name: leads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.leads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: leads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.leads_id_seq OWNED BY public.leads.id;


--
-- Name: organization_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_users (
    org_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text DEFAULT 'member'::text NOT NULL,
    CONSTRAINT organization_users_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'admin'::text, 'member'::text])))
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: rag_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_embeddings (
    id bigint NOT NULL,
    org_id uuid,
    bot_id uuid,
    doc_id uuid,
    chunk_id integer,
    content text NOT NULL,
    embedding extensions.vector(1024) NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: rag_embeddings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_embeddings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_embeddings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_embeddings_id_seq OWNED BY public.rag_embeddings.id;


--
-- Name: resource_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resource_schedules (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    resource_id text NOT NULL,
    day_of_week integer,
    specific_date date,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    slot_duration_minutes integer DEFAULT 30 NOT NULL,
    is_available boolean DEFAULT true NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.resource_schedules FORCE ROW LEVEL SECURITY;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email text,
    display_name text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: booking_audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_audit_logs ALTER COLUMN id SET DEFAULT nextval('public.booking_audit_logs_id_seq'::regclass);


--
-- Name: booking_notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_notifications ALTER COLUMN id SET DEFAULT nextval('public.booking_notifications_id_seq'::regclass);


--
-- Name: bookings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookings ALTER COLUMN id SET DEFAULT nextval('public.bookings_id_seq'::regclass);


--
-- Name: bot_appointments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_appointments ALTER COLUMN id SET DEFAULT nextval('public.bot_appointments_id_seq'::regclass);


--
-- Name: conversation_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_history ALTER COLUMN id SET DEFAULT nextval('public.conversation_history_id_seq'::regclass);


--
-- Name: leads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads ALTER COLUMN id SET DEFAULT nextval('public.leads_id_seq'::regclass);


--
-- Name: rag_embeddings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_embeddings ALTER COLUMN id SET DEFAULT nextval('public.rag_embeddings_id_seq'::regclass);


--
-- Data for Name: app_users; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.app_users VALUES ('3cbceda3-f551-4ba5-928d-f82ce871e679', 'sanket@gmail.com', 'pbkdf2$150000$ov49CBaq1nzdyBMb$wnx9wMwUqKZCz9LUsAurxKSuB2N85Hh8w7lrXhK9ipQ=', 'sanket', '2025-11-23 18:41:44.786963+00');
INSERT INTO public.app_users VALUES ('b7217c15-74dc-4161-8ad0-14a483ad2417', 'hello@gmail.com', 'pbkdf2$150000$74JRN3ZwihnRy9HC$cPL0bOdClxrod1htg_alpmRzFIZ4zBAIF5kpfstguqA=', '074171de-bc84-5ea4-b636-1135477620e1', '2025-11-25 15:35:23.766499+00');
INSERT INTO public.app_users VALUES ('0b9049c6-7e6a-402e-96ac-dd2083d12230', 'demo@example.com', 'pbkdf2$150000$NSxt-2SJARbEMKf9$uvCwV035Cpzx4WTVJy-oHXH9b-_eVQL3Va1Qnl71nM0=', '966aaed4-cfe6-5120-89f0-64d6c459770b', '2025-11-29 11:39:26.559048+00');


--
-- Data for Name: booking_audit_logs; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.booking_audit_logs VALUES (1, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 6, 'create', '{"end_iso": "2025-12-06T01:00:00", "start_iso": "2025-12-06T00:30:00"}', '2025-12-06 07:41:37.761199+00');
INSERT INTO public.booking_audit_logs VALUES (2, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 7, 'create', '{"end_iso": "2025-12-06T01:00:00", "start_iso": "2025-12-06T00:30:00"}', '2025-12-06 07:41:42.998943+00');
INSERT INTO public.booking_audit_logs VALUES (3, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 8, 'create', '{"end_iso": "2025-12-06T01:00:00", "start_iso": "2025-12-06T00:30:00"}', '2025-12-06 09:15:48.405355+00');
INSERT INTO public.booking_audit_logs VALUES (4, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 8, 'reschedule', '{"new_end_iso": "2025-12-07T15:30:00", "new_start_iso": "2025-12-07T15:00:00"}', '2025-12-06 09:39:40.975079+00');
INSERT INTO public.booking_audit_logs VALUES (5, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 8, 'cancel', '{}', '2025-12-06 11:19:12.877968+00');
INSERT INTO public.booking_audit_logs VALUES (6, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 9, 'create', '{"end_iso": "2025-12-06T21:00:00", "start_iso": "2025-12-06T20:30:00"}', '2025-12-06 11:21:03.817898+00');
INSERT INTO public.booking_audit_logs VALUES (7, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 10, 'create', '{"end_iso": "2025-12-07T21:00:00", "start_iso": "2025-12-07T20:30:00"}', '2025-12-06 11:23:30.410874+00');
INSERT INTO public.booking_audit_logs VALUES (8, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 11, 'create', '{"end_iso": "2025-12-09T04:00:00+00:00", "start_iso": "2025-12-09T03:30:00+00:00"}', '2025-12-06 12:03:05.362718+00');
INSERT INTO public.booking_audit_logs VALUES (9, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 12, 'create', '{"end_iso": "2025-12-08T04:00:00+00:00", "start_iso": "2025-12-08T03:30:00+00:00"}', '2025-12-06 12:05:35.93972+00');
INSERT INTO public.booking_audit_logs VALUES (10, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 13, 'create', '{"end_iso": "2025-12-08T04:30:00+00:00", "start_iso": "2025-12-08T04:00:00+00:00"}', '2025-12-06 12:07:44.55823+00');
INSERT INTO public.booking_audit_logs VALUES (11, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 14, 'create', '{"end_iso": "2025-12-08T04:30:00+00:00", "start_iso": "2025-12-08T04:00:00+00:00"}', '2025-12-06 13:18:50.853569+00');
INSERT INTO public.booking_audit_logs VALUES (12, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 15, 'create', '{"end_iso": "2025-12-08T04:00:00+00:00", "start_iso": "2025-12-08T03:30:00+00:00"}', '2025-12-06 13:31:15.792981+00');
INSERT INTO public.booking_audit_logs VALUES (13, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 16, 'create', '{"end_iso": "2025-12-08T05:00:00+00:00", "start_iso": "2025-12-08T04:30:00+00:00"}', '2025-12-06 13:32:55.848059+00');
INSERT INTO public.booking_audit_logs VALUES (14, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 17, 'create', '{"end_iso": "2025-12-08T05:00:00+00:00", "start_iso": "2025-12-08T04:30:00+00:00"}', '2025-12-06 13:45:04.609342+00');
INSERT INTO public.booking_audit_logs VALUES (15, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 18, 'create', '{"end_iso": "2025-12-08T04:00:00+00:00", "start_iso": "2025-12-08T03:30:00+00:00"}', '2025-12-06 15:15:45.575438+00');
INSERT INTO public.booking_audit_logs VALUES (16, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 19, 'create', '{"end_iso": "2025-12-08T04:00:00+00:00", "start_iso": "2025-12-08T03:30:00+00:00"}', '2025-12-07 16:54:24.197146+00');
INSERT INTO public.booking_audit_logs VALUES (17, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 20, 'create', '{"end_iso": "2025-12-08T04:00:00+00:00", "start_iso": "2025-12-08T03:30:00+00:00"}', '2025-12-07 17:05:52.60163+00');
INSERT INTO public.booking_audit_logs VALUES (18, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 21, 'create', '{"end_iso": "2025-12-08T04:30:00+00:00", "start_iso": "2025-12-08T04:00:00+00:00"}', '2025-12-07 19:02:06.401414+00');
INSERT INTO public.booking_audit_logs VALUES (19, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 22, 'create', '{"end_iso": "2025-12-08T05:00:00+00:00", "start_iso": "2025-12-08T04:30:00+00:00"}', '2025-12-08 03:19:54.712647+00');
INSERT INTO public.booking_audit_logs VALUES (20, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 23, 'create', '{"end_iso": "2025-12-10T07:30:00+00:00", "start_iso": "2025-12-10T07:00:00+00:00"}', '2025-12-08 17:28:07.84512+00');
INSERT INTO public.booking_audit_logs VALUES (21, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 24, 'create', '{"end_iso": "2025-12-09T09:00:00+00:00", "start_iso": "2025-12-09T08:30:00+00:00"}', '2025-12-08 17:45:25.21801+00');
INSERT INTO public.booking_audit_logs VALUES (22, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 25, 'create', '{"end_iso": "2025-12-09T07:30:00+00:00", "start_iso": "2025-12-09T07:00:00+00:00"}', '2025-12-09 05:36:23.635594+00');
INSERT INTO public.booking_audit_logs VALUES (23, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 17, 'cancel', '{}', '2025-12-14 18:27:48.030826+00');
INSERT INTO public.booking_audit_logs VALUES (24, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 15, 'cancel', '{}', '2025-12-14 18:45:37.651479+00');
INSERT INTO public.booking_audit_logs VALUES (25, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 18, 'cancel', '{}', '2025-12-15 15:30:37.391178+00');


--
-- Data for Name: booking_notifications; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.booking_notifications VALUES (1, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 6, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 6}', 'queued', '2025-12-06 07:41:37.856485+00', '2025-12-06 07:41:37.856485+00');
INSERT INTO public.booking_notifications VALUES (2, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 7, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 7}', 'queued', '2025-12-06 07:41:43.060755+00', '2025-12-06 07:41:43.060755+00');
INSERT INTO public.booking_notifications VALUES (3, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 8, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 8}', 'queued', '2025-12-06 09:15:48.480329+00', '2025-12-06 09:15:48.480329+00');
INSERT INTO public.booking_notifications VALUES (4, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 9, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 9}', 'queued', '2025-12-06 11:21:03.847985+00', '2025-12-06 11:21:03.847985+00');
INSERT INTO public.booking_notifications VALUES (5, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 10, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 10}', 'queued', '2025-12-06 11:23:30.468106+00', '2025-12-06 11:23:30.468106+00');
INSERT INTO public.booking_notifications VALUES (6, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 11, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 11}', 'queued', '2025-12-06 12:03:05.454613+00', '2025-12-06 12:03:05.454613+00');
INSERT INTO public.booking_notifications VALUES (7, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 12, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 12}', 'queued', '2025-12-06 12:05:36.000891+00', '2025-12-06 12:05:36.000891+00');
INSERT INTO public.booking_notifications VALUES (8, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 13, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 13}', 'queued', '2025-12-06 12:07:44.635102+00', '2025-12-06 12:07:44.635102+00');
INSERT INTO public.booking_notifications VALUES (9, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 14, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 14}', 'queued', '2025-12-06 13:18:50.945754+00', '2025-12-06 13:18:50.945754+00');
INSERT INTO public.booking_notifications VALUES (10, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 15, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 15}', 'queued', '2025-12-06 13:31:15.876109+00', '2025-12-06 13:31:15.876109+00');
INSERT INTO public.booking_notifications VALUES (11, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 16, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 16}', 'queued', '2025-12-06 13:32:55.904302+00', '2025-12-06 13:32:55.904302+00');
INSERT INTO public.booking_notifications VALUES (12, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 17, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 17}', 'queued', '2025-12-06 13:45:04.701333+00', '2025-12-06 13:45:04.701333+00');
INSERT INTO public.booking_notifications VALUES (13, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 18, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 18}', 'queued', '2025-12-06 15:15:45.637342+00', '2025-12-06 15:15:45.637342+00');
INSERT INTO public.booking_notifications VALUES (14, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 19, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 19}', 'queued', '2025-12-07 16:54:24.253916+00', '2025-12-07 16:54:24.253916+00');
INSERT INTO public.booking_notifications VALUES (15, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 20, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 20}', 'queued', '2025-12-07 17:05:52.649613+00', '2025-12-07 17:05:52.649613+00');
INSERT INTO public.booking_notifications VALUES (16, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 21, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 21}', 'queued', '2025-12-07 19:02:06.786484+00', '2025-12-07 19:02:06.786484+00');
INSERT INTO public.booking_notifications VALUES (17, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 22, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 22}', 'queued', '2025-12-08 03:19:54.782501+00', '2025-12-08 03:19:54.782501+00');
INSERT INTO public.booking_notifications VALUES (18, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 23, 'confirmation', 'ashish@gmail.com', '{"appointment_id": 23}', 'queued', '2025-12-08 17:28:07.980591+00', '2025-12-08 17:28:07.980591+00');
INSERT INTO public.booking_notifications VALUES (19, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 24, 'confirmation', 'ashish@gmail.com', '{"appointment_id": 24}', 'queued', '2025-12-08 17:45:25.349984+00', '2025-12-08 17:45:25.349984+00');
INSERT INTO public.booking_notifications VALUES (20, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 25, 'confirmation', 'sanketapatil2003@gmail.com', '{"appointment_id": 25}', 'queued', '2025-12-09 05:36:23.780954+00', '2025-12-09 05:36:23.780954+00');


--
-- Data for Name: booking_resources; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.booking_resources VALUES ('dr_pranav', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'doctor', 'Dr pranav', 'dr_pranav', NULL, 3, NULL, true, '2025-12-13 15:01:12.12972+00', '2025-12-13 15:01:12.12972+00', 'hair ');
INSERT INTO public.booking_resources VALUES ('6e0afeff-3c5a-4879-a312-93df601dda88', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'doctor', 'Dr Sanket Patil', 'dr_sanket_patil', NULL, 2, NULL, true, '2025-12-13 16:12:16.186508+00', '2025-12-13 16:12:16.186508+00', 'cardiology');
INSERT INTO public.booking_resources VALUES ('6c25f35b-dfaf-4456-a40a-d110d79d2c09', 'default-org', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'doctor', 'hello', NULL, NULL, 2, NULL, false, '2025-12-13 12:59:32.223286+00', '2025-12-13 17:50:52.845967+00', NULL);
INSERT INTO public.booking_resources VALUES ('dr_sanket', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'doctor', 'Dr sankey', 'dr_sanket', NULL, 1, NULL, false, '2025-12-13 15:01:11.142708+00', '2025-12-13 17:51:01.294567+00', 'car');
INSERT INTO public.booking_resources VALUES ('febbfab7-a22a-4c50-964c-f54d9ed104b0', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'doctor', 'Dr Sanket Patil', 'dr_sanket_patil', NULL, 2, NULL, false, '2025-12-13 16:13:30.612879+00', '2025-12-13 17:51:11.122759+00', 'cardiology');
INSERT INTO public.booking_resources VALUES ('2b7b42e3-f6cd-47d5-a5da-84c8027391da', 'default-org', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'doctor', 'Dr sanket ', NULL, NULL, 5, NULL, false, '2025-12-13 11:59:00.325219+00', '2025-12-13 17:51:21.686093+00', NULL);
INSERT INTO public.booking_resources VALUES ('52a3e1b8-dd12-4924-abdd-bb279c4c1907', 'default-org', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'service', 'hello service', NULL, NULL, 1, NULL, true, '2025-12-15 16:03:10.041721+00', '2025-12-15 16:03:10.041721+00', NULL);


--
-- Data for Name: bookings; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.bookings VALUES (11, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket patil', 'sanket@gmail.com', '9865321478', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test sys", "department": "neurology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, 'rfvhilbtpa672t372v8ba70120', NULL, '2025-12-13 10:07:21.376527+00', '2025-12-13 10:07:21.376527+00', NULL, NULL, 'rfvhilbtpa672t372v8ba70120');
INSERT INTO public.bookings VALUES (16, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'sankey', 'sanket@gmail.com', '98776544321', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test", "doctor_name": "6e0afeff-3c5a-4879-a312-93df601dda88", "appointment_type": "consultation"}', 'cancelled', NULL, 'ja68ovaviif0tgr68j5rrmfib8', NULL, '2025-12-13 17:02:47.728274+00', '2025-12-13 17:02:47.728274+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (3, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'sanket@gmail.com', '25252525252', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test ", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 08:48:35.259545+00', '2025-12-13 08:48:35.259545+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (4, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'sanket@gmail.com', '5545454545', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "this is test", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 08:54:15.527941+00', '2025-12-13 08:54:15.527941+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (2, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'sanket@gmail.com', '63636363636', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "not well ", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 08:39:51.235453+00', '2025-12-13 08:39:51.235453+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (5, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'sanket@gmail.com', '252525252', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test ysy", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 09:06:09.72359+00', '2025-12-13 09:06:09.72359+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (12, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'sanket P', 'sanket@gail.com', '1515454545', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test", "department": "neurology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, 'hotsk2328cqk5000t1er861u9c', NULL, '2025-12-13 10:19:26.45072+00', '2025-12-13 10:19:26.45072+00', NULL, NULL, 'hotsk2328cqk5000t1er861u9c');
INSERT INTO public.bookings VALUES (6, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'sanket@gmail.com', '77777878887', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test sysmptom", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 09:18:11.023794+00', '2025-12-13 09:18:11.023794+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (7, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'SAnket', 'Sanket@gmail.com', '9595952357', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "this is test ", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 09:27:26.684016+00', '2025-12-13 09:27:26.684016+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (8, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'Sanket@gmail.com', '959586556', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "this is test message ", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 09:33:17.999599+00', '2025-12-13 09:33:17.999599+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (9, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'sanket', 'sanket@gmail.om', '454545454', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test the test", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, 'g6rl30ajin4cpepsrol40ludso', NULL, '2025-12-13 09:37:55.493665+00', '2025-12-13 09:37:55.493665+00', NULL, NULL, 'g6rl30ajin4cpepsrol40ludso');
INSERT INTO public.bookings VALUES (10, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'sanket@gmail.com', '98989898', '2025-12-15', '09:30:00', '10:00:00', NULL, NULL, '{"symptoms": "this is test ", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, 'lg232q5krn8q6pc0baimb805kg', NULL, '2025-12-13 10:02:57.415768+00', '2025-12-13 10:02:57.415768+00', NULL, NULL, 'lg232q5krn8q6pc0baimb805kg');
INSERT INTO public.bookings VALUES (13, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket Anant PAtil', 'sanket@gmail.com', '9876543212', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "hello this is the test ", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "consultation"}', 'cancelled', NULL, 'tmod78uau13tljrcf1nlnapcdk', NULL, '2025-12-13 10:41:21.384623+00', '2025-12-13 10:41:21.384623+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (14, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Seema', 'seema@gmail.com', '98765433212', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test", "department": "neurology", "doctor name ": "Dr_sanket", "appointment_type": "followup"}', 'cancelled', NULL, '66qdjvhj7qoj90tq9nqhkeor0k', NULL, '2025-12-13 10:45:08.804385+00', '2025-12-13 10:45:08.804385+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (1, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'sanket', 'sanket@gmail.com', '3636363255', '2025-12-15', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "", "department": "cardiology", "doctor name ": "Dr_sanket", "appointment_type": "followup"}', 'cancelled', NULL, NULL, NULL, '2025-12-13 08:32:47.278581+00', '2025-12-13 08:32:47.278581+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (15, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket', 'sanket@gmail.com', '9876543212', '2025-12-15', '11:00:00', '11:30:00', 'dr_pranav', 'Dr pranav', '{"symptoms": "test", "doctor_name": "2b7b42e3-f6cd-47d5-a5da-84c8027391da", "appointment_type": "consultation"}', 'cancelled', NULL, 'knrorqahgnaq4lu5rmt91g97gg', NULL, '2025-12-13 16:43:51.228255+00', '2025-12-13 16:43:51.228255+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (17, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'sanket', 'sanket@gmail.com', '9876532244', '2025-12-14', '09:00:00', '09:30:00', NULL, NULL, '{"symptoms": "test", "doctor_name": "dr_pranav", "appointment_type": "followup"}', 'completed', NULL, '9imsemle75j34ch15ieh0hr61s', NULL, '2025-12-14 18:21:26.743318+00', '2025-12-14 18:30:07.435602+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (18, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'SAnket', 'sanket@gmail.com', '98989898', '2025-12-22', '07:00:00', '07:30:00', NULL, NULL, '{"symptoms": "thus istestv ", "doctor_name": "6e0afeff-3c5a-4879-a312-93df601dda88", "appointment_type": "followup"}', 'cancelled', NULL, 'mvo5viuvliv9rac8kftmk0ccg0', NULL, '2025-12-15 15:14:53.767098+00', '2025-12-15 15:30:37.351542+00', NULL, '2025-12-15 15:30:37.351542+00', NULL);
INSERT INTO public.bookings VALUES (19, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'sanket patil', 'sanket@gmail.com', '9876543321425', '2025-12-22', '11:00:00', '11:30:00', NULL, NULL, '{"symptoms": "test", "doctor_name": "dr_pranav", "appointment_type": "followup"}', 'completed', NULL, 'bpa275c0cndddu61uimb714kd4', NULL, '2025-12-15 15:55:31.067261+00', '2025-12-22 06:00:34.973222+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (21, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket Patil', 'patilsanket2411@gmail.com', '9324608194', '2025-12-22', '07:00:00', '07:30:00', NULL, NULL, '{"reason": "", "symptoms": "", "doctor_name": "6e0afeff-3c5a-4879-a312-93df601dda88", "appointment_type": "emergency"}', 'completed', NULL, 'j6cbi4j6b69ftchcn24dcdgsr0', NULL, '2025-12-19 07:09:30.323396+00', '2025-12-22 02:00:16.591428+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (20, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Ashish', 'ashish@gmail.com', '913767367', '2025-12-22', '09:00:00', '09:30:00', '6e0afeff-3c5a-4879-a312-93df601dda88', 'Dr Sanket Patil', '{"reason": "fever", "symptoms": "", "doctor_name": "dr_pranav", "appointment_type": "consultation"}', 'completed', NULL, 'vodg2afoe40g8kmn2a6alp19q0', NULL, '2025-12-19 06:45:40.307326+00', '2025-12-22 04:00:26.352996+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (22, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Ashish', 'ashishkhandagle36@gmail.com', '9137673670', '2025-12-24', '07:40:00', '07:45:00', NULL, NULL, '{"reason": "headache", "symptoms": "", "doctor_name": "dr_pranav", "appointment_type": "followup"}', 'confirmed', NULL, NULL, NULL, '2025-12-23 14:10:58.560694+00', '2025-12-23 14:10:58.560694+00', NULL, NULL, NULL);
INSERT INTO public.bookings VALUES (23, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'Sanket Patil', 'patilsanket2411@gmail.com', '9324608194', '2025-12-24', '07:40:00', '07:45:00', NULL, NULL, '{"reason": "", "symptoms": "", "doctor_name": "dr_pranav", "appointment_type": "consultation"}', 'confirmed', NULL, NULL, NULL, '2025-12-23 14:41:32.264422+00', '2025-12-23 14:41:32.264422+00', NULL, NULL, NULL);


--
-- Data for Name: bot_appointments; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: bot_booking_settings; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.bot_booking_settings VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'Asia/Calcutta', '[{"day": "Mon", "end": "17:00", "start": "09:00"}, {"day": "Tue", "end": "17:00", "start": "09:00"}, {"day": "Wed", "end": "17:00", "start": "09:00"}, {"day": "Thu", "end": "17:00", "start": "09:00"}, {"day": "Fri", "end": "17:00", "start": "09:00"}]', 30, 5, 60, 60, NULL, '2025-12-05 18:43:11.131014+00', '2025-12-13 16:22:14.44571+00', NULL);


--
-- Data for Name: bot_calendar_oauth; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.bot_calendar_oauth VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'google', 'gAAAAABpSsG9sIMJ9E-5O7dj0t9h1EpRdJDPEz1TneC-RAfcDgnN7yEGLx4HGgqTORcKf9SX4TxiB54R8dl9iLyLXp752etlKp59Z0GdZ-vT9AGC422AKw79QFeDVqpMtVsvQZY833hCUQY00yLgLwD1c_fTqj4_KQPIzMTm_R8KMdQv_mmxsKn-Ceh_K2WycYVeNZ2nUFP9ua9haJkD3sqqqT2Xk2m2f7h4yGAkjsxEhAW66pNCGx1ao4A4cSVXpQUkxB-pm95ZYuLUYVvQ4R6j97tfZsqzzlGLxZPPVRUm-lVQ6h_UEgixTVfMW91y4oapFEs1gYjYa2hPlKj80u9hXHjKyj58T2r3iJBuWcEDdVi49CW4RnT3sudF7_asqceDo63fg8zilYLYaPO6qDLayeGLefZ71Q==', 'gAAAAABpSsG9K3etYpQam3EVz6kyXe4vyZ_K0t_zXrDULrYoC48f5eDO0b77JJ-YRTB4Jn68vsfHnUEcFxZ5FG2EPFmcUQsMX4f3PPB8O8DrXkVPr-RU_SD1zKTfTYOyG7U_rS3loZ9Z0vGrIuEiP6Ut7Sc3MWAFTvPJMuMr9qMY3juHYDX3x7P9dbGL7wGmawM66zDTFv7lkBwcZofkJD2LrA4o2KrbZw==', '2025-12-23 17:22:21+00', 'primary', NULL, NULL, NULL, '2025-12-05 18:28:46.162768+00', '2025-12-23 16:22:21.703276+00', 'Asia/Calcutta');


--
-- Data for Name: bot_calendar_settings; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.bot_calendar_settings VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'google', 'primary', NULL, '2025-12-05 18:28:46.195799+00', '2025-12-23 16:22:21.837142+00');


--
-- Data for Name: bot_usage_daily; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-11-26', 46, 46, 0, 9.985555883910674, '2025-11-26 16:31:33.036998+00', '2025-11-26 19:33:27.785998+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-11-25', 32, 32, 0, 4.974774368966359, '2025-11-25 14:33:24.35347+00', '2025-11-25 15:11:43.118883+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-11-23', 54, 24, 30, 0.5135372574976685, '2025-11-23 18:55:42.220448+00', '2025-11-23 20:00:30.727621+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-11-28', 98, 98, 0, 37.49399816456066, '2025-11-28 04:01:57.962021+00', '2025-11-28 19:50:05.207414+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-01', 7, 5, 2, 0.0903398599088022, '2025-12-01 03:59:46.468109+00', '2025-12-01 12:51:30.1556+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-08', 42, 36, 6, 3.165938563317769, '2025-12-08 03:19:25.20766+00', '2025-12-08 18:56:07.10216+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-23', 21, 21, 0, 13.089929801651092, '2025-12-23 04:59:36.812774+00', '2025-12-23 16:00:51.924997+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-06', 77, 36, 41, 2.432468891379662, '2025-12-06 07:05:35.71153+00', '2025-12-06 15:15:12.494229+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-11-24', 16, 15, 1, 1.4672473454020034, '2025-11-24 16:47:31.116983+00', '2025-11-24 18:18:05.803883+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-17', 9, 9, 0, 0.2792684634548433, '2025-12-17 06:04:37.262596+00', '2025-12-17 20:13:52.524277+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-05', 10, 10, 0, 0.36975300614311735, '2025-12-05 18:55:18.734401+00', '2025-12-05 20:02:41.449596+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-14', 58, 54, 4, 31.76259062179772, '2025-12-14 09:28:52.110831+00', '2025-12-14 19:02:45.408768+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-18', 35, 35, 0, 12.047732927021652, '2025-12-18 16:36:13.750195+00', '2025-12-18 18:57:00.292009+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-09', 49, 47, 2, 14.05907728616575, '2025-12-09 05:30:39.484647+00', '2025-12-09 14:54:10.906469+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-21', 41, 41, 0, 12.13678985618469, '2025-12-21 12:11:56.000481+00', '2025-12-21 15:45:45.65468+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-13', 69, 58, 11, 43.8798691990969, '2025-12-13 07:56:53.848176+00', '2025-12-13 21:04:26.342659+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-11', 7, 5, 2, 0.947495967810109, '2025-12-11 04:44:27.626884+00', '2025-12-11 04:51:42.806621+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-19', 6, 6, 0, 4.880197017145871, '2025-12-19 06:44:15.969392+00', '2025-12-19 07:08:45.543045+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-11-27', 37, 37, 0, 7.601277626854937, '2025-11-27 04:14:02.552738+00', '2025-11-27 18:27:00.185844+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-11-29', 80, 77, 3, 3.070968614310981, '2025-11-29 07:41:09.892195+00', '2025-11-29 18:01:40.623571+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-15', 86, 82, 4, 22.456773004013233, '2025-12-15 05:56:10.363058+00', '2025-12-15 19:05:51.509868+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-07', 32, 25, 7, 0.6341145505598993, '2025-12-07 16:26:21.207777+00', '2025-12-07 19:23:37.080855+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-16', 35, 35, 0, 20.220185276482134, '2025-12-16 08:39:28.306596+00', '2025-12-16 20:36:53.729462+00');
INSERT INTO public.bot_usage_daily VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '2025-12-20', 66, 66, 0, 17.0163137257268, '2025-12-20 09:43:35.542057+00', '2025-12-20 18:21:53.082173+00');


--
-- Data for Name: chatbots; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.chatbots VALUES ('6fcdeff6-56b1-4ad7-af93-697b3959b04c', '966aaed4-cfe6-5120-89f0-64d6c459770b', 'Demo Bot', NULL, 'support', 'You are a helpful support assistant.', 0.2, NULL, '2025-11-29 11:39:27.564074+00', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.chatbots VALUES ('c61ec4c9-deaf-4ce6-ba24-9f479e96c614', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'test', NULL, 'appointment', 'Help users schedule appointments. Collect required details and respect constraints from provided context.', 0.2, NULL, '2025-11-23 18:46:24.200135+00', 'F3TO0pSqPJSP1qTGFmmIksLqKRFPNZtcJ3spALyISWw', NULL, NULL, NULL, 'Welcome to Codeweft Technologies! Book your appointment in seconds or ask about our services, I’m here to help.', '2025-11-23 19:17:39.110426+00', '{chatbot,"voice bot"}', '{"email_domains": ["gmail.com"], "phone_restriction": "10_digits", "phone_country_code": "+91"}');


--
-- Data for Name: conversation_history; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation_history VALUES (437, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'hello', '2025-12-23 04:59:35.22708+00');
INSERT INTO public.conversation_history VALUES (438, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'Hello. Welcome to CodeWeft. I''m here to help you explore how our AI solutions can automate customer support, generate leads, and increase sales for your business. What brings you here today? Are you looking for a specific AI solution or would you like me to recommend some options?', '2025-12-23 04:59:35.375101+00');
INSERT INTO public.conversation_history VALUES (439, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'what u can do', '2025-12-23 05:03:06.747508+00');
INSERT INTO public.conversation_history VALUES (440, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'I can help you explore CodeWeft''s AI solutions to automate customer support, generate leads, and increase sales for your business. Our AI products include:

1. **Chat Assistant**: Context-aware responses, multi-language support, and 24/7 availability.
2. **Voice Assistant**: Hands-free voice recognition and interactive voice feedback.
3. **Appointment Booking Assistant**: Automated booking, rescheduling, and canceling appointments.
4. **AI Phone Agent**: Automatically calls potential buyers, collects lead responses, and works 24/7.

I can also provide information on our industry-specific solutions for Healthcare, Real Estate, Education, and Retail & ECommerce. How can I assist you today? Would you like to learn more about a specific product or schedule a demo?', '2025-12-23 05:03:06.890135+00');
INSERT INTO public.conversation_history VALUES (441, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'okay', '2025-12-23 05:04:28.330655+00');
INSERT INTO public.conversation_history VALUES (442, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'You''ve taken a look at our AI products and industries we serve. What would you like to do next? Would you like to:

1. **Explore a specific product** (e.g., Chat Assistant, Voice Assistant)?
2. **Learn more about our solutions for a particular industry** (e.g., Healthcare, Education)?
3. **Request a demo** to see our AI products in action?
4. **Get a free trial** to try out our AI tools?

Let me know, and I''ll be happy to assist you!', '2025-12-23 05:04:28.460113+00');
INSERT INTO public.conversation_history VALUES (443, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'get a free trail', '2025-12-23 05:05:08.416739+00');
INSERT INTO public.conversation_history VALUES (444, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'You''re interested in trying out our AI products. You can get a **Free Trial** for the following products:

1. **Chat Assistant**: Try our context-aware chatbot with multi-language support and knowledge base integration.
2. **AI Voice-Powered Hospital Assistant**: Experience conversational AI trained for healthcare queries with interactive voice feedback.
3. **AI Appointment Booking Chat Assistant**: Test our 24/7 intelligent assistant for booking and rescheduling appointments.

To get started, simply click on the **Free Trial** button next to the product you''re interested in, and we''ll guide you through the process. Would you like me to help you with the trial setup or answer any questions you may have?', '2025-12-23 05:05:08.55516+00');
INSERT INTO public.conversation_history VALUES (445, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'who made the codeweft', '2025-12-23 05:05:56.705108+00');
INSERT INTO public.conversation_history VALUES (446, 'sess_1766465941567_8y6nf0lsr', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'CodeWeft was founded in 2024 by a team of expert developers, data scientists, and AI specialists. Unfortunately, the specific names of the founders are not mentioned on the website. However, it is mentioned that the company is a cutting-edge AI and software development company dedicated to creating intelligent solutions that solve complex business problems.', '2025-12-23 05:05:56.834995+00');
INSERT INTO public.conversation_history VALUES (447, 'sess_1766497757918_scqtowhks', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'hello', '2025-12-23 13:49:44.546456+00');
INSERT INTO public.conversation_history VALUES (448, 'sess_1766497757918_scqtowhks', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'Hello. Welcome to CodeWeft. I''m here to help you explore our AI solutions for your business. What brings you here today? Are you looking to automate customer support, generate leads, or improve sales?', '2025-12-23 13:49:44.690757+00');
INSERT INTO public.conversation_history VALUES (449, 'sess_1766500840115_6006g64gh', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'Id 22', '2025-12-23 14:42:58.792132+00');
INSERT INTO public.conversation_history VALUES (450, 'sess_1766500840115_6006g64gh', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'To schedule an appointment, I''ll need some details. Can you please provide your name, preferred date, and time for the appointment?', '2025-12-23 14:42:58.93592+00');
INSERT INTO public.conversation_history VALUES (451, 'sess_1766500840115_6006g64gh', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'Status id 22', '2025-12-23 14:43:37.868625+00');
INSERT INTO public.conversation_history VALUES (452, 'sess_1766500840115_6006g64gh', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'Status ID 22: Appointment scheduled successfully. Would you like to book another appointment or view your schedule?', '2025-12-23 14:43:37.996148+00');
INSERT INTO public.conversation_history VALUES (453, 'sess_1766500840115_6006g64gh', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'Details id 22', '2025-12-23 14:44:09.511596+00');
INSERT INTO public.conversation_history VALUES (454, 'sess_1766500840115_6006g64gh', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'For ID 22, I need to collect some details to schedule an appointment. Can you please provide your name, preferred date, and time for the appointment, as well as the type of appointment (e.g., healthcare, real estate, education, etc.)?', '2025-12-23 14:44:09.650859+00');
INSERT INTO public.conversation_history VALUES (455, 'sess_1766497757918_scqtowhks', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'hello', '2025-12-23 14:46:14.826715+00');
INSERT INTO public.conversation_history VALUES (456, 'sess_1766497757918_scqtowhks', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'Hello. Welcome to CodeWeft. I''m here to help you explore our AI products. What are you looking for? Do you need assistance with customer support, appointment booking, or perhaps lead generation?', '2025-12-23 14:46:14.956317+00');
INSERT INTO public.conversation_history VALUES (457, 'sess_1766497757918_scqtowhks', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'ok', '2025-12-23 14:48:57.107599+00');
INSERT INTO public.conversation_history VALUES (458, 'sess_1766497757918_scqtowhks', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'You''ve already taken the first step by submitting your enquiry form. I''m here to help you explore our AI products and find the perfect solution for your business. Which product caught your attention, or would you like me to recommend one based on your needs?', '2025-12-23 14:48:57.248085+00');
INSERT INTO public.conversation_history VALUES (459, 'sess_1766505291092_8gmw06yh4', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'hello', '2025-12-23 15:55:23.083512+00');
INSERT INTO public.conversation_history VALUES (460, 'sess_1766505291092_8gmw06yh4', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'Hello. Welcome to CodeWeft - AI Products. How can I assist you today? Are you looking for AI solutions for your business or interested in learning more about our products?', '2025-12-23 15:55:23.232059+00');
INSERT INTO public.conversation_history VALUES (461, 'sess_1766505291092_8gmw06yh4', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'user', 'yes', '2025-12-23 15:56:03.629758+00');
INSERT INTO public.conversation_history VALUES (462, 'sess_1766505291092_8gmw06yh4', '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'assistant', 'You''re interested in learning more about our AI products. Which industry or solution are you most interested in: Healthcare, Real Estate, Education, or Retail & ECommerce? Or would you like to explore our products, such as Chat Assistant or AI Phone Agent?', '2025-12-23 15:56:03.759645+00');


--
-- Data for Name: conversations; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: form_configurations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.form_configurations VALUES ('16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'default-org', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', 'Appointment ', 'this form is used for appointmnet ', 'healthcare', true, '2025-12-13 07:54:21.156572+00', '2025-12-13 12:00:17.185096+00');


--
-- Data for Name: form_fields; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.form_fields VALUES ('5cc594bb-8c60-45af-84cf-665e8e39351c', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'symptoms', 'Symptoms', 'textarea', 3, false, 'Describe your symptoms', NULL, NULL, NULL, NULL, true, '2025-12-13 07:55:07.444594+00', '2025-12-13 07:55:07.444594+00', '{}');
INSERT INTO public.form_fields VALUES ('210aaa94-4a29-4e73-b594-23376e159c16', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'doctor name ', 'sanket patil', 'select', 4, true, 'select the doctor ', 'hello', NULL, '[{"label": "Dr sanket Patil", "value": "Dr_sanket", "capacity": 2, "metadata": null}]', NULL, false, '2025-12-13 08:01:03.450742+00', '2025-12-13 08:07:06.067612+00', '{}');
INSERT INTO public.form_fields VALUES ('66bad7ad-4b1f-436b-91ad-a9b836397afb', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'department', 'Department', 'select', 2, true, NULL, NULL, NULL, '[{"label": "Cardiology", "value": "cardiology"}, {"label": "Neurology", "value": "neurology"}, {"label": "Pediatrics", "value": "pediatrics"}, {"label": "General Medicine", "value": "general"}]', NULL, false, '2025-12-13 07:55:07.36164+00', '2025-12-13 15:34:06.905754+00', '{}');
INSERT INTO public.form_fields VALUES ('e985a5fe-d3a2-4eb1-bcf2-3832a1bf9f1c', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'doctor_name', 'Select Doctor', 'select', 3, true, NULL, NULL, NULL, NULL, NULL, true, '2025-12-13 16:17:51.978496+00', '2025-12-13 16:17:51.978496+00', '{}');
INSERT INTO public.form_fields VALUES ('08ceac4e-2e1b-45bb-be47-0e68091de495', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'doctor name ', 'select doctor ', 'select', 4, true, 'select the doctor ', 'plase select the doctor', NULL, '[]', NULL, false, '2025-12-13 08:01:02.225645+00', '2025-12-13 16:18:03.148218+00', '{}');
INSERT INTO public.form_fields VALUES ('046e44c2-6b1a-4200-8cbf-5c53388eac74', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'appointment_type', 'Appointment Type', 'select', 1, true, NULL, NULL, NULL, '[{"label": "General Consultation", "value": "consultation"}, {"label": "Follow-up Visit", "value": "followup"}, {"label": "Emergency", "value": "emergency"}, {"label": "abc", "value": "xyz"}]', NULL, true, '2025-12-13 07:55:07.326526+00', '2025-12-15 15:06:52.695655+00', '{}');
INSERT INTO public.form_fields VALUES ('51e0efb7-be05-4569-8ccf-d25e8a9f7cef', '16e0194a-0b49-4634-8c19-6ead90aeb9b3', 'reason', 'enter your reason', 'text', 3, true, NULL, NULL, NULL, NULL, NULL, true, '2025-12-16 17:05:20.233792+00', '2025-12-16 17:58:53.9972+00', '{}');


--
-- Data for Name: form_templates; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.form_templates VALUES ('healthcare-template', 'Healthcare - Doctor Appointment', 'healthcare', 'Standard medical appointment booking form', '{"fields": [{"options": [{"label": "General Consultation", "value": "consultation"}, {"label": "Follow-up Visit", "value": "followup"}, {"label": "Emergency", "value": "emergency"}], "field_name": "appointment_type", "field_type": "select", "field_label": "Appointment Type", "field_order": 1, "is_required": true}, {"options": [{"label": "Cardiology", "value": "cardiology"}, {"label": "Neurology", "value": "neurology"}, {"label": "Pediatrics", "value": "pediatrics"}, {"label": "General Medicine", "value": "general"}], "field_name": "department", "field_type": "select", "field_label": "Department", "field_order": 2, "is_required": true}, {"field_name": "symptoms", "field_type": "textarea", "field_label": "Symptoms", "field_order": 3, "is_required": false, "placeholder": "Describe your symptoms"}]}', true, '2025-12-13 07:40:47.684278+00', '2025-12-13 07:40:47.684278+00');
INSERT INTO public.form_templates VALUES ('salon-template', 'Salon - Beauty Appointment', 'salon', 'Beauty salon and spa booking form', '{"fields": [{"options": [{"label": "Haircut", "value": "haircut"}, {"label": "Hair Coloring", "value": "coloring"}, {"label": "Manicure", "value": "manicure"}, {"label": "Pedicure", "value": "pedicure"}], "field_name": "service", "field_type": "select", "field_label": "Service Type", "field_order": 1, "is_required": true}, {"options": [{"label": "30 minutes", "value": "30"}, {"label": "1 hour", "value": "60"}, {"label": "1.5 hours", "value": "90"}], "field_name": "duration", "field_type": "select", "field_label": "Estimated Duration", "field_order": 2, "is_required": true}]}', true, '2025-12-13 07:40:47.736974+00', '2025-12-13 07:40:47.736974+00');


--
-- Data for Name: leads; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: organization_users; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: organizations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.organizations VALUES ('5c2228c1-c4a2-5bed-9468-464bd32df471', '5c2228c1-c4a2-5bed-9468-464bd32df471', '2025-11-23 18:46:23.894534+00');
INSERT INTO public.organizations VALUES ('074171de-bc84-5ea4-b636-1135477620e1', 'test2', '2025-11-25 15:35:23.658999+00');
INSERT INTO public.organizations VALUES ('966aaed4-cfe6-5120-89f0-64d6c459770b', 'demo', '2025-11-29 11:39:26.359299+00');


--
-- Data for Name: rag_embeddings; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.rag_embeddings VALUES (189, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, 'CODEWEFT - AI Products

Weaving Intelligence Into Tomorrow
Weaving Intelligence
Into The Fabric of Tomorrow
Cutting-edge AI solutions that transform businesses through voice bots, chatbots, and intelligent automation. Explore Products
Learn More
Our AI solutions that transform your business
Power smarter conversations and seamless operations with our AI tools.', '[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0.11111111,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0,0,0,0,0,0,0,0,0.22222222,0,0.11111111,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.44444445,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0,0.11111111,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0.22222222,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.22222222,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11111111,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]', '{"language": "en", "page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "57707f83cb0c4d28de0c69d10d7991ca9306c81506ec40569ced6d2005bee41e", "canonical_url": "https://codeweft.in/"}', '2025-12-01 12:35:59.894484+00');
INSERT INTO public.rag_embeddings VALUES (190, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, 'Explore Products
Learn More
Our AI solutions that transform your business
Power smarter conversations and seamless operations with our AI tools. All
Chat Assistant
Voice Assistant
Appointment Booking Assistant
AI Phone Agent
AI Appointment Booking Chat Assistant
Context-aware responses
Multi-language support
Knowledge base integration
24/7 availability
Learn More
Free Trial
AI Voice-Powered Hospital Assistant
Conversational AI trained for healthcare queries
Supports booking, editing, and canceling appointments via voice
Interactive voice feedback with multilingual support
Learn More
Free Trial
AI Appointment Booking Voice + Chat Assistant
Hands-free voice recognition & intuitive chat interface
Multi-language support for inclusive interactions
24/7 intelligent assistant for booking, rescheduling
Learn More
Free Trial
AI Phone Calling Agent
Calls potential buyers automatically
Collects lead responses & preferences
Works 24/7 without human effort
Learn More
Quick Demo
Available Now
Industries
Tailored AI that drives impact across industries.', '[0,0.04756515,0,0,0.04756515,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0.0951303,0,0,0,0.04756515,0,0,0,0,0,0,0,0.04756515,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.0951303,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0.04756515,0,0,0.04756515,0,0,0,0,0.04756515,0,0,0,0,0,0.04756515,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.0951303,0,0,0,0,0,0.0951303,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0.28539088,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0.14269544,0,0,0,0,0.14269544,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.14269544,0,0,0,0,0,0,0,0.0951303,0,0,0,0,0,0.23782575,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.14269544,0,0,0,0,0,0.04756515,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0.0951303,0,0,0,0,0,0,0.14269544,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.1902606,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0.33295605,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0.14269544,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.42808634,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0.23782575,0,0,0,0,0,0,0,0,0.1902606,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.0951303,0,0,0,0,0,0,0,0,0,0,0,0,0,0.0951303,0,0,0.04756515,0.04756515,0,0,0,0,0,0,0,0.14269544,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0.04756515,0,0,0,0,0.28539088,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0.0951303,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0.04756515,0,0,0.04756515,0,0,0.04756515,0,0.04756515,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]', '{"language": "en", "page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "4165655ad348ff4eb9784a36d3d96b3d1b960ec5c09fa429acfe9f040c9192ae", "canonical_url": "https://codeweft.in/"}', '2025-12-01 12:36:00.608198+00');
INSERT INTO public.rag_embeddings VALUES (191, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, 'All
Chat Assistant
Voice Assistant
Appointment Booking Assistant
AI Phone Agent
AI Appointment Booking Chat Assistant
Context-aware responses
Multi-language support
Knowledge base integration
24/7 availability
Learn More
Free Trial
AI Voice-Powered Hospital Assistant
Conversational AI trained for healthcare queries
Supports booking, editing, and canceling appointments via voice
Interactive voice feedback with multilingual support
Learn More
Free Trial
AI Appointment Booking Voice + Chat Assistant
Hands-free voice recognition & intuitive chat interface
Multi-language support for inclusive interactions
24/7 intelligent assistant for booking, rescheduling
Learn More
Free Trial
AI Phone Calling Agent
Calls potential buyers automatically
Collects lead responses & preferences
Works 24/7 without human effort
Learn More
Quick Demo
Available Now
Industries
Tailored AI that drives impact across industries. 🏥
Healthcare & Hospitals
AI scheduling, patient support, and intelligent diagnostics.', '[0,0.050507627,0,0,0.050507627,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.101015255,0,0,0,0.050507627,0,0,0,0,0,0,0,0.050507627,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0.050507627,0,0,0.050507627,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.101015255,0,0,0,0,0,0.101015255,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.101015255,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0.30304575,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0.15152287,0,0,0,0,0.15152287,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.15152287,0,0,0,0,0,0,0,0.101015255,0,0,0,0,0,0.20203051,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.15152287,0,0,0,0,0,0.050507627,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0.101015255,0,0,0,0,0,0,0.20203051,0.101015255,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20203051,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0.35355338,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0.15152287,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.40406102,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0.20203051,0,0,0,0,0,0,0,0,0.20203051,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0.101015255,0,0,0.050507627,0.050507627,0,0,0,0,0,0,0,0.15152287,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0.25253814,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0.050507627,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0.050507627,0,0,0.050507627,0,0,0,0,0.050507627,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]', '{"language": "en", "page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "1c2c57ec3908875169d74e028ae367f58497318c7288c71393876523578f6035", "canonical_url": "https://codeweft.in/"}', '2025-12-01 12:36:01.290855+00');
INSERT INTO public.rag_embeddings VALUES (192, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, '🏥
Healthcare & Hospitals
AI scheduling, patient support, and intelligent diagnostics. 🏘️
Real Estate
Property bots, lead capture, and appointment setting 24/7. 🎓
Education
Virtual tutors, student services, and intelligent scheduling assistants. 🛍️
Retail & ECommerce
Order tracking, returns processing, and product recommendation bots. Why Choose Our AI Products
Our AI products are engineered for performance, scalability, and seamless integration, delivering measurable results for your business. Industry-Leading Technology
Our products leverage state-of-the-art AI for unmatched performance in voice and text interactions. Customizable Solutions
Tailor our AI Voice Assistant, Chat Bots, and Appointment Booking System to fit your brand and workflows. Seamless Integration
Our products integrate effortlessly with your existing platforms, ensuring quick deployment. Proven Reliability
Trusted by businesses worldwide, our AI products deliver consistent, high-quality performance.', '[0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0.11396058,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0.34188172,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0.05698029,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0.11396058,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0.05698029,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.45584232,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0.11396058,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0.05698029,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0.05698029,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11396058,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11396058,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.17094086,0,0,0,0,0.05698029,0,0,0,0.05698029,0,0.05698029,0,0,0,0,0,0,0,0,0.11396058,0,0.05698029,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0.05698029,0.05698029,0.05698029,0,0,0,0,0.05698029,0,0,0.05698029,0.11396058,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0.17094086,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0.05698029,0.05698029,0.05698029,0,0.05698029,0.05698029,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0.34188172,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0.05698029,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0.17094086,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0.05698029,0,0,0,0,0,0,0,0,0,0.05698029,0,0.05698029,0,0,0.11396058,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0.28490144,0,0,0,0,0,0.05698029,0,0,0,0,0,0,0.05698029,0,0,0.05698029,0.05698029,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.17094086,0,0,0,0,0,0,0,0,0,0.17094086,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]', '{"language": "en", "page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "189c85179cd814213576d8901a8ef6c7f57da5566980d488abeaddf6263900bb", "canonical_url": "https://codeweft.in/"}', '2025-12-01 12:36:01.886567+00');
INSERT INTO public.rag_embeddings VALUES (193, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, 'Proven Reliability
Trusted by businesses worldwide, our AI products deliver consistent, high-quality performance. Dedicated Support
Our team provides 24/7 support to ensure your AI products run smoothly. About Us
We are a cutting-edge AI and software development company dedicated to creating intelligent solutions that solve complex business problems. With our team of expert developers, data scientists, and AI specialists, we deliver innovative products that drive digital transformation. Founded in 2024, we''ve been at the forefront of AI innovation, helping businesses across industries leverage the power of artificial intelligence and machine learning to gain competitive advantages. Our Mission
At CodeWeft, we''re weaving intelligence into the fabric of tomorrow''s technology. Our mission is to democratize advanced AI capabilities, making them accessible, practical, and transformative for businesses of all sizes. We believe that AI should enhance human potential, not replace it.', '[0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2803861,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2803861,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0.056077216,0,0,0,0,0,0.2803861,0,0,0,0,0.056077216,0,0,0.056077216,0,0,0.056077216,0,0,0,0.056077216,0,0,0,0.16823165,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0.056077216,0.056077216,0,0,0,0,0.056077216,0,0.056077216,0,0,0.22430886,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0.056077216,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0.056077216,0,0.11215443,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0.11215443,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0.056077216,0.056077216,0,0,0.056077216,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11215443,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.11215443,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0.056077216,0,0,0,0,0,0,0,0,0.056077216,0.056077216,0,0.16823165,0,0,0,0,0,0,0,0,0.11215443,0.056077216,0,0,0,0,0,0,0,0.16823165,0.056077216,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0.056077216,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0.056077216,0,0,0,0,0,0,0.056077216,0,0.22430886,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0.3925405,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0.11215443,0,0.16823165,0,0,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0.11215443,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0.056077216,0,0.056077216,0,0,0,0,0,0,0.056077216,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0.056077216,0,0.16823165,0,0.056077216,0,0,0,0.11215443,0,0,0,0,0,0,0.056077216,0,0,0,0.056077216,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.056077216,0.056077216,0,0,0,0,0,0,0,0,0.056077216,0,0,0,0,0,0,0,0,0.11215443,0,0,0,0,0,0,0,0,0]', '{"language": "en", "page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "9b6305767696e008bc8c834cd37905f6f908e6b9138fb829446add13f71083f6", "canonical_url": "https://codeweft.in/"}', '2025-12-01 12:36:02.466652+00');
INSERT INTO public.rag_embeddings VALUES (194, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, 'We believe that AI should enhance human potential, not replace it. Every solution we build aims to augment human capabilities, allowing people to focus on creative, strategic, and empathetic work. Contact Us
Get in touch to explore how our AI products can elevate your business. Get in Touch
Email:
codeweft.ai@gmail.com
Phone:
+91 9137673670
Headquarters: Mumbai, MH, India
Your Name
Your Number
Your Message
Select Product
AI Voice Assistant
AI Chat Bots
AI Phone Calling Agent
AI Appointment Booking
Your Email
Send', '[0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.14990634,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.14990634,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0.07495317,0,0,0,0.07495317,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0.14990634,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0.07495317,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0.14990634,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0.07495317,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0.2248595,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0.5246722,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0.14990634,0,0,0,0,0,0,0,0.07495317,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.14990634,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.14990634,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.14990634,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0.07495317,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.449719,0,0,0,0,0,0,0,0,0,0,0.07495317,0,0,0,0,0,0,0]', '{"language": "en", "page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "c44fe2bdd3e643ecfbd1ac519aeb40a220fe00375c0454a7791c38d9e4b06882", "canonical_url": "https://codeweft.in/"}', '2025-12-01 12:36:03.1149+00');
INSERT INTO public.rag_embeddings VALUES (196, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, 'CODEWEFT - AI Products', '[0.020984616,0.020641826,-0.023914564,-0.0027538533,-0.005709478,0.0060807,-0.032318126,-0.00065994414,-0.0043891063,0.013682403,-0.009729519,0.031480376,-0.020327764,-0.038411308,-0.0035287144,0.011091267,-0.0043089963,-0.028160388,-0.06498912,-0.007362497,0.042098373,-0.0023592294,-0.07632393,-0.026584195,-0.05260314,0.029138986,-0.0015227825,-0.038084973,0.09883699,0.04080866,-0.047509532,-0.03334926,0.03594976,-0.06413379,-0.033584706,-0.023317745,-0.01247457,0.044973247,-0.030368991,-0.07206629,-0.0059088687,-0.045755148,0.022937397,-0.053095695,-0.075304925,-0.00074212253,0.019174226,0.0012683846,-0.009828478,-0.04307324,-0.00029802698,0.026318261,0.042738434,-0.065868706,-0.030106826,-0.013172176,-0.0018339241,-0.04229487,-0.02466027,0.010552899,0.045586076,0.020882865,-0.008623331,-0.04756846,-0.017295511,0.0016270305,0.012360761,0.0065659555,0.028375395,0.016990745,0.0099597685,0.009724308,-0.0032090116,-0.04461543,-0.011604744,-0.013901931,-0.017387597,0.0015595712,-0.008180439,-0.008585309,-0.0060863425,0.042611722,-0.025353143,0.032787785,-0.019657476,-0.013855511,-0.0018541026,0.0036647357,-0.015044749,0.010630294,-0.050392453,0.020563236,0.0025500243,-0.00011967828,0.0010271905,0.019757414,0.006298535,0.02206917,-0.013859738,0.025640568,0.024084942,0.06205408,-0.02762437,0.02146814,-0.0058271307,0.01776338,0.01774599,-0.040481333,-0.029280515,-0.03166688,-0.01806003,-0.000642952,-0.020324409,0.014577583,0.024645235,0.016560048,-0.020265713,0.0033384522,-0.012398869,0.016108265,-0.014431609,0.012888915,-0.01745097,0.0016824636,-0.005828223,-0.06250564,0.00018718961,0.009945979,0.031688314,-0.0028297387,0.0023979077,-0.0075326255,-0.008694887,0.030763235,0.009449883,0.030582525,-0.029804897,0.016257975,-0.0063397833,0.014575793,0.041371092,-0.031175707,0.014289182,0.090634145,0.007918825,0.020930016,-0.009991941,-0.013272115,-0.041870378,-0.008281929,-0.028971806,0.0168099,-0.015908528,0.027897319,-0.005629284,-0.05802108,-0.015231121,0.035064615,0.050422817,0.026612919,0.024177715,0.0040152934,-0.02210287,0.034477677,-0.0561028,0.025533402,-0.018155321,0.0025834914,-0.025729215,-0.003163397,-0.0027797061,0.004821383,-0.02724362,-0.0071134483,0.021522572,0.025640823,0.05767584,0.020928351,0.030332787,0.0006804759,-0.036047317,-0.013244128,-0.003064137,0.045166034,-0.020525139,-0.0059348345,0.02942588,0.0006455086,0.0066642696,0.0024201963,0.03491388,0.045855045,-0.06597953,0.05502895,-0.058377318,0.013182981,0.0030022943,0.04519033,0.027193546,-0.024576562,-0.040521413,0.03764366,-0.016554171,-0.05713489,-0.024020653,0.0007142472,-0.0031287866,0.005158173,-0.054358255,-0.008275406,-0.0049664285,-0.022851354,-0.005981521,-0.059622772,0.027034527,0.0011181459,-0.048257012,0.031595927,-0.01926041,-0.0050009526,0.020519312,0.024414236,0.034893353,0.03859255,0.00011886741,0.024405656,-0.012609696,0.0657034,0.0073044966,0.03353733,0.02145461,0.057477925,0.008336368,0.04787216,-0.0050486876,0.032006767,0.003762686,0.037529405,0.023117557,0.0024392188,-0.02067106,-0.020363338,0.013250802,0.02303174,0.016864456,-0.021869458,0.015695278,-0.01107695,-0.0038271875,0.0018795206,-0.06777328,0.03780257,-0.010941231,0.012103698,-0.024791028,-0.0189712,0.014034605,0.024112234,-0.016095813,0.030651165,0.021870404,0.05434744,0.004739967,0.019297559,0.04651366,0.052530676,0.052637894,-0.008831105,-0.06794849,-0.042394355,-0.058754873,-0.06251855,-0.040671814,-0.021377595,-0.054312572,-0.01593112,-0.00048043457,-0.0048588235,0.02739693,-0.03679797,0.020092756,-0.017388765,-0.03289027,0.009686565,0.03396238,0.057385027,-0.04989463,0.00060845196,-0.0019757445,0.02613497,-0.019889465,0.020010052,0.012590468,-0.0354959,-0.013089298,0.01341653,-0.01675815,0.0027713408,-0.066574775,-0.03315438,-0.02088567,0.0051549687,0.0022850118,-0.008851974,-0.06582584,0.04428913,0.019502684,-0.03457474,0.054183695,0.022331119,-0.056046866,0.03607131,0.0063889194,0.022616362,-0.03200104,0.037104048,0.05274541,0.013765863,-0.06335864,-0.016149491,-0.05415384,0.056846417,-0.008654285,0.012470386,-0.018674208,0.00770239,-0.016580854,-0.110537216,0.012278532,-0.006689935,-0.06732013,-0.032126833,0.005094486,0.00969645,0.011441851,0.014476019,-0.013875777,-0.007836124,0.004234262,0.013645728,0.03844893,0.017701862,0.048221387,0.01932084,-0.0017863724,-0.029706415,0.026232911,-0.026803976,0.037532765,-0.01696833,-0.014449751,0.00535588,0.0062590516,-0.0023777909,0.011573538,0.036790736,-0.028415918,0.015672075,0.008451362,0.028409924,0.01895966,-0.0012967032,-0.0010341576,0.004219304,-0.03401384,-0.016404409,0.021787442,0.014911536,0.027385814,-0.06614381,-0.023538593,-0.0076262387,-0.037155863,0.04248049,0.004268215,-0.0401905,-0.011020317,0.030151857,0.044906463,-0.048987463,-0.045246378,0.022246044,0.04715411,0.029504083,-0.023678591,-0.00712248,-0.0052761785,0.02932251,-0.057293985,0.014556625,-0.02291011,-0.0028481293,-0.0082912,0.016330915,-0.019754639,-0.049016874,0.0033967167,-0.009530927,-0.0045121214,0.0134947905,0.024494076,0.04412567,0.025362907,0.041218404,-0.035506554,-0.014720964,0.0023949586,0.013675779,0.020151464,-0.019234452,-0.018507535,0.011907033,-0.01775748,0.029449953,-0.006261491,0.008179696,-0.025684476,0.011663502,0.004402537,0.056937147,0.015642082,0.018368302,-0.018485384,-0.0011980308,0.05029055,-0.04020777,0.0035121213,-0.050316688,-0.017886717,0.037707023,-0.02054735,0.0075221094,-0.028770259,-0.04200877,0.016204042,0.05665158,0.021895425,0.014096418,0.008310907,-0.029506397,0.023033453,-0.00852612,-0.017381463,0.009967391,0.0145850405,-0.027729461,0.014203325,0.0136056235,0.0064478666,-0.026787864,0.011642307,-0.053695552,0.000919787,-0.02678974,0.031269077,-0.013606233,0.025977451,-0.0027087384,0.033101648,0.03155808,-0.004059681,-0.0023861225,0.027243111,-0.05968687,-0.037190408,0.045735646,0.010724397,-0.010914339,0.03502774,-0.011491824,-0.018172264,0.015901705,-0.0005436053,-0.0073366333,-0.01583906,6.610712e-06,0.0004647268,-0.004073445,-0.054477874,-0.011162064,-0.030884609,0.0020535626,0.011851944,-0.022550063,-0.0021154217,-0.0427124,-0.027146801,0.02962518,-0.008277404,0.029977357,0.010152862,-0.028786056,0.053100307,-0.0039399955,-0.0072544524,-0.03317944,-0.019942444,-0.0026489277,0.04283855,0.004234794,0.051914606,-0.04263925,-0.03760489,-0.005789277,-0.016736345,0.007702568,-0.026004372,0.053407796,-0.0132552255,0.006393682,-0.029611414,0.0048399586,-0.06179021,0.0049992297,0.0034052082,0.02738133,0.0058798366,-0.033313643,-0.04669382,0.03370254,0.013901952,-0.047285683,-0.027449436,0.041521825,0.0047847503,0.04476713,0.03895183,0.0132281715,-0.03127909,-0.040016506,0.018101126,-0.04263154,0.0020051505,-0.0076257605,-0.03639992,-0.009150457,0.014643291,0.00594103,-0.050715785,-0.044101268,-0.023224985,0.008820341,-0.051142335,0.002497421,-0.03905664,0.003748286,0.027673835,-0.014708667,0.00600326,0.023068707,-0.010280165,0.03353929,0.020561036,0.025035687,-0.039280027,-0.041356653,0.028620934,-0.0071041067,0.00560904,-0.016911456,-0.041494608,0.027721457,-0.05445431,-0.020285312,-0.043292288,-0.007053035,-0.015336058,0.0045332685,0.04501441,0.011868569,0.009812886,-0.020590106,0.058154542,0.052118126,0.030523976,-0.0050748885,-0.052653667,-0.006764867,-0.04987531,0.0212202,-0.012864704,0.020906676,-0.025034059,-0.024637664,0.030775998,-0.023985088,0.042929985,0.07570903,-0.01338575,-0.0023380278,-0.012624558,0.0239799,0.015013189,-0.041337308,-9.36059e-05,0.031262856,0.011974389,0.00084394024,-0.022860352,-0.034845233,-0.02925438,0.027253741,0.051941432,-0.04041185,0.0333208,-0.017230606,-0.033227473,-0.03385085,0.03729182,-0.009493897,0.012010627,0.020774394,0.016278464,-0.009222384,0.030240634,-0.0041068317,-0.023999788,-0.0018239035,0.03389351,-0.014771401,-0.03326458,-0.0028821507,0.03157047,0.004904985,-0.045755513,0.0022340822,0.026392598,0.0037649963,-0.031285893,0.054248188,0.0077251415,0.01701074,0.00059433153,-0.01241299,-0.018561797,0.012629956,0.07680317,0.010660771,-0.054510165,0.009936639,0.017055165,-0.0025369148,-0.026359519,-0.022979941,-0.013350583,-0.033447567,-0.006784746,0.037757248,-0.00021882962,0.012430183,0.052472528,0.031184316,0.040343985,-0.014327465,0.010114282,0.013655752,-0.033292443,-0.04715187,-0.029336767,0.024206225,-0.033403922,0.0045803064,0.005905139,0.038138665,0.04980449,0.024299962,0.0034856817,-0.04442549,-0.021132905,-0.074195966,-0.024582567,0.030648049,-0.024994789,-0.013275365,0.012519029,-0.009788451,-0.03174664,-0.018358106,0.025318649,0.014622883,-0.026066246,-0.017720038,0.0038710944,-0.060024228,-0.02790122,0.03687822,0.024571827,-0.0027986567,3.107518e-05,-0.023309616,-0.025839625,0.02058954,0.04148593,-0.035291232,0.017925283,0.0077302554,-0.03467395,-0.043408576,0.025685022,-0.034914102,0.031950515,0.04678423,0.024074217,0.039962906,0.021843145,-0.015137089,-0.01940383,0.021004213,0.06483678,-0.021050371,0.032053474,-0.05217169,0.024216313,-0.010833428,0.010110157,0.04500609,-0.008795844,0.03509728,0.042224113,-0.03197,0.060106512,-0.012128936,0.004812311,-0.025124494,0.0003512221,-0.00380149,-0.030365257,0.04495919,-0.0017090496,0.02726374,-0.07357937,0.040347666,0.0075352467,-0.03508323,0.030761074,0.0029413274,-0.059486113,-0.022786139,-0.0170823,0.010266113,0.07824173,0.049339008,0.007534605,0.01612897,0.025985923,-0.05514353,-0.0011181447,-0.047054112,-0.005442638,0.032547057,-0.019284854,0.0148465885,-0.023203764,-0.009225577,-0.037514098,-0.023570795,0.016838774,0.012248599,0.024577036,-0.038286068,-0.0026471606,-0.08481423,-0.036104877,0.017962413,0.031915274,-0.03618224,-0.04420399,0.018252518,0.07482101,0.0024595167,0.0026345574,-0.03562133,-0.0081934165,0.00095841405,0.01042614,-0.042766754,0.042730395,-0.04457543,0.014790829,0.03262539,0.016150968,-0.048260126,0.042726938,0.018456068,0.019359834,0.017756544,0.023061154,0.020192493,-0.0036620663,-0.0026030166,-0.008361644,0.0023712846,0.0037808781,-0.012674175,0.02042267,0.04627993,0.03745675,0.057102136,-0.040991478,0.0279729,0.09059312,0.036948413,-0.0007749102,0.021288747,0.010613487,0.02828863,0.03355869,-0.031620014,0.030310404,-0.015370797,0.00063145603,-0.0020901705,0.013817621,-0.04392859,-0.004231217,-0.06614964,0.016030585,-0.004880594,-0.04758679,-0.032143053,-0.01604817,0.008677126,0.007241812,0.026933916,-0.008582798,0.020412477,0.030205823,0.01840705,-0.0049460377,0.008099351,0.00873741,-0.0027917123,-0.012885618,-0.01790742,0.013243225,0.023333233,-0.0024520862,-0.060837954,0.053279124,0.0022834141,-0.051800016,0.014255858,-0.022065962,-0.013431814,-0.030466186,-0.009761319,-0.035643976,-0.009711257,0.014791602,-0.01006664,-0.024687734,0.019517248,0.02085376,0.010607418,0.04763322,0.056335125,-0.040152993,0.040588375,0.06900409,-0.026385004,0.013738254,0.02823491,0.004669351,-0.043300517,-0.012212312,-0.024459457,-0.046212193,-0.027852643,-0.02301309,-0.008044031,0.026232133,0.0018035177,-0.020478977,-0.013139643,0.022482263,-0.03410325,0.0043927482,0.06784328,0.015484598,0.026887722,-0.037648097,0.010998501,-0.02209852,0.0018625027,-0.02919748,0.03273382,-0.02481511,0.0015669971,-0.010112452,0.015150967,-0.048922338,-0.03897541,-0.0039558816,-0.03510129,0.015547086,0.028337851,0.03831383,0.00520084,-0.02129332,-0.030128459,0.08321077,0.012300335,-0.010841018,0.06585791,0.07564347,-0.014012201,0.0219864,0.024407806,0.018285379,-0.033405956,-0.014197679,0.0049413345,0.027818406,-0.017254056,-0.06468122,-0.0005442572,0.073454276,0.007637572,-0.035824116,-0.039332885,-0.028318768,-0.06958024,0.009854748,-0.06006147,0.035201304,0.043476705,-0.041027788,0.022021953,-0.04632887,0.24392003,0.020170346,0.019151013,0.05403627,0.024689468,0.030407287,0.016020441,-8.817441e-05,-0.0023452404,-0.028631007,-0.024740525,0.0021452687,0.021436825,0.0128083145,-0.029773973,0.02551454,-0.031108968,0.030106371,-0.0170075,-0.039736357,-0.09154388,0.04288828,0.004344343,0.013551624,0.004244157,-0.014181481,-0.0068790405,-0.021359334,-7.3006355e-05,-0.044061817,0.0378672,-0.0065712132,0.0251264,-0.027339075,0.022393407,0.03530089,0.0027249474,-0.00028365798,0.010490535,0.020212162,0.017944816,-0.03296245,-0.0045789257,-0.018937932,-0.0134890815,0.01102221,0.0061229668,-0.023090871,0.037834574,-0.012784377,0.0054279002,-0.046061415,0.052373935,-0.03617102,-0.04343359,-0.006643531,-0.0055645443,0.017821003,0.001434519,-0.012170867,-0.027391594,0.01921985,0.005075558,0.027216963,-0.05563005,-0.026556944,0.035982165,0.044753492,-0.013880296,-0.033647235,0.010323997,-0.0054111728,-0.024056973,-0.017501261,-0.0071677007,0.037470553,-0.0053350106,0.049461816,0.012601737,-0.037672523,0.01612209,0.007049281,-0.026087929,0.00065176765,0.033360023,0.029648058,-0.06942947,0.027673854,-0.0045793713,0.019137332,9.202969e-05,0.029002372,0.0062395027,0.015321633,0.0023851597]', '{"page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "5b73077d71c4bc31364b34346145c47d9f3bcf3f3126bacc358c118d12c989f2", "canonical_url": "https://codeweft.in/"}', '2025-12-18 16:33:34.865201+00');
INSERT INTO public.rag_embeddings VALUES (195, '5c2228c1-c4a2-5bed-9468-464bd32df471', 'c61ec4c9-deaf-4ce6-ba24-9f479e96c614', NULL, NULL, 'CODEWEFT - AI Products', '[0.020984616,0.020641826,-0.023914564,-0.0027538533,-0.005709478,0.0060807,-0.032318126,-0.00065994414,-0.0043891063,0.013682403,-0.009729519,0.031480376,-0.020327764,-0.038411308,-0.0035287144,0.011091267,-0.0043089963,-0.028160388,-0.06498912,-0.007362497,0.042098373,-0.0023592294,-0.07632393,-0.026584195,-0.05260314,0.029138986,-0.0015227825,-0.038084973,0.09883699,0.04080866,-0.047509532,-0.03334926,0.03594976,-0.06413379,-0.033584706,-0.023317745,-0.01247457,0.044973247,-0.030368991,-0.07206629,-0.0059088687,-0.045755148,0.022937397,-0.053095695,-0.075304925,-0.00074212253,0.019174226,0.0012683846,-0.009828478,-0.04307324,-0.00029802698,0.026318261,0.042738434,-0.065868706,-0.030106826,-0.013172176,-0.0018339241,-0.04229487,-0.02466027,0.010552899,0.045586076,0.020882865,-0.008623331,-0.04756846,-0.017295511,0.0016270305,0.012360761,0.0065659555,0.028375395,0.016990745,0.0099597685,0.009724308,-0.0032090116,-0.04461543,-0.011604744,-0.013901931,-0.017387597,0.0015595712,-0.008180439,-0.008585309,-0.0060863425,0.042611722,-0.025353143,0.032787785,-0.019657476,-0.013855511,-0.0018541026,0.0036647357,-0.015044749,0.010630294,-0.050392453,0.020563236,0.0025500243,-0.00011967828,0.0010271905,0.019757414,0.006298535,0.02206917,-0.013859738,0.025640568,0.024084942,0.06205408,-0.02762437,0.02146814,-0.0058271307,0.01776338,0.01774599,-0.040481333,-0.029280515,-0.03166688,-0.01806003,-0.000642952,-0.020324409,0.014577583,0.024645235,0.016560048,-0.020265713,0.0033384522,-0.012398869,0.016108265,-0.014431609,0.012888915,-0.01745097,0.0016824636,-0.005828223,-0.06250564,0.00018718961,0.009945979,0.031688314,-0.0028297387,0.0023979077,-0.0075326255,-0.008694887,0.030763235,0.009449883,0.030582525,-0.029804897,0.016257975,-0.0063397833,0.014575793,0.041371092,-0.031175707,0.014289182,0.090634145,0.007918825,0.020930016,-0.009991941,-0.013272115,-0.041870378,-0.008281929,-0.028971806,0.0168099,-0.015908528,0.027897319,-0.005629284,-0.05802108,-0.015231121,0.035064615,0.050422817,0.026612919,0.024177715,0.0040152934,-0.02210287,0.034477677,-0.0561028,0.025533402,-0.018155321,0.0025834914,-0.025729215,-0.003163397,-0.0027797061,0.004821383,-0.02724362,-0.0071134483,0.021522572,0.025640823,0.05767584,0.020928351,0.030332787,0.0006804759,-0.036047317,-0.013244128,-0.003064137,0.045166034,-0.020525139,-0.0059348345,0.02942588,0.0006455086,0.0066642696,0.0024201963,0.03491388,0.045855045,-0.06597953,0.05502895,-0.058377318,0.013182981,0.0030022943,0.04519033,0.027193546,-0.024576562,-0.040521413,0.03764366,-0.016554171,-0.05713489,-0.024020653,0.0007142472,-0.0031287866,0.005158173,-0.054358255,-0.008275406,-0.0049664285,-0.022851354,-0.005981521,-0.059622772,0.027034527,0.0011181459,-0.048257012,0.031595927,-0.01926041,-0.0050009526,0.020519312,0.024414236,0.034893353,0.03859255,0.00011886741,0.024405656,-0.012609696,0.0657034,0.0073044966,0.03353733,0.02145461,0.057477925,0.008336368,0.04787216,-0.0050486876,0.032006767,0.003762686,0.037529405,0.023117557,0.0024392188,-0.02067106,-0.020363338,0.013250802,0.02303174,0.016864456,-0.021869458,0.015695278,-0.01107695,-0.0038271875,0.0018795206,-0.06777328,0.03780257,-0.010941231,0.012103698,-0.024791028,-0.0189712,0.014034605,0.024112234,-0.016095813,0.030651165,0.021870404,0.05434744,0.004739967,0.019297559,0.04651366,0.052530676,0.052637894,-0.008831105,-0.06794849,-0.042394355,-0.058754873,-0.06251855,-0.040671814,-0.021377595,-0.054312572,-0.01593112,-0.00048043457,-0.0048588235,0.02739693,-0.03679797,0.020092756,-0.017388765,-0.03289027,0.009686565,0.03396238,0.057385027,-0.04989463,0.00060845196,-0.0019757445,0.02613497,-0.019889465,0.020010052,0.012590468,-0.0354959,-0.013089298,0.01341653,-0.01675815,0.0027713408,-0.066574775,-0.03315438,-0.02088567,0.0051549687,0.0022850118,-0.008851974,-0.06582584,0.04428913,0.019502684,-0.03457474,0.054183695,0.022331119,-0.056046866,0.03607131,0.0063889194,0.022616362,-0.03200104,0.037104048,0.05274541,0.013765863,-0.06335864,-0.016149491,-0.05415384,0.056846417,-0.008654285,0.012470386,-0.018674208,0.00770239,-0.016580854,-0.110537216,0.012278532,-0.006689935,-0.06732013,-0.032126833,0.005094486,0.00969645,0.011441851,0.014476019,-0.013875777,-0.007836124,0.004234262,0.013645728,0.03844893,0.017701862,0.048221387,0.01932084,-0.0017863724,-0.029706415,0.026232911,-0.026803976,0.037532765,-0.01696833,-0.014449751,0.00535588,0.0062590516,-0.0023777909,0.011573538,0.036790736,-0.028415918,0.015672075,0.008451362,0.028409924,0.01895966,-0.0012967032,-0.0010341576,0.004219304,-0.03401384,-0.016404409,0.021787442,0.014911536,0.027385814,-0.06614381,-0.023538593,-0.0076262387,-0.037155863,0.04248049,0.004268215,-0.0401905,-0.011020317,0.030151857,0.044906463,-0.048987463,-0.045246378,0.022246044,0.04715411,0.029504083,-0.023678591,-0.00712248,-0.0052761785,0.02932251,-0.057293985,0.014556625,-0.02291011,-0.0028481293,-0.0082912,0.016330915,-0.019754639,-0.049016874,0.0033967167,-0.009530927,-0.0045121214,0.0134947905,0.024494076,0.04412567,0.025362907,0.041218404,-0.035506554,-0.014720964,0.0023949586,0.013675779,0.020151464,-0.019234452,-0.018507535,0.011907033,-0.01775748,0.029449953,-0.006261491,0.008179696,-0.025684476,0.011663502,0.004402537,0.056937147,0.015642082,0.018368302,-0.018485384,-0.0011980308,0.05029055,-0.04020777,0.0035121213,-0.050316688,-0.017886717,0.037707023,-0.02054735,0.0075221094,-0.028770259,-0.04200877,0.016204042,0.05665158,0.021895425,0.014096418,0.008310907,-0.029506397,0.023033453,-0.00852612,-0.017381463,0.009967391,0.0145850405,-0.027729461,0.014203325,0.0136056235,0.0064478666,-0.026787864,0.011642307,-0.053695552,0.000919787,-0.02678974,0.031269077,-0.013606233,0.025977451,-0.0027087384,0.033101648,0.03155808,-0.004059681,-0.0023861225,0.027243111,-0.05968687,-0.037190408,0.045735646,0.010724397,-0.010914339,0.03502774,-0.011491824,-0.018172264,0.015901705,-0.0005436053,-0.0073366333,-0.01583906,6.610712e-06,0.0004647268,-0.004073445,-0.054477874,-0.011162064,-0.030884609,0.0020535626,0.011851944,-0.022550063,-0.0021154217,-0.0427124,-0.027146801,0.02962518,-0.008277404,0.029977357,0.010152862,-0.028786056,0.053100307,-0.0039399955,-0.0072544524,-0.03317944,-0.019942444,-0.0026489277,0.04283855,0.004234794,0.051914606,-0.04263925,-0.03760489,-0.005789277,-0.016736345,0.007702568,-0.026004372,0.053407796,-0.0132552255,0.006393682,-0.029611414,0.0048399586,-0.06179021,0.0049992297,0.0034052082,0.02738133,0.0058798366,-0.033313643,-0.04669382,0.03370254,0.013901952,-0.047285683,-0.027449436,0.041521825,0.0047847503,0.04476713,0.03895183,0.0132281715,-0.03127909,-0.040016506,0.018101126,-0.04263154,0.0020051505,-0.0076257605,-0.03639992,-0.009150457,0.014643291,0.00594103,-0.050715785,-0.044101268,-0.023224985,0.008820341,-0.051142335,0.002497421,-0.03905664,0.003748286,0.027673835,-0.014708667,0.00600326,0.023068707,-0.010280165,0.03353929,0.020561036,0.025035687,-0.039280027,-0.041356653,0.028620934,-0.0071041067,0.00560904,-0.016911456,-0.041494608,0.027721457,-0.05445431,-0.020285312,-0.043292288,-0.007053035,-0.015336058,0.0045332685,0.04501441,0.011868569,0.009812886,-0.020590106,0.058154542,0.052118126,0.030523976,-0.0050748885,-0.052653667,-0.006764867,-0.04987531,0.0212202,-0.012864704,0.020906676,-0.025034059,-0.024637664,0.030775998,-0.023985088,0.042929985,0.07570903,-0.01338575,-0.0023380278,-0.012624558,0.0239799,0.015013189,-0.041337308,-9.36059e-05,0.031262856,0.011974389,0.00084394024,-0.022860352,-0.034845233,-0.02925438,0.027253741,0.051941432,-0.04041185,0.0333208,-0.017230606,-0.033227473,-0.03385085,0.03729182,-0.009493897,0.012010627,0.020774394,0.016278464,-0.009222384,0.030240634,-0.0041068317,-0.023999788,-0.0018239035,0.03389351,-0.014771401,-0.03326458,-0.0028821507,0.03157047,0.004904985,-0.045755513,0.0022340822,0.026392598,0.0037649963,-0.031285893,0.054248188,0.0077251415,0.01701074,0.00059433153,-0.01241299,-0.018561797,0.012629956,0.07680317,0.010660771,-0.054510165,0.009936639,0.017055165,-0.0025369148,-0.026359519,-0.022979941,-0.013350583,-0.033447567,-0.006784746,0.037757248,-0.00021882962,0.012430183,0.052472528,0.031184316,0.040343985,-0.014327465,0.010114282,0.013655752,-0.033292443,-0.04715187,-0.029336767,0.024206225,-0.033403922,0.0045803064,0.005905139,0.038138665,0.04980449,0.024299962,0.0034856817,-0.04442549,-0.021132905,-0.074195966,-0.024582567,0.030648049,-0.024994789,-0.013275365,0.012519029,-0.009788451,-0.03174664,-0.018358106,0.025318649,0.014622883,-0.026066246,-0.017720038,0.0038710944,-0.060024228,-0.02790122,0.03687822,0.024571827,-0.0027986567,3.107518e-05,-0.023309616,-0.025839625,0.02058954,0.04148593,-0.035291232,0.017925283,0.0077302554,-0.03467395,-0.043408576,0.025685022,-0.034914102,0.031950515,0.04678423,0.024074217,0.039962906,0.021843145,-0.015137089,-0.01940383,0.021004213,0.06483678,-0.021050371,0.032053474,-0.05217169,0.024216313,-0.010833428,0.010110157,0.04500609,-0.008795844,0.03509728,0.042224113,-0.03197,0.060106512,-0.012128936,0.004812311,-0.025124494,0.0003512221,-0.00380149,-0.030365257,0.04495919,-0.0017090496,0.02726374,-0.07357937,0.040347666,0.0075352467,-0.03508323,0.030761074,0.0029413274,-0.059486113,-0.022786139,-0.0170823,0.010266113,0.07824173,0.049339008,0.007534605,0.01612897,0.025985923,-0.05514353,-0.0011181447,-0.047054112,-0.005442638,0.032547057,-0.019284854,0.0148465885,-0.023203764,-0.009225577,-0.037514098,-0.023570795,0.016838774,0.012248599,0.024577036,-0.038286068,-0.0026471606,-0.08481423,-0.036104877,0.017962413,0.031915274,-0.03618224,-0.04420399,0.018252518,0.07482101,0.0024595167,0.0026345574,-0.03562133,-0.0081934165,0.00095841405,0.01042614,-0.042766754,0.042730395,-0.04457543,0.014790829,0.03262539,0.016150968,-0.048260126,0.042726938,0.018456068,0.019359834,0.017756544,0.023061154,0.020192493,-0.0036620663,-0.0026030166,-0.008361644,0.0023712846,0.0037808781,-0.012674175,0.02042267,0.04627993,0.03745675,0.057102136,-0.040991478,0.0279729,0.09059312,0.036948413,-0.0007749102,0.021288747,0.010613487,0.02828863,0.03355869,-0.031620014,0.030310404,-0.015370797,0.00063145603,-0.0020901705,0.013817621,-0.04392859,-0.004231217,-0.06614964,0.016030585,-0.004880594,-0.04758679,-0.032143053,-0.01604817,0.008677126,0.007241812,0.026933916,-0.008582798,0.020412477,0.030205823,0.01840705,-0.0049460377,0.008099351,0.00873741,-0.0027917123,-0.012885618,-0.01790742,0.013243225,0.023333233,-0.0024520862,-0.060837954,0.053279124,0.0022834141,-0.051800016,0.014255858,-0.022065962,-0.013431814,-0.030466186,-0.009761319,-0.035643976,-0.009711257,0.014791602,-0.01006664,-0.024687734,0.019517248,0.02085376,0.010607418,0.04763322,0.056335125,-0.040152993,0.040588375,0.06900409,-0.026385004,0.013738254,0.02823491,0.004669351,-0.043300517,-0.012212312,-0.024459457,-0.046212193,-0.027852643,-0.02301309,-0.008044031,0.026232133,0.0018035177,-0.020478977,-0.013139643,0.022482263,-0.03410325,0.0043927482,0.06784328,0.015484598,0.026887722,-0.037648097,0.010998501,-0.02209852,0.0018625027,-0.02919748,0.03273382,-0.02481511,0.0015669971,-0.010112452,0.015150967,-0.048922338,-0.03897541,-0.0039558816,-0.03510129,0.015547086,0.028337851,0.03831383,0.00520084,-0.02129332,-0.030128459,0.08321077,0.012300335,-0.010841018,0.06585791,0.07564347,-0.014012201,0.0219864,0.024407806,0.018285379,-0.033405956,-0.014197679,0.0049413345,0.027818406,-0.017254056,-0.06468122,-0.0005442572,0.073454276,0.007637572,-0.035824116,-0.039332885,-0.028318768,-0.06958024,0.009854748,-0.06006147,0.035201304,0.043476705,-0.041027788,0.022021953,-0.04632887,0.24392003,0.020170346,0.019151013,0.05403627,0.024689468,0.030407287,0.016020441,-8.817441e-05,-0.0023452404,-0.028631007,-0.024740525,0.0021452687,0.021436825,0.0128083145,-0.029773973,0.02551454,-0.031108968,0.030106371,-0.0170075,-0.039736357,-0.09154388,0.04288828,0.004344343,0.013551624,0.004244157,-0.014181481,-0.0068790405,-0.021359334,-7.3006355e-05,-0.044061817,0.0378672,-0.0065712132,0.0251264,-0.027339075,0.022393407,0.03530089,0.0027249474,-0.00028365798,0.010490535,0.020212162,0.017944816,-0.03296245,-0.0045789257,-0.018937932,-0.0134890815,0.01102221,0.0061229668,-0.023090871,0.037834574,-0.012784377,0.0054279002,-0.046061415,0.052373935,-0.03617102,-0.04343359,-0.006643531,-0.0055645443,0.017821003,0.001434519,-0.012170867,-0.027391594,0.01921985,0.005075558,0.027216963,-0.05563005,-0.026556944,0.035982165,0.044753492,-0.013880296,-0.033647235,0.010323997,-0.0054111728,-0.024056973,-0.017501261,-0.0071677007,0.037470553,-0.0053350106,0.049461816,0.012601737,-0.037672523,0.01612209,0.007049281,-0.026087929,0.00065176765,0.033360023,0.029648058,-0.06942947,0.027673854,-0.0045793713,0.019137332,9.202969e-05,0.029002372,0.0062395027,0.015321633,0.0023851597]', '{"page_title": "CODEWEFT - AI Products", "source_url": "https://codeweft.in/", "content_hash": "5b73077d71c4bc31364b34346145c47d9f3bcf3f3126bacc358c118d12c989f2", "canonical_url": "https://codeweft.in/"}', '2025-12-18 16:33:34.862062+00');


--
-- Data for Name: resource_schedules; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.resource_schedules VALUES ('ed8c991e-3f8f-4db8-b7bf-8934702ea330', 'dr_pranav', 0, NULL, '09:00:00', '17:00:00', 30, true, NULL, '2025-12-13 15:01:12.289917+00', '2025-12-13 15:01:12.289917+00');
INSERT INTO public.resource_schedules VALUES ('6768b205-0b65-48b0-be81-8fa998664331', 'dr_pranav', 1, NULL, '11:00:00', '17:02:00', 30, true, NULL, '2025-12-13 15:01:12.354724+00', '2025-12-13 15:01:12.354724+00');
INSERT INTO public.resource_schedules VALUES ('61584db5-8645-4966-8068-af02aeb4d8bc', 'dr_pranav', 2, NULL, '09:00:00', '17:00:00', 30, true, NULL, '2025-12-13 15:01:12.417831+00', '2025-12-13 15:01:12.417831+00');
INSERT INTO public.resource_schedules VALUES ('e4e3be41-bc95-4eed-82c5-6e45f586b2de', '6e0afeff-3c5a-4879-a312-93df601dda88', 0, NULL, '07:00:00', '10:00:00', 30, true, NULL, '2025-12-13 20:52:00.328265+00', '2025-12-13 20:52:00.328265+00');
INSERT INTO public.resource_schedules VALUES ('d839f031-18cc-4738-9e89-904b6994a237', '6e0afeff-3c5a-4879-a312-93df601dda88', 1, NULL, '07:00:00', '10:00:00', 30, true, NULL, '2025-12-13 20:52:12.047789+00', '2025-12-13 20:52:12.047789+00');
INSERT INTO public.resource_schedules VALUES ('cb4273f1-e875-42c3-99d9-f1227bc202ca', 'dr_pranav', 3, NULL, '07:00:00', '10:00:00', 5, true, NULL, '2025-12-15 15:12:46.555343+00', '2025-12-15 15:12:46.555343+00');
INSERT INTO public.resource_schedules VALUES ('d17093f3-87b2-42ef-897a-4fc93fb31ca0', '52a3e1b8-dd12-4924-abdd-bb279c4c1907', 3, NULL, '07:00:00', '10:00:00', 30, true, NULL, '2025-12-15 16:03:21.340063+00', '2025-12-15 16:03:21.340063+00');


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Name: booking_audit_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.booking_audit_logs_id_seq', 25, true);


--
-- Name: booking_notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.booking_notifications_id_seq', 20, true);


--
-- Name: bookings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.bookings_id_seq', 23, true);


--
-- Name: bot_appointments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.bot_appointments_id_seq', 1, false);


--
-- Name: conversation_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.conversation_history_id_seq', 462, true);


--
-- Name: leads_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.leads_id_seq', 20, true);


--
-- Name: rag_embeddings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.rag_embeddings_id_seq', 196, true);


--
-- Name: app_users app_users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_email_key UNIQUE (email);


--
-- Name: app_users app_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_pkey PRIMARY KEY (id);


--
-- Name: booking_audit_logs booking_audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_audit_logs
    ADD CONSTRAINT booking_audit_logs_pkey PRIMARY KEY (id);


--
-- Name: booking_notifications booking_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_notifications
    ADD CONSTRAINT booking_notifications_pkey PRIMARY KEY (id);


--
-- Name: booking_resources booking_resources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_resources
    ADD CONSTRAINT booking_resources_pkey PRIMARY KEY (id);


--
-- Name: bookings bookings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookings
    ADD CONSTRAINT bookings_pkey PRIMARY KEY (id);


--
-- Name: bot_appointments bot_appointments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_appointments
    ADD CONSTRAINT bot_appointments_pkey PRIMARY KEY (id);


--
-- Name: bot_booking_settings bot_booking_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_booking_settings
    ADD CONSTRAINT bot_booking_settings_pkey PRIMARY KEY (org_id, bot_id);


--
-- Name: bot_calendar_oauth bot_calendar_oauth_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_calendar_oauth
    ADD CONSTRAINT bot_calendar_oauth_pkey PRIMARY KEY (org_id, bot_id, provider);


--
-- Name: bot_calendar_settings bot_calendar_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_calendar_settings
    ADD CONSTRAINT bot_calendar_settings_pkey PRIMARY KEY (org_id, bot_id, provider);


--
-- Name: bot_usage_daily bot_usage_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_usage_daily
    ADD CONSTRAINT bot_usage_daily_pkey PRIMARY KEY (org_id, bot_id, day);


--
-- Name: chatbots chatbots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chatbots
    ADD CONSTRAINT chatbots_pkey PRIMARY KEY (id);


--
-- Name: conversation_history conversation_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_history
    ADD CONSTRAINT conversation_history_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: form_configurations form_configurations_bot_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_configurations
    ADD CONSTRAINT form_configurations_bot_id_key UNIQUE (bot_id);


--
-- Name: form_configurations form_configurations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_configurations
    ADD CONSTRAINT form_configurations_pkey PRIMARY KEY (id);


--
-- Name: form_fields form_fields_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_fields
    ADD CONSTRAINT form_fields_pkey PRIMARY KEY (id);


--
-- Name: form_templates form_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_templates
    ADD CONSTRAINT form_templates_pkey PRIMARY KEY (id);


--
-- Name: leads leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_pkey PRIMARY KEY (id);


--
-- Name: organization_users organization_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_users
    ADD CONSTRAINT organization_users_pkey PRIMARY KEY (org_id, user_id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: rag_embeddings rag_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_embeddings
    ADD CONSTRAINT rag_embeddings_pkey PRIMARY KEY (id);


--
-- Name: resource_schedules resource_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_schedules
    ADD CONSTRAINT resource_schedules_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_booking_resources_bot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_booking_resources_bot ON public.booking_resources USING btree (bot_id);


--
-- Name: idx_bookings_bot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookings_bot ON public.bookings USING btree (bot_id);


--
-- Name: idx_bookings_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookings_date ON public.bookings USING btree (booking_date);


--
-- Name: idx_bookings_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookings_resource ON public.bookings USING btree (resource_id);


--
-- Name: idx_conversation_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversation_session ON public.conversation_history USING btree (session_id, created_at);


--
-- Name: idx_form_configs_bot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form_configs_bot ON public.form_configurations USING btree (bot_id);


--
-- Name: idx_form_fields_config; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form_fields_config ON public.form_fields USING btree (form_config_id);


--
-- Name: idx_resource_schedules_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_resource_schedules_resource ON public.resource_schedules USING btree (resource_id);


--
-- Name: rag_embeddings_bot_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rag_embeddings_bot_idx ON public.rag_embeddings USING btree (bot_id);


--
-- Name: rag_embeddings_ivf_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rag_embeddings_ivf_idx ON public.rag_embeddings USING ivfflat (embedding extensions.vector_cosine_ops) WITH (lists='100');


--
-- Name: rag_embeddings_org_bot_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rag_embeddings_org_bot_idx ON public.rag_embeddings USING btree (org_id, bot_id);


--
-- Name: chatbots chatbots_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chatbots
    ADD CONSTRAINT chatbots_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: chatbots chatbots_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chatbots
    ADD CONSTRAINT chatbots_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_bot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES public.chatbots(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_users organization_users_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_users
    ADD CONSTRAINT organization_users_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_users organization_users_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_users
    ADD CONSTRAINT organization_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: rag_embeddings rag_embeddings_bot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_embeddings
    ADD CONSTRAINT rag_embeddings_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES public.chatbots(id) ON DELETE CASCADE;


--
-- Name: rag_embeddings rag_embeddings_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_embeddings
    ADD CONSTRAINT rag_embeddings_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: bot_appointments Users can see org appointments; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org appointments" ON public.bot_appointments USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = bot_appointments.org_id)))));


--
-- Name: booking_resources Users can see org booking resources; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org booking resources" ON public.booking_resources USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = booking_resources.org_id)))));


--
-- Name: bookings Users can see org bookings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org bookings" ON public.bookings USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = bookings.org_id)))));


--
-- Name: bot_booking_settings Users can see org bot booking settings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org bot booking settings" ON public.bot_booking_settings USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = bot_booking_settings.org_id)))));


--
-- Name: bot_calendar_oauth Users can see org bot calendar oauth; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org bot calendar oauth" ON public.bot_calendar_oauth USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = bot_calendar_oauth.org_id)))));


--
-- Name: bot_calendar_settings Users can see org bot calendar settings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org bot calendar settings" ON public.bot_calendar_settings USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = bot_calendar_settings.org_id)))));


--
-- Name: bot_usage_daily Users can see org bot usage daily; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org bot usage daily" ON public.bot_usage_daily USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = bot_usage_daily.org_id)))));


--
-- Name: form_configurations Users can see org form configurations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org form configurations" ON public.form_configurations USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = form_configurations.org_id)))));


--
-- Name: form_fields Users can see org form fields; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org form fields" ON public.form_fields USING ((EXISTS ( SELECT 1
   FROM public.form_configurations fc
  WHERE ((fc.id = form_fields.form_config_id) AND (EXISTS ( SELECT 1
           FROM public.app_users
          WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = fc.org_id))))))));


--
-- Name: leads Users can see org leads; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org leads" ON public.leads USING ((EXISTS ( SELECT 1
   FROM public.app_users
  WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = leads.org_id)))));


--
-- Name: resource_schedules Users can see org resource schedules; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see org resource schedules" ON public.resource_schedules USING ((EXISTS ( SELECT 1
   FROM public.booking_resources br
  WHERE ((br.id = resource_schedules.resource_id) AND (EXISTS ( SELECT 1
           FROM public.app_users
          WHERE ((app_users.id = (auth.uid())::text) AND (app_users.org_id = br.org_id))))))));


--
-- Name: form_templates Users can see public form templates; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see public form templates" ON public.form_templates FOR SELECT USING ((is_public = true));


--
-- Name: app_users Users can see their own data; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can see their own data" ON public.app_users FOR SELECT USING (((auth.uid())::text = id));


--
-- Name: app_users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.app_users ENABLE ROW LEVEL SECURITY;

--
-- Name: booking_audit_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.booking_audit_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: booking_notifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.booking_notifications ENABLE ROW LEVEL SECURITY;

--
-- Name: booking_resources; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.booking_resources ENABLE ROW LEVEL SECURITY;

--
-- Name: bookings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_appointments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_appointments ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_booking_settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_booking_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_calendar_oauth; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_calendar_oauth ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_calendar_settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_calendar_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_usage_daily; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_usage_daily ENABLE ROW LEVEL SECURITY;

--
-- Name: chatbots; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.chatbots ENABLE ROW LEVEL SECURITY;

--
-- Name: conversation_history; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.conversation_history ENABLE ROW LEVEL SECURITY;

--
-- Name: conversations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

--
-- Name: form_configurations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.form_configurations ENABLE ROW LEVEL SECURITY;

--
-- Name: form_fields; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.form_fields ENABLE ROW LEVEL SECURITY;

--
-- Name: form_templates; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.form_templates ENABLE ROW LEVEL SECURITY;

--
-- Name: leads; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;

--
-- Name: organizations org_members_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY org_members_select ON public.organizations FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.organization_users m
  WHERE ((m.org_id = organizations.id) AND (m.user_id = auth.uid())))));


--
-- Name: chatbots org_members_select_chatbots; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY org_members_select_chatbots ON public.chatbots FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.organization_users m
  WHERE ((m.org_id = m.org_id) AND (m.user_id = auth.uid())))));


--
-- Name: conversations org_members_select_conversations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY org_members_select_conversations ON public.conversations FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.organization_users m
  WHERE ((m.org_id = m.org_id) AND (m.user_id = auth.uid())))));


--
-- Name: rag_embeddings org_members_select_embeddings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY org_members_select_embeddings ON public.rag_embeddings FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.organization_users m
  WHERE ((m.org_id = m.org_id) AND (m.user_id = auth.uid())))));


--
-- Name: organization_users org_membership_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY org_membership_select ON public.organization_users FOR SELECT USING ((user_id = auth.uid()));


--
-- Name: organization_users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.organization_users ENABLE ROW LEVEL SECURITY;

--
-- Name: organizations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

--
-- Name: rag_embeddings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.rag_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: resource_schedules; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.resource_schedules ENABLE ROW LEVEL SECURITY;

--
-- Name: booking_audit_logs service_role_all_booking_audit; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY service_role_all_booking_audit ON public.booking_audit_logs USING (true);


--
-- Name: booking_notifications service_role_all_booking_notif; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY service_role_all_booking_notif ON public.booking_notifications USING (true);


--
-- Name: conversation_history service_role_all_conversation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY service_role_all_conversation ON public.conversation_history USING (true);


--
-- Name: users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
-- Name: users users_self_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_self_select ON public.users FOR SELECT USING ((id = auth.uid()));


--
-- PostgreSQL database dump complete
--

