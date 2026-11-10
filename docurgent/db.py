#!/usr/bin/env python3
"""
DocUrgent 24/7 — SQLite Database Management & Security Layer
Thread-safe, secure storage for Patients, Doctors, Consultations,
Prescriptions, Payments, WebRTC Signaling, and Compliance Audit Logs.
"""

import sqlite3
import os
import hashlib
import uuid
import datetime
import json
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "docurgent.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Security Constants
HASH_ITERATIONS = 100000
DEFAULT_CURRENCY = "INR"  # Supports INR (₹) and USD ($)
PLATFORM_COMMISSION_PERCENT = 15  # Doctor keeps 85%, platform 15%

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password: str, salt: bytes = None) -> tuple:
    if salt is None:
        salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, HASH_ITERATIONS)
    return hashed.hex(), salt.hex()

def verify_password(password: str, hashed_hex: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, hashed_hex)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # 1. Users Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        phone TEXT,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('patient', 'doctor', 'admin')),
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    # 2. Sessions Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # 3. Doctors Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id TEXT PRIMARY KEY,
        user_id TEXT UNIQUE,
        name TEXT NOT NULL,
        specialty TEXT NOT NULL,
        category TEXT NOT NULL,
        degrees TEXT NOT NULL,
        license_number TEXT NOT NULL,
        hospital TEXT NOT NULL,
        experience_years INTEGER NOT NULL,
        consultation_fee REAL NOT NULL,
        achievements TEXT,
        bio TEXT,
        avatar TEXT,
        certificate_url TEXT,
        verification_status TEXT NOT NULL DEFAULT 'pending_verification'
            CHECK(verification_status IN ('pending_verification', 'under_review', 'verified', 'rejected', 'suspended')),
        is_available INTEGER DEFAULT 1,
        response_time TEXT DEFAULT '< 30 sec',
        rating REAL DEFAULT 5.0,
        reviews_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # 4. Patients Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id TEXT PRIMARY KEY,
        user_id TEXT UNIQUE,
        name TEXT NOT NULL,
        age INTEGER,
        phone TEXT NOT NULL,
        emergency_contact TEXT,
        allergies TEXT,
        medical_history TEXT,
        consent_telehealth INTEGER DEFAULT 1,
        consent_data INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # 5. Consultations Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS consultations (
        id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        doctor_id TEXT,
        category TEXT NOT NULL,
        condition_desc TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'requested'
            CHECK(status IN ('safety_checked', 'requested', 'accepted', 'in_progress', 'completed', 'cancelled', 'rejected')),
        emergency_level TEXT DEFAULT 'urgent',
        fee REAL NOT NULL,
        currency TEXT DEFAULT 'INR',
        call_duration_seconds INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        cancellation_reason TEXT,
        payment_id TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id),
        FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    )
    """)

    # 6. Messages Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        consultation_id TEXT NOT NULL,
        sender_role TEXT NOT NULL CHECK(sender_role IN ('patient', 'doctor', 'system')),
        sender_id TEXT NOT NULL,
        text TEXT,
        photo_url TEXT,
        created_at TEXT NOT NULL,
        read_at TEXT,
        FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE
    )
    """)

    # 7. Prescriptions Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS prescriptions (
        id TEXT PRIMARY KEY,
        consultation_id TEXT UNIQUE NOT NULL,
        doctor_id TEXT NOT NULL,
        patient_id TEXT NOT NULL,
        clinical_assessment TEXT NOT NULL,
        diagnosis TEXT NOT NULL,
        first_aid_instructions TEXT,
        medications_json TEXT,
        follow_up_instructions TEXT,
        referral_hospital TEXT,
        is_signed INTEGER DEFAULT 0,
        signed_at TEXT,
        digital_signature_hash TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE,
        FOREIGN KEY(doctor_id) REFERENCES doctors(id),
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    )
    """)

    # 8. Payments Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        consultation_id TEXT NOT NULL,
        patient_id TEXT NOT NULL,
        doctor_id TEXT,
        amount_total REAL NOT NULL,
        doctor_payout REAL NOT NULL,
        platform_cut REAL NOT NULL,
        currency TEXT DEFAULT 'INR',
        transaction_ref TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending', 'completed', 'failed', 'refunded')),
        gateway_mode TEXT DEFAULT 'sandbox',
        gateway_payload TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(consultation_id) REFERENCES consultations(id)
    )
    """)

    # 9. Doctor Verification History Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS doctor_verifications (
        id TEXT PRIMARY KEY,
        doctor_id TEXT NOT NULL,
        admin_id TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT NOT NULL,
        review_notes TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
    )
    """)

    # 10. Audit Logs Table (Mandatory for Telehealth compliance)
    c.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        role TEXT,
        action TEXT NOT NULL,
        resource_type TEXT NOT NULL,
        resource_id TEXT,
        details TEXT,
        ip_address TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # 11. WebRTC Signaling Table (Thread-safe exchange between patient and doctor)
    c.execute("""
    CREATE TABLE IF NOT EXISTS webrtc_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT NOT NULL,
        sender_role TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        signal_data TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()

    # Seed Default Administrator
    c.execute("SELECT id FROM users WHERE email = 'admin@docurgent.org'")
    admin_row = c.fetchone()
    if not admin_row:
        admin_id = "user-admin-01"
        now = datetime.datetime.utcnow().isoformat()
        pwd_hash, salt = hash_password("DocAdmin2026!")
        c.execute("""
        INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 'admin', 1, ?)
        """, (admin_id, "admin@docurgent.org", "+919876543210", pwd_hash, salt, now))
        log_audit(conn, admin_id, 'admin', 'SYSTEM_INIT', 'users', admin_id, 'Default administrator account seeded')
        conn.commit()

    # Seed Initial Verified Specialists (if table empty)
    c.execute("SELECT COUNT(*) FROM doctors")
    if c.fetchone()[0] == 0:
        seed_doctors(conn)

    conn.close()

