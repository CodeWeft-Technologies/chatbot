-- ============================================
-- Railway Database Migration Script
-- Complete schema setup for chatbot application
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- Core Tables
-- ============================================

-- Organizations table
CREATE TABLE IF NOT EXISTS organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users table (app_users to avoid conflicts with system tables)
CREATE TABLE IF NOT EXISTS app_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  display_name TEXT,
  password_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Organization users mapping
CREATE TABLE IF NOT EXISTS organization_users (
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES app_users(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('owner','admin','member')) NOT NULL DEFAULT 'member',
  PRIMARY KEY (org_id, user_id)
);

-- Chatbots table
CREATE TABLE IF NOT EXISTS chatbots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  behavior TEXT CHECK (behavior IN ('sales','support','appointment')) NOT NULL DEFAULT 'support',
  system_prompt TEXT,
  temperature REAL NOT NULL DEFAULT 0.2,
  created_by UUID REFERENCES app_users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================
-- RAG and Embeddings
-- ============================================

-- RAG embeddings table (using pgvector extension)
CREATE TABLE IF NOT EXISTS rag_embeddings (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  bot_id UUID REFERENCES chatbots(id) ON DELETE CASCADE,
  doc_id UUID,
  chunk_id INT,
  content TEXT NOT NULL,
  embedding VECTOR(1024) NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for embeddings
CREATE INDEX IF NOT EXISTS rag_embeddings_bot_idx ON rag_embeddings (bot_id);
CREATE INDEX IF NOT EXISTS rag_embeddings_org_bot_idx ON rag_embeddings (org_id, bot_id);
CREATE INDEX IF NOT EXISTS rag_embeddings_ivf_idx ON rag_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);

-- ============================================
-- Conversations
-- ============================================

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  bot_id UUID REFERENCES chatbots(id) ON DELETE CASCADE,
  external_user_id TEXT,
  last_user_message TEXT,
  last_bot_message TEXT,
  messages JSONB DEFAULT '[]'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Conversation history table
