-- ==============================================================================
-- DocUrgent 24/7 — Production PostgreSQL & Supabase Database Schema
-- HIPAA & Telemedicine Regulatory Compliant Schema with Row-Level Security (RLS)
-- ==============================================================================

-- Enable required cryptographic extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. User Roles Enum
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('patient', 'doctor', 'admin', 'super_admin');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Doctor Verification Status Enum
DO $$ BEGIN
    CREATE TYPE verification_status_enum AS ENUM ('pending_verification', 'under_review', 'verified', 'rejected', 'suspended');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 3. Consultation Status Enum
DO $$ BEGIN
    CREATE TYPE consultation_status_enum AS ENUM ('safety_checked', 'requested', 'accepted', 'in_progress', 'completed', 'cancelled', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 4. Payment Status Enum
DO $$ BEGIN
    CREATE TYPE payment_status_enum AS ENUM ('pending', 'completed', 'failed', 'refunded');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ==============================================================================
-- TABLES DEFINITION
-- ==============================================================================

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE,
    phone TEXT,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'patient',
    is_active BOOLEAN DEFAULT TRUE,
    is_email_verified BOOLEAN DEFAULT FALSE,
    mfa_secret TEXT,
    mfa_enabled BOOLEAN DEFAULT FALSE,
    recovery_code_hash JSONB,
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Sessions Table
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role user_role NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Doctors Profile Table
CREATE TABLE IF NOT EXISTS doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    category TEXT NOT NULL,
    degrees TEXT NOT NULL,
    license_number TEXT NOT NULL UNIQUE,
    hospital TEXT NOT NULL,
    experience_years INT NOT NULL DEFAULT 5,
    consultation_fee NUMERIC(10,2) NOT NULL DEFAULT 800.00,
    achievements TEXT,
    bio TEXT,
    avatar TEXT,
    certificate_url TEXT,
    verification_status verification_status_enum NOT NULL DEFAULT 'pending_verification',
    is_available BOOLEAN DEFAULT TRUE,
    response_time TEXT DEFAULT '< 30 sec',
    rating NUMERIC(3,2) DEFAULT 5.0,
    reviews_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Patients Profile Table
CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    age INT,
    phone TEXT NOT NULL,
    emergency_contact TEXT,
    allergies TEXT,
    medical_history TEXT,
    consent_telehealth BOOLEAN DEFAULT TRUE,
    consent_data BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Consultations Table
CREATE TABLE IF NOT EXISTS consultations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id UUID REFERENCES doctors(id),
    category TEXT NOT NULL,
    condition_desc TEXT NOT NULL,
    status consultation_status_enum NOT NULL DEFAULT 'requested',
    emergency_level TEXT DEFAULT 'urgent',
    fee NUMERIC(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'INR',
    call_duration_seconds INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancellation_reason TEXT,
    payment_id UUID
);

-- 6. Messages Table (Real-Time Consultation Chat)
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID NOT NULL REFERENCES consultations(id) ON DELETE CASCADE,
    sender_role user_role NOT NULL,
    sender_id UUID NOT NULL,
    text TEXT,
    photo_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at TIMESTAMPTZ
);

-- 7. Prescriptions Table
CREATE TABLE IF NOT EXISTS prescriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID UNIQUE NOT NULL REFERENCES consultations(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    patient_id UUID NOT NULL REFERENCES patients(id),
    clinical_assessment TEXT NOT NULL,
    diagnosis TEXT NOT NULL,
    first_aid_instructions TEXT,
    medications_json JSONB,
    follow_up_instructions TEXT,
    referral_hospital TEXT,
    is_signed BOOLEAN DEFAULT FALSE,
    signed_at TIMESTAMPTZ,
    digital_signature_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Payments Table
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID NOT NULL REFERENCES consultations(id),
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id UUID REFERENCES doctors(id),
    amount_total NUMERIC(10,2) NOT NULL,
    doctor_payout NUMERIC(10,2) NOT NULL,
    platform_cut NUMERIC(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'INR',
    transaction_ref TEXT UNIQUE NOT NULL,
    status payment_status_enum NOT NULL DEFAULT 'pending',
    gateway_mode VARCHAR(20) DEFAULT 'sandbox',
    gateway_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. Doctor Verifications Audit Table
CREATE TABLE IF NOT EXISTS doctor_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    admin_id UUID NOT NULL REFERENCES users(id),
    old_status verification_status_enum,
    new_status verification_status_enum NOT NULL,
    review_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. Audit Logs Table (Mandatory for Telehealth Regulatory Compliance)
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    role TEXT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    details TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 11. System Settings Table
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by UUID
);

-- 12. Doctor Payouts Table
CREATE TABLE IF NOT EXISTS doctor_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    amount NUMERIC(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'INR',
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending',
    payout_method TEXT,
    reference_id TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES FOR SUPABASE
-- ==============================================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctors ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE consultations ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Verified doctors are visible to all authenticated patients
CREATE POLICY "Public read verified doctors" ON doctors
    FOR SELECT USING (verification_status = 'verified');

-- Patients can only access their own consultations
CREATE POLICY "Patients access own consultations" ON consultations
    FOR ALL USING (patient_id IN (SELECT id FROM patients WHERE user_id = auth.uid()));

-- Doctors can only access consultations assigned to them
CREATE POLICY "Doctors access assigned consultations" ON consultations
    FOR ALL USING (doctor_id IN (SELECT id FROM doctors WHERE user_id = auth.uid()));

-- Administrators have full platform access
CREATE POLICY "Admins full access" ON audit_logs
    FOR ALL USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'super_admin')));