def log_audit(conn, user_id, role, action, resource_type, resource_id=None, details=None, ip="127.0.0.1"):
    now = datetime.datetime.utcnow().isoformat()
    log_id = str(uuid.uuid4())
    conn.execute("""
    INSERT INTO audit_logs (id, user_id, role, action, resource_type, resource_id, details, ip_address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (log_id, user_id, role, action, resource_type, resource_id, details, ip, now))

def seed_doctors(conn):
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    INITIAL_DOCS = [
      {
        'id': 'doc-eye-1',
        'email': 'sarah.jenkins@docurgent.org',
        'name': 'Dr. Sarah Jenkins, MD',
        'avatar': 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=600',
        'specialty': 'Ophthalmology & Eye Trauma',
        'category': 'eye',
        'degrees': 'MBBS, MS (Ophthalmology), Fellow in Corneal Trauma & Reconstruction',
        'license_number': 'MED-OPHTH-88219',
        'hospital': 'Metro Eye & Emergency Trauma Center',
        'experience_years': 12,
        'consultation_fee': 800.0,  # ₹800 (Doctor keeps ₹680, Platform ₹120)
        'achievements': 'Over 4,500 emergency eye trauma surgeries; Board Certified in Ophthalmic Emergencies; Member of All India Ophthalmological Society',
        'bio': 'Specialist in rapid visual triage, chemical splashes, corneal abrasions, foreign body removal, and acute ocular trauma.',
        'verification_status': 'verified',
        'is_available': 1,
        'response_time': '< 30 sec',
        'rating': 4.98,
        'reviews_count': 382
      },
      {
        'id': 'doc-ortho-1',
        'email': 'rajesh.mehta@docurgent.org',
        'name': 'Dr. Rajesh Mehta, MS, FRCS',
        'avatar': 'https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=600',
        'specialty': 'Orthopedic Trauma & Fracture Care',
        'category': 'stairs',
        'degrees': 'MBBS, MS (Orthopedics), M.Ch (Trauma Surgery), FRCS (Glasgow)',
        'license_number': 'ORTHO-REG-449102',
        'hospital': 'Apex Trauma & Joint Care Hospital',
        'experience_years': 16,
        'consultation_fee': 1000.0, # ₹1,000 (Doctor keeps ₹850, Platform ₹150)
        'achievements': 'Former Chief of Trauma Surgery; Handled 5,200+ accident & fall cases; Specialist in limb immobilization & fracture triage',
        'bio': 'Emergency guidance for stair falls, bone fractures, acute sprains, joint dislocations, and post-accident immobilization advice.',
        'verification_status': 'verified',
        'is_available': 1,
        'response_time': '< 45 sec',
        'rating': 4.95,
        'reviews_count': 512
      },
      {
        'id': 'doc-er-1',
        'email': 'elena.rostova@docurgent.org',
        'name': 'Dr. Elena Rostova, MD',
        'avatar': 'https://images.unsplash.com/photo-1594824813583-02f896b7972b?auto=format&fit=crop&q=80&w=600',
        'specialty': 'Emergency & Critical Care Medicine',
        'category': 'emergency',
        'degrees': 'MD (Emergency Medicine), Board Certified Emergency Physician, ACLS / ATLS Director',
        'license_number': 'EM-MED-774019',
        'hospital': 'St. Jude Level-1 Emergency Hospital',
        'experience_years': 14,
        'consultation_fee': 900.0,
        'achievements': 'Over 6,000 emergency admissions managed; Emergency Department Lead; Keynote Speaker on Pre-Hospital Tele-Triage',
        'bio': 'Immediate guidance for severe cuts, heavy bleeding, concussion from falls, acute burns, and emergency stabilization advice.',
        'verification_status': 'verified',
        'is_available': 1,
        'response_time': '< 25 sec',
        'rating': 4.99,
        'reviews_count': 640
      },
      {
        'id': 'doc-peds-1',
        'email': 'david.kim@docurgent.org',
        'name': 'Dr. David Kim, MD, FAAP',
        'avatar': 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=600',
        'specialty': 'Pediatric Emergency & Urgent Care',
        'category': 'pediatric',
        'degrees': 'MD (Pediatrics), Fellowship in Pediatric Emergency Medicine (CHOP)',
        'license_number': 'PED-EM-302194',
        'hospital': "Children's Acute Medical Pavilion",
        'experience_years': 10,
        'consultation_fee': 750.0,
        'achievements': 'Author of Parent Guide to Home First-Aid; Handled 3,000+ pediatric accidents and acute emergencies',
        'bio': 'Calm, rapid triage for children and infants after falls from beds or stairs, accidental ingestions, high fever, and sudden cuts.',
        'verification_status': 'verified',
        'is_available': 1,
        'response_time': '< 35 sec',
        'rating': 4.97,
        'reviews_count': 290
      },
      {
        'id': 'doc-burns-1',
        'email': 'amara.okafor@docurgent.org',
        'name': 'Dr. Amara Okafor, MD',
        'avatar': 'https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&q=80&w=600',
        'specialty': 'Burns, Scalds & Wound Trauma',
        'category': 'burns',
        'degrees': 'MBBS, MD (Dermatological Surgery & Wound Care)',
        'license_number': 'WOUND-CARE-661204',
        'hospital': 'University Burn & Acute Wound Center',
        'experience_years': 11,
        'consultation_fee': 850.0,
        'achievements': 'Pioneered rapid tele-triage for thermal and chemical burns; Treated 2,800+ scald and burn emergencies',
        'bio': 'Emergency first-aid for boiling liquid scalds, fire burns, chemical contact, deep abrasions, and sterile dressing protocol.',
        'verification_status': 'verified',
        'is_available': 1,
        'response_time': '< 40 sec',
        'rating': 4.94,
        'reviews_count': 215
      },
      {
        'id': 'doc-pending-demo',
        'email': 'vikram.patel@docurgent.org',
        'name': 'Dr. Vikram Patel, MS',
        'avatar': 'https://images.unsplash.com/photo-1537368910025-700350fe46c7?auto=format&fit=crop&q=80&w=600',
        'specialty': 'General Surgery & Acute Trauma',
        'category': 'general',
        'degrees': 'MBBS, MS (General Surgery)',
        'license_number': 'SURG-LIC-119283',
        'hospital': 'Metro General Hospital',
        'experience_years': 8,
        'consultation_fee': 600.0,
        'achievements': 'Handled 1,800+ acute surgical and trauma cases',
        'bio': 'Trauma surgery specialist evaluating wound closure urgency and internal trauma risk.',
        'verification_status': 'pending_verification', # Real demonstration of pending verification!
        'is_available': 1,
        'response_time': 'Pending Approval',
        'rating': 4.90,
        'reviews_count': 12
      }
    ]

    for d in INITIAL_DOCS:
        uid = f"user-{d['id']}"
        pwd_hash, salt = hash_password("DoctorPass123!")
        c.execute("""
        INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 'doctor', 1, ?)
        """, (uid, d['email'], "+919876500000", pwd_hash, salt, now))

        c.execute("""
        INSERT INTO doctors (
            id, user_id, name, specialty, category, degrees, license_number, hospital,
            experience_years, consultation_fee, achievements, bio, avatar, certificate_url,
            verification_status, is_available, response_time, rating, reviews_count,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            d['id'], uid, d['name'], d['specialty'], d['category'], d['degrees'],
            d['license_number'], d['hospital'], d['experience_years'], d['consultation_fee'],
            d['achievements'], d['bio'], d['avatar'], 'Medical_Board_Certification_Verified.pdf',
            d['verification_status'], d['is_available'], d['response_time'], d['rating'],
            d['reviews_count'], now, now
        ))

    conn.commit()

# Run database setup
if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
