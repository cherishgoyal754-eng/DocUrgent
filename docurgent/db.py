#!/usr/bin/env python3
"""
DocUrgent 24/7 — SQLite Database Management & Security Layer
Thread-safe, secure storage for Patients, Doctors, Consultations,
Prescriptions, Payments, WebRTC Signaling, and Compliance Audit Logs.
Enhanced with Super Admin ownership, Multi-Factor Authentication (RFC 6238 TOTP),
System Settings, Signed File Storage URLs, and Disaster Recovery Hooks.
"""

import sqlite3
import os
import hashlib
import uuid
import datetime
import json
import secrets
import base64
import struct
import hmac
import time
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
RUNTIME_DIR = os.path.join("/tmp", "docurgent") if IS_SERVERLESS else BASE_DIR

BUNDLED_DB_PATH = os.path.join(BASE_DIR, "docurgent.db")
DB_PATH = os.environ.get("DOCURGENT_DB_PATH") or os.path.join(RUNTIME_DIR, "docurgent.db")
UPLOAD_DIR = os.path.join(RUNTIME_DIR, "uploads")
BACKUP_DIR = os.path.join(RUNTIME_DIR, "backups")

os.makedirs(RUNTIME_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(os.path.join(BACKUP_DIR, "db"), exist_ok=True)
os.makedirs(os.path.join(BACKUP_DIR, "files"), exist_ok=True)

if IS_SERVERLESS and not os.path.exists(DB_PATH) and os.path.exists(BUNDLED_DB_PATH):
    shutil.copy2(BUNDLED_DB_PATH, DB_PATH)

# Security Constants
HASH_ITERATIONS = 100000
DEFAULT_CURRENCY = "INR"  # Supports INR (₹) and USD ($)
PLATFORM_COMMISSION_PERCENT = 15  # Doctor keeps 85%, platform 15%
DEFAULT_STORAGE_QUOTA_MB = 5000  # 5 GB initial storage quota

def get_connection():
    """Returns a thread-safe connection to the DocUrgent SQLite database with WAL mode."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

# =========================================================================
# CRYPTOGRAPHIC & AUTHENTICATION UTILITIES
# =========================================================================

def hash_password(password: str, salt: bytes = None) -> tuple:
    """PBKDF2-SHA256 password hashing with 100,000 iterations."""
    if salt is None:
        salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, HASH_ITERATIONS)
    return hashed.hex(), salt.hex()

def verify_password(password: str, hashed_hex: str, salt_hex: str) -> bool:
    """Verifies a password against PBKDF2-SHA256 hash in constant time."""
    salt = bytes.fromhex(salt_hex)
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, hashed_hex)

# --- RFC 6238 Standard TOTP (Zero external dependencies) ---

def generate_totp_secret() -> str:
    """Generates a 32-character Base32 secret for Authenticator apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode('utf-8')

def get_totp_code(secret_b32: str, intervals_no: int = None) -> str:
    """Calculates the standard 6-digit TOTP code for a given interval (default: current 30s window)."""
    if intervals_no is None:
        intervals_no = int(time.time() // 30)
    key = base64.b32decode(secret_b32.strip().upper(), True)
    msg = struct.pack(">Q", intervals_no)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 15
    h_code = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
    return f"{h_code:06d}"

def verify_totp_code(secret_b32: str, code: str, window: int = 1) -> bool:
    """Verifies a 6-digit TOTP code allowing clock drift of +/- window steps (default: 30s)."""
    if not code or not secret_b32:
        return False
    code = code.strip()
    current_interval = int(time.time() // 30)
    for i in range(-window, window + 1):
        if secrets.compare_digest(get_totp_code(secret_b32, current_interval + i), code):
            return True
    return False

def generate_recovery_codes(count: int = 8) -> tuple:
    """Generates emergency one-time recovery codes and their SHA-256 hashes."""
    plain_codes = []
    hashed_codes = []
    for _ in range(count):
        code = f"{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
        plain_codes.append(code)
        hashed_codes.append(hashlib.sha256(code.encode('utf-8')).hexdigest())
    return plain_codes, json.dumps(hashed_codes)

def verify_and_consume_recovery_code(plain_code: str, hashed_codes_json: str) -> tuple:
    """Verifies and consumes a single-use recovery code. Returns (is_valid, updated_json)."""
    if not hashed_codes_json or not plain_code:
        return False, hashed_codes_json
    try:
        hashed_list = json.loads(hashed_codes_json)
    except Exception:
        return False, hashed_codes_json
    
    candidate_hash = hashlib.sha256(plain_code.strip().upper().encode('utf-8')).hexdigest()
    if candidate_hash in hashed_list:
        hashed_list.remove(candidate_hash)
        return True, json.dumps(hashed_list)
    return False, hashed_codes_json

# --- Private File Access with Short-Lived Signed URLs ---

def get_server_secret() -> bytes:
    """Fetches or generates the server cryptographic signing secret."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM system_settings WHERE key = 'server_secret_key'")
    row = c.fetchone()
    if row:
        secret_hex = row['value']
    else:
        secret_hex = secrets.token_hex(32)
        now = datetime.datetime.utcnow().isoformat()
        c.execute("""
            INSERT OR REPLACE INTO system_settings (key, value, updated_at, updated_by)
            VALUES ('server_secret_key', ?, ?, 'system')
        """, (secret_hex, now))
        conn.commit()
    conn.close()
    return bytes.fromhex(secret_hex)

def generate_signed_file_url(filename: str, expires_in_seconds: int = 900) -> str:
    """Generates a secure, short-lived signed download query string (default: 15 minutes)."""
    expires_at = int(time.time()) + expires_in_seconds
    secret = get_server_secret()
    message = f"{filename}:{expires_at}".encode('utf-8')
    token = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return f"/api/files/download?file={filename}&token={token}&expires={expires_at}"

def verify_signed_file_token(filename: str, token: str, expires_timestamp: int) -> bool:
    """Verifies that a signed file download token is valid and unexpired."""
    if int(time.time()) > expires_timestamp:
        return False
    secret = get_server_secret()
    message = f"{filename}:{expires_timestamp}".encode('utf-8')
    expected = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return secrets.compare_digest(token, expected)

# =========================================================================
# AUDIT & ERROR LOGGING (TELEHEALTH COMPLIANCE)
# =========================================================================

def log_audit(conn, user_id, role, action, resource_type, resource_id=None, details=None, ip="127.0.0.1"):
    """Records an immutable audit event for regulatory and compliance adherence."""
    now = datetime.datetime.utcnow().isoformat()
    log_id = str(uuid.uuid4())
    conn.execute("""
    INSERT INTO audit_logs (id, user_id, role, action, resource_type, resource_id, details, ip_address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (log_id, user_id, role, action, resource_type, resource_id, details, ip, now))

def log_error(severity: str, endpoint: str, error_message: str, stack_trace: str = None, user_id: str = None, ip: str = "127.0.0.1"):
    """Records application exceptions and errors for proactive operational monitoring."""
    now = datetime.datetime.utcnow().isoformat()
    log_id = str(uuid.uuid4())
    try:
        conn = get_connection()
        conn.execute("""
        INSERT INTO error_logs (id, severity, endpoint, error_message, stack_trace, user_id, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, severity, endpoint, error_message, stack_trace, user_id, ip, now))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR_LOGGER_FAILURE] Could not write error log: {e}")

# =========================================================================
# SYSTEM SETTINGS HELPERS
# =========================================================================

def get_setting(key: str, default=None):
    """Retrieves a persistent system configuration setting."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
        row = c.fetchone()
        conn.close()
        return row['value'] if row else default
    except Exception:
        return default

def set_setting(key: str, value: str, updated_by: str = "system") -> bool:
    """Updates or inserts a system setting with timestamp and auditor tracking."""
    now = datetime.datetime.utcnow().isoformat()
    try:
        conn = get_connection()
        conn.execute("""
        INSERT OR REPLACE INTO system_settings (key, value, updated_at, updated_by)
        VALUES (?, ?, ?, ?)
        """, (key, str(value), now, updated_by))
        log_audit(conn, updated_by, 'admin', 'SETTING_UPDATE', 'system_settings', key, f"Updated setting {key} to {value}")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log_error("ERROR", "db.set_setting", str(e))
        return False

def get_all_settings():
    """Returns a dictionary of all active system settings."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value, updated_at, updated_by FROM system_settings")
    rows = c.fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}

# =========================================================================
# STORAGE & DATABASE HEALTH METRICS
# =========================================================================

def get_storage_metrics():
    """Calculates storage volume, file counts, and quota alert levels (70%, 85%, 95%)."""
    total_bytes = 0
    file_count = 0
    if os.path.exists(UPLOAD_DIR):
        for root, _, files in os.walk(UPLOAD_DIR):
            for f in files:
                if not f.startswith('.'):
                    fp = os.path.join(root, f)
                    total_bytes += os.path.getsize(fp)
                    file_count += 1
    
    quota_mb = float(get_setting("storage_quota_mb", DEFAULT_STORAGE_QUOTA_MB))
    used_mb = round(total_bytes / (1024 * 1024), 2)
    percent_used = round((used_mb / quota_mb) * 100, 2) if quota_mb > 0 else 0.0

    alert_level = "NORMAL"
    if percent_used >= 95.0:
        alert_level = "CRITICAL"
    elif percent_used >= 85.0:
        alert_level = "WARNING"
    elif percent_used >= 70.0:
        alert_level = "NOTICE"

    return {
        "used_bytes": total_bytes,
        "used_mb": used_mb,
        "quota_mb": quota_mb,
        "percent_used": percent_used,
        "file_count": file_count,
        "alert_level": alert_level,
        "storage_path": UPLOAD_DIR
    }

def get_database_health():
    """Inspects database file size, integrity checks, and entity row counts."""
    conn = get_connection()
    c = conn.cursor()

    # Integrity check
    c.execute("PRAGMA integrity_check")
    integrity_rows = c.fetchall()
    integrity_status = "ok" if integrity_rows and integrity_rows[0][0] == "ok" else "corrupted"

    # Quick table counts
    counts = {}
    for tbl in ['users', 'doctors', 'patients', 'consultations', 'prescriptions', 'payments', 'audit_logs', 'complaints', 'error_logs']:
        try:
            c.execute(f"SELECT COUNT(*) FROM {tbl}")
            counts[tbl] = c.fetchone()[0]
        except Exception:
            counts[tbl] = 0

    conn.close()

    db_size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    db_size_mb = round(db_size_bytes / (1024 * 1024), 3)

    return {
        "database_engine": "SQLite3 (Thread-Safe WAL Mode)",
        "file_path": DB_PATH,
        "size_bytes": db_size_bytes,
        "size_mb": db_size_mb,
        "integrity_status": integrity_status,
        "table_counts": counts,
        "last_checked": datetime.datetime.utcnow().isoformat()
    }

# =========================================================================
# DATABASE INITIALIZATION & SEAMLESS MIGRATIONS
# =========================================================================

def init_db():
    """Initializes tables, migrates constraints seamlessly, and seeds administrators."""
    conn = get_connection()
    c = conn.cursor()

    # Check if 'users' table needs migration to support 'super_admin' and security columns
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    users_sql_row = c.fetchone()
    if users_sql_row:
        users_sql = users_sql_row[0]
        if 'super_admin' not in users_sql:
            # Non-destructive table recreation migration
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("""
            CREATE TABLE users_migrated (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                phone TEXT,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('patient', 'doctor', 'admin', 'super_admin')),
                is_active INTEGER DEFAULT 1,
                is_email_verified INTEGER DEFAULT 0,
                mfa_secret TEXT,
                mfa_enabled INTEGER DEFAULT 0,
                recovery_code_hash TEXT,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TEXT,
                last_login_at TEXT,
                created_at TEXT NOT NULL
            )
            """)
            c.execute("""
            INSERT INTO users_migrated (id, email, phone, password_hash, salt, role, is_active, created_at)
            SELECT id, email, phone, password_hash, salt, role, is_active, created_at FROM users
            """)
            c.execute("DROP TABLE users")
            c.execute("ALTER TABLE users_migrated RENAME TO users")
            c.execute("PRAGMA foreign_keys = ON")
            conn.commit()
    else:
        # Create fresh users table
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            phone TEXT,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient', 'doctor', 'admin', 'super_admin')),
            is_active INTEGER DEFAULT 1,
            is_email_verified INTEGER DEFAULT 0,
            mfa_secret TEXT,
            mfa_enabled INTEGER DEFAULT 0,
            recovery_code_hash TEXT,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until TEXT,
            last_login_at TEXT,
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

    # 11. WebRTC Signaling Table
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

    # 12. System Settings Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_by TEXT
    )
    """)

    # 13. Complaints Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id TEXT PRIMARY KEY,
        consultation_id TEXT,
        patient_id TEXT,
        doctor_id TEXT,
        complaint_type TEXT,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'open' CHECK(status IN ('open', 'under_investigation', 'resolved', 'dismissed')),
        resolution_notes TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id),
        FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    )
    """)

    # 14. Error Logs Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS error_logs (
        id TEXT PRIMARY KEY,
        severity TEXT NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
        endpoint TEXT,
        error_message TEXT NOT NULL,
        stack_trace TEXT,
        user_id TEXT,
        ip_address TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # 15. Doctor Payouts Ledger Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS doctor_payouts (
        id TEXT PRIMARY KEY,
        doctor_id TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'INR',
        period_start TEXT,
        period_end TEXT,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processed', 'held')),
        payout_method TEXT,
        reference_id TEXT,
        processed_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    )
    """)

    conn.commit()

    # Seed Default System Settings
    now = datetime.datetime.utcnow().isoformat()
    default_settings = [
        ("platform_commission_percent", str(PLATFORM_COMMISSION_PERCENT)),
        ("maintenance_mode", "false"),
        ("default_currency", DEFAULT_CURRENCY),
        ("superadmin_email", os.environ.get("SUPERADMIN_EMAIL", "owner@docurgent.in")),
        ("max_upload_size_mb", "5"),
        ("alert_email", os.environ.get("ALERT_EMAIL", "admin@docurgent.in")),
        ("storage_quota_mb", str(DEFAULT_STORAGE_QUOTA_MB)),
        ("server_secret_key", secrets.token_hex(32))
    ]
    for k, v in default_settings:
        c.execute("""
        INSERT OR IGNORE INTO system_settings (key, value, updated_at, updated_by)
        VALUES (?, ?, ?, 'system')
        """, (k, v, now))
    conn.commit()

    # Seed Default Administrator (Standard Admin)
    c.execute("SELECT id FROM users WHERE email = 'admin@docurgent.org'")
    admin_row = c.fetchone()
    if not admin_row:
        admin_id = "user-admin-01"
        pwd_hash, salt = hash_password("DocAdmin2026!")
        c.execute("""
        INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, is_email_verified, created_at)
        VALUES (?, ?, ?, ?, ?, 'admin', 1, 1, ?)
        """, (admin_id, "admin@docurgent.org", "+919876543210", pwd_hash, salt, now))
        log_audit(conn, admin_id, 'admin', 'SYSTEM_INIT', 'users', admin_id, 'Default administrator account seeded')
        conn.commit()

    # Seed Initial Super Admin if not present
    c.execute("SELECT id FROM users WHERE role = 'super_admin'")
    super_admin_row = c.fetchone()
    if not super_admin_row:
        super_id = "user-superadmin-01"
        super_email = os.environ.get("SUPERADMIN_EMAIL", "owner@docurgent.in")
        super_pass = os.environ.get("SUPERADMIN_PASSWORD", "SuperSecureOwner2026!#")
        pwd_hash, salt = hash_password(super_pass)
        totp_secret = generate_totp_secret()
        _, recovery_hash_json = generate_recovery_codes(8)

        c.execute("""
        INSERT INTO users (
            id, email, phone, password_hash, salt, role, is_active,
            is_email_verified, mfa_secret, mfa_enabled, recovery_code_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, 'super_admin', 1, 1, ?, 1, ?, ?)
        """, (super_id, super_email, "+919999999999", pwd_hash, salt, totp_secret, recovery_hash_json, now))
        log_audit(conn, super_id, 'super_admin', 'SYSTEM_INIT', 'users', super_id, 'Initial Super Admin owner account seeded')
        conn.commit()

    # Seed Initial Verified Specialists (if table empty)
    c.execute("SELECT COUNT(*) FROM doctors")
    if c.fetchone()[0] == 0:
        seed_doctors(conn)

    conn.close()

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
        'consultation_fee': 800.0,
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
        'consultation_fee': 1000.0,
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
        'avatar': 'https://images.unsplash.com/photo-1594824476967-48c8b964273f?auto=format&fit=crop&q=80&w=600',
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
        'avatar': 'https://images.unsplash.com/photo-1622902046580-2b47f47f5471?auto=format&fit=crop&q=80&w=600',
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
        'avatar': 'https://images.unsplash.com/photo-1651008376811-b90baee60c1f?auto=format&fit=crop&q=80&w=600',
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
        'verification_status': 'pending_verification',
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
        INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, is_email_verified, created_at)
        VALUES (?, ?, ?, ?, ?, 'doctor', 1, 1, ?)
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
    health = get_database_health()
    print("Database initialized successfully at:", DB_PATH)
    print("Health Status:", health['integrity_status'], "| Size:", f"{health['size_mb']} MB")
    print("Table Counts:", health['table_counts'])