CREATE TABLE IF NOT EXISTS conversation_history (
  id BIGSERIAL PRIMARY KEY,
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL,
  session_id TEXT,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversation_history(session_id);

-- ============================================
-- Leads Management
-- ============================================

CREATE TABLE IF NOT EXISTS leads (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  bot_id UUID REFERENCES chatbots(id) ON DELETE CASCADE,
  name TEXT,
  email TEXT,
  phone TEXT,
  company TEXT,
  job_title TEXT,
  interest_level TEXT,
  notes TEXT,
  form_data JSONB,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================
-- Dynamic Forms System
-- ============================================

-- Form configurations
CREATE TABLE IF NOT EXISTS form_configurations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  bot_id UUID REFERENCES chatbots(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  industry TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(bot_id)
);

-- Form fields
CREATE TABLE IF NOT EXISTS form_fields (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  form_config_id UUID REFERENCES form_configurations(id) ON DELETE CASCADE,
  field_name TEXT NOT NULL,
  field_label TEXT NOT NULL,
  field_type TEXT CHECK (field_type IN ('text','email','phone','number','select','multiselect','date','time','datetime','textarea','checkbox','radio')) NOT NULL,
  field_order INT NOT NULL DEFAULT 0,
  is_required BOOLEAN NOT NULL DEFAULT FALSE,
  placeholder TEXT,
  help_text TEXT,
  validation_rules JSONB,
  options JSONB,
  default_value TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Form field dependencies
CREATE TABLE IF NOT EXISTS form_field_dependencies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  field_id UUID REFERENCES form_fields(id) ON DELETE CASCADE,
  depends_on_field_id UUID REFERENCES form_fields(id) ON DELETE CASCADE,
  depends_on_value JSONB NOT NULL,
  action TEXT CHECK (action IN ('show','hide','require','disable')) NOT NULL DEFAULT 'show',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Form templates
CREATE TABLE IF NOT EXISTS form_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  industry TEXT NOT NULL,
  description TEXT,
  template_data JSONB NOT NULL,
  is_public BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_form_configs_bot ON form_configurations(bot_id);
CREATE INDEX IF NOT EXISTS idx_form_fields_config ON form_fields(form_config_id);

-- ============================================
-- Booking Resources
-- ============================================

-- Booking resources (doctors, staff, rooms, equipment)
CREATE TABLE IF NOT EXISTS booking_resources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  bot_id UUID REFERENCES chatbots(id) ON DELETE CASCADE,
  resource_type TEXT NOT NULL,
  resource_name TEXT NOT NULL,
  resource_code TEXT,
  description TEXT,
  capacity_per_slot INT NOT NULL DEFAULT 1,
  metadata JSONB,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Resource schedules
CREATE TABLE IF NOT EXISTS resource_schedules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_id UUID REFERENCES booking_resources(id) ON DELETE CASCADE,
  day_of_week INT CHECK (day_of_week BETWEEN 0 AND 6),
  specific_date DATE,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  slot_duration_minutes INT NOT NULL DEFAULT 30,
  is_available BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK ((day_of_week IS NOT NULL AND specific_date IS NULL) OR (day_of_week IS NULL AND specific_date IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_booking_resources_bot ON booking_resources(bot_id);
CREATE INDEX IF NOT EXISTS idx_resource_schedules_resource ON resource_schedules(resource_id);

-- ============================================
-- Bookings
-- ============================================

-- Bookings table
CREATE TABLE IF NOT EXISTS bookings (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  bot_id UUID REFERENCES chatbots(id) ON DELETE CASCADE,
  form_config_id UUID REFERENCES form_configurations(id),
  
  -- Standard fields
  customer_name TEXT NOT NULL,
  customer_email TEXT NOT NULL,
  customer_phone TEXT,
  
  -- Booking details
  booking_date DATE NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  
  -- Resource assignment
  resource_id UUID REFERENCES booking_resources(id),
  resource_name TEXT,
  
  -- Dynamic form data
  form_data JSONB NOT NULL DEFAULT '{}'::JSONB,
  
  -- Status management
  status TEXT CHECK (status IN ('pending','confirmed','cancelled','completed','no_show')) NOT NULL DEFAULT 'pending',
  cancellation_reason TEXT,
  
  -- External calendar integration
  calendar_event_id TEXT,
  
  -- Metadata
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  confirmed_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bookings_bot ON bookings(bot_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_resource ON bookings(resource_id);

-- ============================================
-- Bot Appointments (Legacy support)
-- ============================================

CREATE TABLE IF NOT EXISTS bot_appointments (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL,
  customer_name TEXT NOT NULL,
  customer_email TEXT NOT NULL,
  customer_phone TEXT,
  appointment_date DATE NOT NULL,
  appointment_time TIME NOT NULL,
  duration_minutes INT NOT NULL DEFAULT 30,
  status TEXT NOT NULL DEFAULT 'pending',
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  external_event_id TEXT,
  timezone TEXT DEFAULT 'UTC'
);

-- ============================================
-- Calendar Integration
-- ============================================

CREATE TABLE IF NOT EXISTS bot_calendar_oauth (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL,
  provider TEXT NOT NULL,
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  token_expiry TIMESTAMPTZ,
  scope TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_calendar_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL,
  calendar_id TEXT,
  calendar_name TEXT,
  sync_enabled BOOLEAN DEFAULT TRUE,
  auto_confirm BOOLEAN DEFAULT FALSE,
  buffer_minutes INT DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_booking_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL UNIQUE,
  enabled BOOLEAN DEFAULT FALSE,
  min_notice_hours INT DEFAULT 2,
  max_days_advance INT DEFAULT 30,
  slot_duration_minutes INT DEFAULT 30,
  slots_per_day INT DEFAULT 10,
  timezone TEXT DEFAULT 'UTC',
  working_hours JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================
-- Audit and Notifications
-- ============================================

-- Booking audit logs
CREATE TABLE IF NOT EXISTS booking_audit_logs (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL,
  appointment_id INT NOT NULL,
  action TEXT NOT NULL,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Booking notifications
CREATE TABLE IF NOT EXISTS booking_notifications (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL,
  appointment_id INT NOT NULL,
  notification_type TEXT NOT NULL,
  recipient_email TEXT NOT NULL,
  subject TEXT,
  body TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================
-- Usage Tracking
-- ============================================

CREATE TABLE IF NOT EXISTS bot_usage_daily (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  bot_id UUID NOT NULL,
  usage_date DATE NOT NULL,
  messages_sent INT DEFAULT 0,
  messages_received INT DEFAULT 0,
  unique_users INT DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(bot_id, usage_date)
);

-- ============================================
-- Functions for Capacity Checking
-- ============================================

-- Function to check resource capacity
CREATE OR REPLACE FUNCTION check_resource_capacity(
  p_resource_id UUID,
  p_booking_date DATE,
  p_start_time TIME,
  p_end_time TIME
) RETURNS BOOLEAN AS $$
DECLARE
  v_capacity INT;
  v_booked_count INT;
BEGIN
  -- Get resource capacity
  SELECT capacity_per_slot INTO v_capacity
  FROM booking_resources
  WHERE id = p_resource_id;
  
  -- Count existing bookings for this time slot
  SELECT COUNT(*) INTO v_booked_count
  FROM bookings
  WHERE resource_id = p_resource_id
    AND booking_date = p_booking_date
    AND status NOT IN ('cancelled', 'rejected')
    AND (
      (start_time <= p_start_time AND end_time > p_start_time) OR
      (start_time < p_end_time AND end_time >= p_end_time) OR
      (start_time >= p_start_time AND end_time <= p_end_time)
    );
  
  RETURN v_booked_count < v_capacity;
END;
$$ LANGUAGE plpgsql;

-- Function to get available slots for a resource
CREATE OR REPLACE FUNCTION get_available_slots(
  p_resource_id UUID,
  p_date DATE
) RETURNS TABLE(slot_start TIME, slot_end TIME, available_capacity INT) AS $$
DECLARE
  v_schedule RECORD;
  v_slot_start TIME;
  v_slot_end TIME;
  v_capacity INT;
  v_booked INT;
BEGIN
  -- Get resource capacity
  SELECT capacity_per_slot INTO v_capacity FROM booking_resources WHERE id = p_resource_id;
  
  -- Get schedule for the resource
  FOR v_schedule IN
    SELECT start_time, end_time, slot_duration_minutes
    FROM resource_schedules
    WHERE resource_id = p_resource_id
      AND is_available = TRUE
      AND (
        (day_of_week = EXTRACT(DOW FROM p_date) AND specific_date IS NULL) OR
        specific_date = p_date
      )
  LOOP
    v_slot_start := v_schedule.start_time;
    
    -- Generate time slots
    WHILE v_slot_start < v_schedule.end_time LOOP
      v_slot_end := v_slot_start + (v_schedule.slot_duration_minutes || ' minutes')::INTERVAL;
      
      IF v_slot_end <= v_schedule.end_time THEN
        SELECT COUNT(*) INTO v_booked
        FROM bookings
        WHERE resource_id = p_resource_id
          AND booking_date = p_date
          AND status NOT IN ('cancelled', 'rejected')
          AND (
            (start_time <= v_slot_start AND end_time > v_slot_start) OR
            (start_time < v_slot_end AND end_time >= v_slot_end) OR
            (start_time >= v_slot_start AND end_time <= v_slot_end)
          );
        
        slot_start := v_slot_start;
        slot_end := v_slot_end;
        available_capacity := v_capacity - COALESCE(v_booked, 0);
        
        IF available_capacity > 0 THEN
          RETURN NEXT;
        END IF;
      END IF;
      
      v_slot_start := v_slot_end;
    END LOOP;
  END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Insert Default Form Templates
-- ============================================

INSERT INTO form_templates (name, industry, description, template_data) VALUES
('Healthcare - Doctor Appointment', 'healthcare', 'Standard medical appointment booking form', 
'{
  "fields": [
    {"field_name": "appointment_type", "field_label": "Appointment Type", "field_type": "select", "field_order": 1, "is_required": true, "options": [
      {"value": "consultation", "label": "General Consultation"},
      {"value": "followup", "label": "Follow-up Visit"},
      {"value": "emergency", "label": "Emergency"}
    ]},
    {"field_name": "doctor", "field_label": "Select Doctor", "field_type": "select", "field_order": 2, "is_required": true, "options": []},
    {"field_name": "department", "field_label": "Department", "field_type": "select", "field_order": 3, "is_required": true, "options": [
      {"value": "cardiology", "label": "Cardiology"},
      {"value": "neurology", "label": "Neurology"},
      {"value": "pediatrics", "label": "Pediatrics"},
      {"value": "general", "label": "General Medicine"}
    ]},
    {"field_name": "symptoms", "field_label": "Symptoms", "field_type": "textarea", "field_order": 4, "is_required": false, "placeholder": "Describe your symptoms"},
    {"field_name": "insurance", "field_label": "Insurance Provider", "field_type": "text", "field_order": 5, "is_required": false},
    {"field_name": "first_visit", "field_label": "Is this your first visit?", "field_type": "checkbox", "field_order": 6, "is_required": false}
  ]
}'::JSONB),

('Salon - Beauty Appointment', 'salon', 'Beauty salon and spa booking form',
'{
  "fields": [
    {"field_name": "service", "field_label": "Service Type", "field_type": "select", "field_order": 1, "is_required": true, "options": [
      {"value": "haircut", "label": "Haircut"},
      {"value": "coloring", "label": "Hair Coloring"},
      {"value": "manicure", "label": "Manicure"},
      {"value": "pedicure", "label": "Pedicure"},
      {"value": "facial", "label": "Facial"},
      {"value": "massage", "label": "Massage"}
    ]},
    {"field_name": "stylist", "field_label": "Preferred Stylist", "field_type": "select", "field_order": 2, "is_required": false, "options": []},
    {"field_name": "duration", "field_label": "Estimated Duration", "field_type": "select", "field_order": 3, "is_required": true, "options": [
      {"value": "30", "label": "30 minutes"},
      {"value": "60", "label": "1 hour"},
      {"value": "90", "label": "1.5 hours"},
      {"value": "120", "label": "2 hours"}
    ]},
    {"field_name": "special_requests", "field_label": "Special Requests", "field_type": "textarea", "field_order": 4, "is_required": false}
  ]
}'::JSONB),

('Consulting - Meeting', 'consulting', 'Professional consulting meeting booking',
'{
  "fields": [
    {"field_name": "meeting_type", "field_label": "Meeting Type", "field_type": "select", "field_order": 1, "is_required": true, "options": [
      {"value": "initial", "label": "Initial Consultation"},
      {"value": "followup", "label": "Follow-up Meeting"},
      {"value": "strategy", "label": "Strategy Session"}
    ]},
    {"field_name": "consultant", "field_label": "Consultant", "field_type": "select", "field_order": 2, "is_required": true, "options": []},
    {"field_name": "meeting_format", "field_label": "Meeting Format", "field_type": "radio", "field_order": 3, "is_required": true, "options": [
      {"value": "in_person", "label": "In Person"},
      {"value": "video", "label": "Video Call"},
      {"value": "phone", "label": "Phone Call"}
    ]},
    {"field_name": "topics", "field_label": "Topics to Discuss", "field_type": "textarea", "field_order": 4, "is_required": true, "placeholder": "What would you like to discuss?"}
  ]
}'::JSONB),

('Education - Tutoring Session', 'education', 'Tutoring or educational session booking',
'{
  "fields": [
    {"field_name": "subject", "field_label": "Subject", "field_type": "select", "field_order": 1, "is_required": true, "options": [
      {"value": "math", "label": "Mathematics"},
      {"value": "science", "label": "Science"},
      {"value": "english", "label": "English"},
      {"value": "history", "label": "History"},
      {"value": "coding", "label": "Programming/Coding"}
    ]},
    {"field_name": "tutor", "field_label": "Preferred Tutor", "field_type": "select", "field_order": 2, "is_required": false, "options": []},
    {"field_name": "grade_level", "field_label": "Grade Level", "field_type": "select", "field_order": 3, "is_required": true, "options": [
      {"value": "elementary", "label": "Elementary (K-5)"},
      {"value": "middle", "label": "Middle School (6-8)"},
      {"value": "high", "label": "High School (9-12)"},
      {"value": "college", "label": "College/University"}
    ]},
    {"field_name": "learning_goals", "field_label": "Learning Goals", "field_type": "textarea", "field_order": 4, "is_required": false}
  ]
}'::JSONB)
ON CONFLICT DO NOTHING;

-- ============================================
-- Migration Complete
-- ============================================
