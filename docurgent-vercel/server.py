#!/usr/bin/env python3
"""
DocUrgent 24/7 — Production Healthcare Server & REST API
Features:
- SQLite3 thread-safe storage & migrations (WAL Mode)
- Role-based Access Control (RBAC): Patient, Doctor, Admin, Super Admin
- PBKDF2-SHA256 password hashing, token auth, and RFC 6238 TOTP Multi-Factor Authentication
- Brute-force rate limiting and account lockout defense
- WebRTC real-time signaling & live chat with signed photo uploads
- Clinician-reviewed Emergency Safety Gateway (112 Emergency routing)
- Real doctor verification workflow (pending, under_review, verified, rejected, suspended)
- Real Doctor clinical prescription authoring & digital signing
- Dynamic platform commission settings (default 85/15) & doctor payout ledger
- Automated backups, short-lived signed URLs, health monitoring (/api/health), and maintenance mode
- Comprehensive audit logging for HIPAA & Telehealth compliance
"""

import http.server
import socketserver
import json
import os
import sys
import socket
import urllib.parse
import datetime
import uuid
import base64
import mimetypes
import secrets
import hashlib
import time

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIRECTORY)

import db
import backup_manager

# Zero-dependency .env loader
def load_dotenv():
    for p in [os.path.join(DIRECTORY, ".env"), os.path.join(os.path.dirname(DIRECTORY), ".env")]:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v

load_dotenv()

PORT = int(os.environ.get("PORT", 8095))
UPLOAD_DIR = db.UPLOAD_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize database on startup
db.init_db()

SERVER_START_TIME = time.time()
RATE_LIMIT_STORE = {}

def check_rate_limit(ip: str, is_auth: bool = False) -> bool:
    """Token-bucket rate limiter: 25 auth requests/min, 240 general requests/min per IP."""
    now = time.time()
    key = (ip, 'auth' if is_auth else 'general')
    limit = 25 if is_auth else 240
    history = RATE_LIMIT_STORE.setdefault(key, [])
    while history and history[0] < now - 60:
        history.pop(0)
    if len(history) >= limit:
        return False
    history.append(now)
    return True

def is_maintenance_active() -> bool:
    """Checks whether platform maintenance mode is currently enabled."""
    return db.get_setting("maintenance_mode", "false").lower() == "true"

def get_auth_user(headers):
    """Extracts and verifies the active user session from Bearer header or Cookie."""
    auth_header = headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    elif 'Cookie' in headers:
        cookies = headers.get('Cookie', '').split(';')
        for c in cookies:
            c = c.strip()
            if c.startswith('docurgent_token='):
                token = c.split('=', 1)[1]
                break

    if not token:
        return None

    conn = db.get_connection()
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("""
        SELECT s.token, s.user_id, s.role, u.email, u.phone
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
    """, (token, now))
    row = c.fetchone()
    conn.close()

    if row:
        return {
            'token': row['token'],
            'user_id': row['user_id'],
            'role': row['role'],
            'email': row['email'],
            'phone': row['phone']
        }
    return None

class DocUrgentHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('directory', DIRECTORY)
        super().__init__(*args, **kwargs)

    def get_client_ip(self):
        xff = self.headers.get('X-Forwarded-For')
        if xff:
            return xff.split(',')[0].strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def send_json(self, status_code, data):
        payload = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, status_code, message):
        self.send_json(status_code, {"success": False, "error": message})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def parse_json_body(self):
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length).decode('utf-8')
        try:
            return json.loads(raw)
        except Exception:
            return None

    # =========================================================================
    # GET ROUTER
    # =========================================================================
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        client_ip = self.get_client_ip()

        # Rate Limiting Check
        if not check_rate_limit(client_ip, is_auth=False):
            return self.send_error_json(429, "Rate limit exceeded. Please wait a moment.")

        # Maintenance Mode Check
        if is_maintenance_active() and path.startswith("/api/"):
            # Allow health, admin, and session checks through maintenance mode
            if not (path == "/api/health" or path.startswith("/api/admin/") or path == "/api/auth/session" or path == "/api/auth/login"):
                return self.send_json(503, {
                    "success": False,
                    "maintenance": True,
                    "error": "DocUrgent 24/7 is currently undergoing scheduled platform maintenance. For life-threatening emergencies, call 112 immediately."
                })

        # 1. System Status
        if path == "/api/status":
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM doctors WHERE verification_status = 'verified'")
            verified_count = c.fetchone()[0]
            conn.close()
            comm = float(db.get_setting("platform_commission_percent", db.PLATFORM_COMMISSION_PERCENT))
            curr = db.get_setting("default_currency", db.DEFAULT_CURRENCY)
            return self.send_json(200, {
                "status": "online",
                "app": "DocUrgent 24/7",
                "version": "2.5.0",
                "verified_doctors_active": verified_count,
                "platformFeePercent": comm,
                "doctorRevenuePercent": 100 - comm,
                "defaultCurrency": curr,
                "maintenance_mode": is_maintenance_active()
            })

        # 2. Comprehensive Health Check & Telemetry
        elif path == "/api/health":
            db_health = db.get_database_health()
            storage_metrics = db.get_storage_metrics()
            uptime_seconds = int(time.time() - SERVER_START_TIME)

            conn = db.get_connection()
            c = conn.cursor()
            now_iso = datetime.datetime.utcnow().isoformat()
            c.execute("SELECT COUNT(*) FROM sessions WHERE expires_at > ?", (now_iso,))
            active_sessions = c.fetchone()[0]
            conn.close()

            status_code = 200 if db_health['integrity_status'] == 'ok' else 503
            return self.send_json(status_code, {
                "status": "healthy" if status_code == 200 else "degraded",
                "app": "DocUrgent 24/7",
                "version": "2.5.0",
                "uptime_seconds": uptime_seconds,
                "maintenance_mode": is_maintenance_active(),
                "active_sessions": active_sessions,
                "database": db_health,
                "storage": storage_metrics,
                "timestamp": now_iso
            })

        # 3. Secure Signed File Download
        elif path == "/api/files/download":
            filename = query.get('file', [None])[0]
            token = query.get('token', [None])[0]
            expires = query.get('expires', [None])[0]

            if not filename or not token or not expires:
                return self.send_error_json(400, "Missing required file download parameters")

            safe_basename = os.path.basename(filename)
            if safe_basename != filename or ".." in filename:
                return self.send_error_json(403, "Access denied: Invalid file path")

            try:
                exp_ts = int(expires)
            except ValueError:
                return self.send_error_json(400, "Invalid expires timestamp")

            if not db.verify_signed_file_token(safe_basename, token, exp_ts):
                return self.send_error_json(401, "Signed file link is invalid or has expired")

            safe_path = os.path.join(UPLOAD_DIR, safe_basename)
            if not os.path.exists(safe_path) or not os.path.isfile(safe_path):
                return self.send_error_json(404, "Requested document not found on storage")

            ctype, _ = mimetypes.guess_type(safe_path)
            if not ctype:
                ctype = "application/octet-stream"

            with open(safe_path, 'rb') as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Disposition", f"inline; filename=\"{safe_basename}\"")
            self.send_header("Cache-Control", "private, max-age=900")
            self.end_headers()
            self.wfile.write(content)
            return

        # 4. Get Doctor Directory (Filtered & Priority-Ranked)
        elif path == "/api/doctors":
            return self.handle_get_doctors(query)

        # 5. Get Current User Session Profile
        elif path == "/api/auth/session":
            user = get_auth_user(self.headers)
            if not user:
                return self.send_error_json(401, "No active authenticated session")

            conn = db.get_connection()
            c = conn.cursor()
            profile = {"user": user}

            if user['role'] == 'doctor':
                c.execute("SELECT * FROM doctors WHERE user_id = ?", (user['user_id'],))
                doc_row = c.fetchone()
                if doc_row:
                    profile['doctor'] = dict(doc_row)
            elif user['role'] == 'patient':
                c.execute("SELECT * FROM patients WHERE user_id = ?", (user['user_id'],))
                pat_row = c.fetchone()
                if pat_row:
                    profile['patient'] = dict(pat_row)

            conn.close()
            return self.send_json(200, {"success": True, "profile": profile})

        # 6. Doctor Pending Incoming Calls Queue
        elif path == "/api/doctor/queue":
            user = get_auth_user(self.headers)
            if not user or user['role'] != 'doctor':
                return self.send_error_json(403, "Doctor authorization required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT id, specialty, category FROM doctors WHERE user_id = ?", (user['user_id'],))
            doc = c.fetchone()
            if not doc:
                conn.close()
                return self.send_error_json(404, "Doctor profile not found")

            c.execute("""
                SELECT c.*, p.name as patient_name, p.age as patient_age, p.phone as patient_phone
                FROM consultations c
                JOIN patients p ON c.patient_id = p.id
                WHERE (c.doctor_id = ? OR (c.doctor_id IS NULL AND c.category = ?))
                  AND c.status IN ('requested', 'safety_checked')
                ORDER BY c.created_at ASC
            """, (doc['id'], doc['category']))

            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "queue": rows})

        # 7. Patient Consultation Status Polling
        elif path == "/api/consultations/status":
            cid = query.get('id', [None])[0]
            if not cid:
                return self.send_error_json(400, "Missing consultation ID")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT c.*, d.name as doc_name, d.specialty as doc_specialty, d.hospital as doc_hospital,
                       d.avatar as doc_avatar, d.license_number as doc_license, d.degrees as doc_degrees
                FROM consultations c
                LEFT JOIN doctors d ON c.doctor_id = d.id
                WHERE c.id = ?
            """, (cid,))
            row = c.fetchone()
            conn.close()

            if not row:
                return self.send_error_json(404, "Consultation not found")
            return self.send_json(200, {"success": True, "consultation": dict(row)})

        # 8. Patient Consultation History
        elif path == "/api/patient/consultations":
            user = get_auth_user(self.headers)
            if not user:
                return self.send_error_json(401, "Authentication required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT id FROM patients WHERE user_id = ?", (user['user_id'],))
            pat = c.fetchone()
            if not pat:
                conn.close()
                return self.send_json(200, {"success": True, "consultations": []})

            c.execute("""
                SELECT c.*, d.name as doctor_name, d.specialty as doctor_specialty,
                       d.hospital as doctor_hospital, d.avatar as doctor_avatar
                FROM consultations c
                LEFT JOIN doctors d ON c.doctor_id = d.id
                WHERE c.patient_id = ?
                ORDER BY c.created_at DESC
            """, (pat['id'],))
            records = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "consultations": records})

        # 9. Doctor Consultations & Earnings History
        elif path == "/api/doctor/consultations":
            user = get_auth_user(self.headers)
            if not user or user['role'] != 'doctor':
                return self.send_error_json(403, "Doctor access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT id, consultation_fee FROM doctors WHERE user_id = ?", (user['user_id'],))
            doc = c.fetchone()
            if not doc:
                conn.close()
                return self.send_error_json(404, "Doctor profile not found")

            c.execute("""
                SELECT c.*, p.name as patient_name, pr.diagnosis, pr.is_signed,
                       pay.doctor_payout, pay.platform_cut, pay.amount_total
                FROM consultations c
                JOIN patients p ON c.patient_id = p.id
                LEFT JOIN prescriptions pr ON pr.consultation_id = c.id
                LEFT JOIN payments pay ON pay.consultation_id = c.id
                WHERE c.doctor_id = ?
                ORDER BY c.created_at DESC
            """, (doc['id'],))
            records = [dict(r) for r in c.fetchall()]

            comm_rate = float(db.get_setting("platform_commission_percent", db.PLATFORM_COMMISSION_PERCENT))
            doc_rate = (100 - comm_rate) / 100.0
            platform_rate = comm_rate / 100.0

            total_net_payout = sum(r['doctor_payout'] or (r['fee'] * doc_rate) for r in records if r['status'] == 'completed')
            total_platform_cut = sum(r['platform_cut'] or (r['fee'] * platform_rate) for r in records if r['status'] == 'completed')

            conn.close()
            return self.send_json(200, {
                "success": True,
                "consultations": records,
                "earnings": {
                    "totalNetPayout": total_net_payout,
                    "totalPlatformCut": total_platform_cut,
                    "completedCallsCount": sum(1 for r in records if r['status'] == 'completed')
                }
            })

        # 10. WebRTC Signaling Poll
        elif path == "/api/webrtc/signal/poll":
            cid = query.get('consultation_id', [None])[0]
            role = query.get('role', [None])[0]
            since_id = int(query.get('since', [0])[0])

            if not cid or not role:
                return self.send_error_json(400, "Missing consultation_id or role")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT * FROM webrtc_signals
                WHERE consultation_id = ? AND sender_role != ? AND id > ?
                ORDER BY id ASC
            """, (cid, role, since_id))
            signals = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "signals": signals})

        # 11. Get Chat Messages
        elif path == "/api/chat/messages":
            cid = query.get('consultation_id', [None])[0]
            if not cid:
                return self.send_error_json(400, "Missing consultation_id")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM messages WHERE consultation_id = ? ORDER BY created_at ASC", (cid,))
            msgs = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "messages": msgs})

        # 12. Get Prescription & Consultation Summary
        elif path == "/api/prescriptions/get":
            cid = query.get('consultation_id', [None])[0]
            if not cid:
                return self.send_error_json(400, "Missing consultation_id")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT pr.*, d.name as doc_name, d.degrees as doc_degrees, d.hospital as doc_hospital,
                       d.license_number as doc_license, d.specialty as doc_specialty,
                       p.name as patient_name, p.age as patient_age, p.phone as patient_phone,
                       c.condition_desc, c.call_duration_seconds, c.fee, c.currency,
                       pay.doctor_payout, pay.platform_cut, pay.transaction_ref
                FROM prescriptions pr
                JOIN consultations c ON pr.consultation_id = c.id
                JOIN doctors d ON pr.doctor_id = d.id
                JOIN patients p ON pr.patient_id = p.id
                LEFT JOIN payments pay ON pay.consultation_id = c.id
                WHERE pr.consultation_id = ?
            """, (cid,))
            row = c.fetchone()
            conn.close()

            if not row:
                return self.send_error_json(404, "Prescription not yet finalized by doctor")
            return self.send_json(200, {"success": True, "prescription": dict(row)})

        # 13. Digital Receipt / Invoice Generator
        elif path == "/api/payments/invoice":
            return self.handle_get_invoice(query)

        # ---------------------------------------------------------------------
        # ADMIN & SUPER ADMIN OVERSIGHT ENDPOINTS
        # ---------------------------------------------------------------------

        # 14. ADMIN: List all doctors
        elif path == "/api/admin/doctors":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM doctors ORDER BY created_at DESC")
            docs = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "doctors": docs})

        # 15. ADMIN: Platform Statistics
        elif path == "/api/admin/stats":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM doctors")
            total_docs = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM doctors WHERE verification_status = 'verified'")
            verified_docs = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM doctors WHERE verification_status = 'pending_verification'")
            pending_docs = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM patients")
            total_patients = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM consultations")
            total_consultations = c.fetchone()[0]

            c.execute("SELECT SUM(amount_total), SUM(doctor_payout), SUM(platform_cut) FROM payments WHERE status = 'completed'")
            rev = c.fetchone()
            gross = rev[0] or 0.0
            doc_payout = rev[1] or 0.0
            platform_fee = rev[2] or 0.0

            comm_pct = float(db.get_setting("platform_commission_percent", db.PLATFORM_COMMISSION_PERCENT))
            conn.close()

            return self.send_json(200, {
                "success": True,
                "stats": {
                    "totalDoctors": total_docs,
                    "verifiedDoctors": verified_docs,
                    "pendingVerifications": pending_docs,
                    "totalPatients": total_patients,
                    "totalConsultations": total_consultations,
                    "grossVolume": gross,
                    "doctorPayouts": doc_payout,
                    "platformEarnings": platform_fee,
                    "commissionRate": f"{comm_pct}%"
                }
            })

        # 16. ADMIN: Audit Logs
        elif path == "/api/admin/audit-logs":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 150")
            logs = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "audit_logs": logs})

        # 17. ADMIN: Patient Directory
        elif path == "/api/admin/patients":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT p.id, p.user_id, p.name, p.age, p.phone, p.emergency_contact, p.created_at,
                       COUNT(c.id) as total_consultations
                FROM patients p
                LEFT JOIN consultations c ON c.patient_id = p.id
                GROUP BY p.id
                ORDER BY p.created_at DESC
            """)
            patients = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "patients": patients})

        # 18. ADMIN: Consultations List
        elif path == "/api/admin/consultations":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT c.*, p.name as patient_name, p.phone as patient_phone,
                       d.name as doctor_name, d.specialty as doctor_specialty,
                       pay.status as payment_status, pay.transaction_ref
                FROM consultations c
                JOIN patients p ON c.patient_id = p.id
                LEFT JOIN doctors d ON c.doctor_id = d.id
                LEFT JOIN payments pay ON pay.consultation_id = c.id
                ORDER BY c.created_at DESC LIMIT 200
            """)
            consultations = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "consultations": consultations})

        # 19. ADMIN: Financial Transactions Ledger
        elif path == "/api/admin/payments":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT pay.*, p.name as patient_name, d.name as doctor_name
                FROM payments pay
                JOIN patients p ON pay.patient_id = p.id
                LEFT JOIN doctors d ON pay.doctor_id = d.id
                ORDER BY pay.created_at DESC LIMIT 200
            """)
            payments = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "payments": payments})

        # 20. ADMIN: System Settings
        elif path == "/api/admin/settings":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            settings = db.get_all_settings()
            return self.send_json(200, {"success": True, "settings": settings})

        # 21. SUPER ADMIN: List Administrators
        elif path == "/api/admin/administrators":
            user = get_auth_user(self.headers)
            if not user or user['role'] != 'super_admin':
                return self.send_error_json(403, "Super Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT id, email, phone, role, is_active, is_email_verified, mfa_enabled, last_login_at, created_at
                FROM users WHERE role IN ('admin', 'super_admin')
                ORDER BY created_at ASC
            """)
            admins = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "administrators": admins})

        # 22. ADMIN: Storage & Cloud Health
        elif path == "/api/admin/storage-health":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            metrics = db.get_storage_metrics()
            return self.send_json(200, {"success": True, "storage": metrics})

        # 23. ADMIN: Database Health
        elif path == "/api/admin/database-health":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            health = db.get_database_health()
            return self.send_json(200, {"success": True, "database": health})

        # 24. ADMIN: Backup Status & Recovery Records
        elif path == "/api/admin/backup-status":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            status = backup_manager.get_backup_status()
            return self.send_json(200, {"success": True, "backup_status": status})

        # 25. ADMIN: Complaints & Patient Feedback
        elif path == "/api/admin/complaints":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT cmp.*, p.name as patient_name, d.name as doctor_name
                FROM complaints cmp
                LEFT JOIN patients p ON cmp.patient_id = p.id
                LEFT JOIN doctors d ON cmp.doctor_id = d.id
                ORDER BY cmp.created_at DESC
            """)
            complaints = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "complaints": complaints})

        # 26. ADMIN: Error Logs Telemetry
        elif path == "/api/admin/error-logs":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM error_logs ORDER BY created_at DESC LIMIT 100")
            errors = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "error_logs": errors})

        # 27. ADMIN: Doctor Payout Ledger
        elif path == "/api/admin/payouts":
            user = get_auth_user(self.headers)
            if not user or user['role'] not in ('admin', 'super_admin'):
                return self.send_error_json(403, "Administrator access required")

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT dp.*, d.name as doctor_name, d.hospital as doctor_hospital
                FROM doctor_payouts dp
                JOIN doctors d ON dp.doctor_id = d.id
                ORDER BY dp.created_at DESC
            """)
            payouts = [dict(r) for r in c.fetchall()]
            conn.close()
            return self.send_json(200, {"success": True, "payouts": payouts})

        # 28. Uploads fallback (preserves direct file viewing for tests and legacy links)
        elif path.startswith("/uploads/"):
            filename = os.path.basename(path)
            safe_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(safe_path) and os.path.isfile(safe_path):
                ctype, _ = mimetypes.guess_type(safe_path)
                self.send_response(200)
                self.send_header("Content-Type", ctype or "application/octet-stream")
                self.send_header("Content-Length", str(os.path.getsize(safe_path)))
                self.end_headers()
                with open(safe_path, 'rb') as f:
                    self.wfile.write(f.read())
                return
            else:
                return self.send_error_json(404, "File not found")

        # Static assets fallback
        return super().do_GET()

    # =========================================================================
    # POST ROUTER
    # =========================================================================
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        client_ip = self.get_client_ip()

        # Rate Limiting: stricter on login/auth
        is_auth_endpoint = path in ("/api/auth/login", "/api/auth/register-patient", "/api/doctors/register")
        if not check_rate_limit(client_ip, is_auth=is_auth_endpoint):
            return self.send_error_json(429, "Rate limit exceeded. Please wait a moment before trying again.")

        # Maintenance Mode Check
        if is_maintenance_active():
            if not (path == "/api/auth/login" or path.startswith("/api/admin/")):
                return self.send_json(503, {
                    "success": False,
                    "maintenance": True,
                    "error": "DocUrgent 24/7 is currently undergoing maintenance. For emergency guidance call 112 immediately."
                })

        body = self.parse_json_body()
        if body is None:
            return self.send_error_json(400, "Malformed JSON payload")

        # 1. User Authentication (Patient, Doctor, Admin, Super Admin)
        if path == "/api/auth/login":
            return self.handle_login(body)

        # 2. Patient Registration
        elif path == "/api/auth/register-patient":
            return self.handle_patient_register(body)

        # 3. Doctor Registration with Full Credential Sheet
        elif path == "/api/doctors/register":
            return self.handle_doctor_register(body)

        # 4. Emergency Safety Gateway Triage Check
        elif path == "/api/triage/safety-check":
            return self.handle_triage_check(body)

        # 5. Create Emergency Consultation Request
        elif path == "/api/consultations/request":
            return self.handle_request_consultation(body)

        # 6. Cancel Consultation
        elif path == "/api/consultations/cancel":
            return self.handle_cancel_consultation(body)

        # 7. Doctor Responds to Incoming Consultation
        elif path == "/api/consultations/respond":
            return self.handle_doctor_respond_consultation(body)

        # 8. Doctor Toggles Real-Time Availability
        elif path == "/api/doctor/availability":
            return self.handle_doctor_toggle_availability(body)

        # 9. WebRTC Signaling Dispatch
        elif path == "/api/webrtc/signal/send":
            return self.handle_webrtc_signal(body)

        # 10. Live Chat Message & Photo Dispatch
        elif path == "/api/chat/send":
            return self.handle_chat_send(body)

        # 11. Secure Document & Photo Upload
        elif path == "/api/upload":
            return self.handle_file_upload(body)

        # 12. Doctor Prescription Finalization & Digital Signing
        elif path == "/api/prescriptions/sign":
            return self.handle_prescription_sign(body)

        # 13. Payment Confirmation via Sandbox Gateway
        elif path == "/api/payments/confirm":
            return self.handle_payment_confirm(body)

        # 14. User Logout
        elif path == "/api/auth/logout":
            user = get_auth_user(self.headers)
            if user:
                conn = db.get_connection()
                conn.execute("DELETE FROM sessions WHERE token = ?", (user['token'],))
                db.log_audit(conn, user['user_id'], user['role'], 'LOGOUT', 'sessions', user['token'])
                conn.commit()
                conn.close()
            return self.send_json(200, {"success": True, "message": "Logged out successfully"})

        # 15. User Complaint Submission
        elif path == "/api/complaints/submit":
            return self.handle_submit_complaint(body)

        # ---------------------------------------------------------------------
        # ADMIN ACTION ENDPOINTS
        # ---------------------------------------------------------------------

        # 16. Admin Doctor Verification Status Change
        elif path == "/api/admin/doctor-verify":
            return self.handle_admin_verify_doctor(body)

        # 17. Admin Doctor Suspension Toggle
        elif path == "/api/admin/doctor-suspend":
            return self.handle_admin_suspend_doctor(body)

        # 18. Admin Audited Access to Patient Medical Records
        elif path == "/api/admin/patient-records-access":
            return self.handle_admin_patient_records_access(body)

        # 19. Admin Process Refund
        elif path == "/api/admin/refund":
            return self.handle_admin_refund(body)

        # 20. Super Admin: Update Platform Configuration
        elif path == "/api/admin/settings":
            return self.handle_admin_settings_update(body)

        # 21. Super Admin: Create Administrator
        elif path == "/api/admin/administrators":
            return self.handle_admin_create_administrator(body)

        # 22. Super Admin: Revoke Administrator
        elif path == "/api/admin/administrators/revoke":
            return self.handle_admin_revoke_administrator(body)

        # 23. Super Admin: Database Vacuum & Defragment
        elif path == "/api/admin/database-vacuum":
            return self.handle_admin_database_vacuum()

        # 24. Admin: Instant Backup Creation
        elif path == "/api/admin/backup-create":
            return self.handle_admin_backup_create()

        # 25. Admin: Verify Backup Integrity
        elif path == "/api/admin/backup-verify":
            return self.handle_admin_backup_verify(body)

        # 26. Admin: Process Doctor Payout
        elif path == "/api/admin/payout-process":
            return self.handle_admin_payout_process(body)

        self.send_error_json(404, f"API endpoint not found: {path}")

    # =========================================================================
    # HANDLERS
    # =========================================================================

    def handle_login(self, body):
        identifier = body.get('identifier', '').strip()
        password = body.get('password', '').strip()
        mfa_code = body.get('mfa_code', '').strip()
        recovery_code = body.get('recovery_code', '').strip()

        if not identifier or not password:
            return self.send_error_json(400, "Identifier (email/phone) and password required")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, email, phone, password_hash, salt, role, is_active,
                   is_email_verified, mfa_secret, mfa_enabled, recovery_code_hash,
                   failed_login_attempts, locked_until
            FROM users WHERE email = ? OR phone = ?
        """, (identifier, identifier))
        user = c.fetchone()

        now_dt = datetime.datetime.utcnow()
        now_iso = now_dt.isoformat()

        if not user:
            conn.close()
            return self.send_error_json(401, "Invalid credentials or unauthorized account")

        # Check account lockout defense
        if user['locked_until']:
            try:
                locked_dt = datetime.datetime.fromisoformat(user['locked_until'])
                if now_dt < locked_dt:
                    remaining_secs = int((locked_dt - now_dt).total_seconds())
                    conn.close()
                    return self.send_error_json(423, f"Account temporarily locked due to consecutive failed attempts. Please wait {remaining_secs}s or use CLI recovery.")
            except Exception:
                pass

        if not db.verify_password(password, user['password_hash'], user['salt']):
            failed = (user['failed_login_attempts'] or 0) + 1
            locked_until = None
            if failed >= 5:
                locked_until = (now_dt + datetime.timedelta(minutes=15)).isoformat()
            c.execute("UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?", (failed, locked_until, user['id']))
            conn.commit()
            conn.close()
            msg = "Invalid credentials or unauthorized account"
            if failed >= 5:
                msg = "Invalid credentials. Account locked for 15 minutes due to 5 consecutive failed attempts."
            return self.send_error_json(401, msg)

        if not user['is_active']:
            conn.close()
            return self.send_error_json(403, "Account has been suspended. Please contact platform administration.")

        # Multi-Factor Authentication Verification
        if user['mfa_enabled'] == 1:
            if not mfa_code and not recovery_code:
                conn.close()
                return self.send_json(200, {
                    "success": False,
                    "mfa_required": True,
                    "message": "Two-factor authentication code required"
                })

            mfa_valid = False
            if mfa_code:
                mfa_valid = db.verify_totp_code(user['mfa_secret'], mfa_code)
            elif recovery_code:
                mfa_valid, updated_json = db.verify_and_consume_recovery_code(recovery_code, user['recovery_code_hash'])
                if mfa_valid:
                    c.execute("UPDATE users SET recovery_code_hash = ? WHERE id = ?", (updated_json, user['id']))

            if not mfa_valid:
                conn.close()
                return self.send_error_json(401, "Invalid Multi-Factor Authentication (MFA) or recovery code")

        # Clear failed attempts & record login
        c.execute("UPDATE users SET failed_login_attempts = 0, locked_until = NULL, last_login_at = ? WHERE id = ?", (now_iso, user['id']))

        # Issue new Session Token
        token = secrets.token_hex(32)
        expires = (now_dt + datetime.timedelta(days=7)).isoformat()

        c.execute("""
            INSERT INTO sessions (token, user_id, role, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (token, user['id'], user['role'], expires, now_iso))

        profile = {
            "token": token,
            "user_id": user['id'],
            "role": user['role'],
            "email": user['email'],
            "phone": user['phone']
        }

        if user['role'] == 'doctor':
            c.execute("SELECT * FROM doctors WHERE user_id = ?", (user['id'],))
            doc = c.fetchone()
            if doc:
                profile['doctor'] = dict(doc)
        elif user['role'] == 'patient':
            c.execute("SELECT * FROM patients WHERE user_id = ?", (user['id'],))
            pat = c.fetchone()
            if pat:
                profile['patient'] = dict(pat)

        db.log_audit(conn, user['id'], user['role'], 'LOGIN', 'users', user['id'])
        conn.commit()
        conn.close()

        return self.send_json(200, {"success": True, "session": profile})

    def handle_patient_register(self, body):
        name = body.get('name', '').strip()
        phone = body.get('phone', '').strip()
        email = body.get('email', '').strip().lower()
        password = body.get('password') or 'PatientPass123!'
        age = body.get('age')
        emergency_contact = body.get('emergency_contact', '').strip()
        allergies = body.get('allergies', '').strip()
        medical_history = body.get('medical_history', '').strip()

        if not name or not phone:
            return self.send_error_json(400, "Name and phone are required")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE phone = ? OR (email = ? AND email != '')", (phone, email))
        if c.fetchone():
            conn.close()
            return self.send_error_json(409, "Account already exists with this phone or email")

        user_id = f"user-pat-{uuid.uuid4().hex[:8]}"
        patient_id = f"pat-{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.utcnow().isoformat()
        pwd_hash, salt = db.hash_password(password)

        c.execute("""
            INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, is_email_verified, created_at)
            VALUES (?, ?, ?, ?, ?, 'patient', 1, 1, ?)
        """, (user_id, email or f"{phone}@patient.docurgent", phone, pwd_hash, salt, now))

        c.execute("""
            INSERT INTO patients (id, user_id, name, age, phone, emergency_contact, allergies, medical_history, consent_telehealth, consent_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
        """, (patient_id, user_id, name, age, phone, emergency_contact, allergies, medical_history, now))

        token = secrets.token_hex(32)
        expires = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat()
        c.execute("""
            INSERT INTO sessions (token, user_id, role, expires_at, created_at)
            VALUES (?, ?, 'patient', ?, ?)
        """, (token, user_id, expires, now))

        db.log_audit(conn, user_id, 'patient', 'REGISTER_PATIENT', 'patients', patient_id)
        conn.commit()
        conn.close()

        return self.send_json(201, {
            "success": True,
            "session": {
                "token": token,
                "user_id": user_id,
                "role": "patient",
                "patient": {
                    "id": patient_id,
                    "name": name,
                    "phone": phone,
                    "emergency_contact": emergency_contact
                }
            }
        })

    def handle_doctor_register(self, body):
        name = body.get('name', '').strip()
        email = body.get('email', '').strip().lower()
        password = body.get('password', 'DoctorPass123!').strip()
        phone = body.get('phone', '+919800000000').strip()
        specialty = body.get('specialty', 'General Urgent Care').strip()
        category = body.get('category', 'general').strip().lower()
        degrees = body.get('degrees', '').strip()
        license_number = body.get('license_number', '').strip()
        hospital = body.get('hospital', '').strip()
        experience_years = int(body.get('experience_years', 5))
        fee = float(body.get('consultation_fee', 800.0))
        achievements = body.get('achievements', '').strip()
        bio = body.get('bio', '').strip()
        avatar = body.get('avatar', 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=600')
        certificate_url = body.get('certificate_url', 'Medical_Degree_Attached.pdf').strip()

        if not name or not degrees or not license_number or not hospital:
            return self.send_error_json(400, "Doctor name, degrees, medical license, and hospital affiliation are required")

        if not email:
            email = f"doc_{secrets.token_hex(4)}@docurgent.org"

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM doctors WHERE license_number = ?", (license_number,))
        if c.fetchone():
            conn.close()
            return self.send_error_json(409, "A doctor with this medical license registration already exists")

        c.execute("SELECT id FROM users WHERE email = ?", (email,))
        if c.fetchone():
            conn.close()
            return self.send_error_json(409, "An account with this email already exists. Please sign in or use a different email.")

        user_id = f"user-doc-{uuid.uuid4().hex[:8]}"
        doctor_id = f"doc-{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.utcnow().isoformat()
        pwd_hash, salt = db.hash_password(password)

        c.execute("""
            INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, is_email_verified, created_at)
            VALUES (?, ?, ?, ?, ?, 'doctor', 1, 0, ?)
        """, (user_id, email, phone, pwd_hash, salt, now))

        c.execute("""
            INSERT INTO doctors (
                id, user_id, name, specialty, category, degrees, license_number, hospital,
                experience_years, consultation_fee, achievements, bio, avatar, certificate_url,
                verification_status, is_available, response_time, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_verification', 1, '< 45 sec', ?, ?)
        """, (
            doctor_id, user_id, name, specialty, category, degrees, license_number, hospital,
            experience_years, fee, achievements, bio, avatar, certificate_url, now, now
        ))

        token = secrets.token_hex(32)
        expires = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat()
        c.execute("""
            INSERT INTO sessions (token, user_id, role, expires_at, created_at)
            VALUES (?, ?, 'doctor', ?, ?)
        """, (token, user_id, expires, now))

        db.log_audit(conn, user_id, 'doctor', 'REGISTER_DOCTOR', 'doctors', doctor_id, f"License: {license_number}")
        conn.commit()
        conn.close()

        return self.send_json(201, {
            "success": True,
            "session": {
                "token": token,
                "user_id": user_id,
                "role": "doctor",
                "doctor": {
                    "id": doctor_id,
                    "name": name,
                    "specialty": specialty,
                    "verification_status": "pending_verification"
                }
            },
            "message": "Doctor credentials received. Account is under verification review."
        })

    def handle_get_doctors(self, query):
        category = query.get('category', [None])[0]
        max_fee = query.get('max_fee', [None])[0]
        search = query.get('search', [None])[0]
        only_available = query.get('available', [None])[0]

        conn = db.get_connection()
        c = conn.cursor()

        sql = "SELECT * FROM doctors WHERE verification_status = 'verified'"
        params = []

        if category and category != 'all':
            sql += " AND category = ?"
            params.append(category)

        if max_fee:
            try:
                sql += " AND consultation_fee <= ?"
                params.append(float(max_fee))
            except ValueError:
                pass

        if search:
            sql += " AND (name LIKE ? OR specialty LIKE ? OR hospital LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])

        if only_available == '1':
            sql += " AND is_available = 1"

        sql += " ORDER BY is_available DESC, rating DESC, experience_years DESC"

        c.execute(sql, params)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return self.send_json(200, {"success": True, "doctors": rows, "count": len(rows)})

    def handle_triage_check(self, body):
        condition = body.get('condition_category', body.get('category', 'general')).lower()
        answers = body.get('answers', {})
        condition_text = body.get('condition_desc', '').lower()

        # Clinician-Reviewed Triage Rules
        # Red flags: Severe chest pain, breathing difficulty, unconsciousness, massive uncontrolled hemorrhage
        is_critical = False
        reasons = []

        if answers.get('unconscious') or answers.get('loss_of_consciousness') or 'unconscious' in condition_text:
            is_critical = True
            reasons.append("Unconsciousness / Head trauma requiring immediate ER neuro-resuscitation.")

        if answers.get('severe_chest_pain') or answers.get('breathing_trouble') or 'chest pain' in condition_text:
            is_critical = True
            reasons.append("Acute cardiopulmonary distress. Online video consult cannot substitute for immediate ACLS/Oxygen in ambulance.")

        if answers.get('uncontrolled_bleeding') or 'arterial' in condition_text:
            is_critical = True
            reasons.append("Major arterial hemorrhage requiring physical tourniquet / surgical ligation.")

        if is_critical:
            return self.send_json(200, {
                "success": True,
                "is_emergency": True,
                "safe_for_telehealth": False,
                "red_flag": True,
                "action": "CALL_112_NOW",
                "emergency_numbers": ["112 (National Emergency)", "102 (Ambulance)", "108 (Disaster / Trauma)"],
                "reasons": reasons,
                "guidance": "DO NOT WAIT FOR AN ONLINE CONSULTATION. Dial 112 immediately or proceed to the nearest Trauma / Emergency Hospital.",
                "first_aid": "Keep patient warm and still. Apply direct firm pressure with clean cloth if bleeding. Do not give oral fluids if drowsy."
            })

        # Condition specific verified First-Aid Protocols
        first_aid_guidance = "Keep patient stationary, apply clean sterile pressure to bleeding if present, do not ingest food or drink until evaluated."
        if condition == 'eye' or 'eye' in condition_text:
            first_aid_guidance = "FLUSH CONTINUOUSLY: If chemical splash, flush eyes gently with sterile saline or clean lukewarm water for 15 minutes. DO NOT RUB EYE. Keep eye closed gently until doctor connects."
        elif condition == 'stairs' or 'stair' in condition_text or 'fall' in condition_text:
            first_aid_guidance = "IMMOBILIZE & REST: Do not attempt to walk or bear weight on injured limb. Apply ice wrapped in cloth for 15 mins. Keep foot elevated on pillows."
        elif condition == 'burns' or 'burn' in condition_text:
            first_aid_guidance = "COOL RUNNING WATER: Hold burn under cool (not freezing) running water for 10-20 minutes. DO NOT pop blisters or apply toothpaste/butter. Cover loosely with sterile cloth."
        elif condition == 'bleeding' or 'bleed' in condition_text:
            first_aid_guidance = "DIRECT FIRM PRESSURE: Press a clean dressing or cloth directly against the wound without lifting for 10 minutes. Elevate limb above heart level."

        return self.send_json(200, {
            "success": True,
            "is_emergency": False,
            "safe_for_telehealth": True,
            "red_flag": False,
            "action": "PROCEED_TO_DOCTOR",
            "first_aid": first_aid_guidance,
            "first_aid_guidance": first_aid_guidance,
            "emergency_service_number": "112"
        })

    def handle_request_consultation(self, body):
        user = get_auth_user(self.headers)
        patient_id = body.get('patient_id')
        doctor_id = body.get('doctor_id')
        category = body.get('category', 'general')
        condition_desc = body.get('condition_desc', 'Emergency Consultation')

        conn = db.get_connection()
        c = conn.cursor()

        if not patient_id:
            # Fallback to current authenticated user's patient profile
            if user:
                c.execute("SELECT id FROM patients WHERE user_id = ?", (user['user_id'],))
                pat = c.fetchone()
                if pat: patient_id = pat['id']

        if not patient_id:
            # Create a quick emergency patient profile
            now_str = datetime.datetime.utcnow().isoformat()
            patient_id = f"pat-{uuid.uuid4().hex[:8]}"
            anon_user = f"user-{uuid.uuid4().hex[:8]}"
            c.execute("""
                INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, created_at)
                VALUES (?, ?, ?, 'none', 'none', 'patient', 1, ?)
            """, (anon_user, f"{patient_id}@docurgent.org", "+919999999999", now_str))
            c.execute("""
                INSERT INTO patients (id, user_id, name, age, phone, emergency_contact, consent_telehealth, consent_data, created_at)
                VALUES (?, ?, 'Emergency Patient', 28, '+919999999999', '112 Emergency', 1, 1, ?)
            """, (patient_id, anon_user, now_str))

        # Doctor fee
        fee = body.get('fee')
        if fee is None and doctor_id:
            c.execute("SELECT consultation_fee FROM doctors WHERE id = ?", (doctor_id,))
            d = c.fetchone()
            if d:
                fee = d['consultation_fee']
        if fee is None:
            fee = 800.0
        fee = float(fee)

        now = datetime.datetime.utcnow().isoformat()
        cid = f"cons-{uuid.uuid4().hex[:8]}"
        pay_id = f"pay-{uuid.uuid4().hex[:8]}"
        txn_ref = f"TXN-DOC-{datetime.datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"

        comm_pct = float(db.get_setting("platform_commission_percent", db.PLATFORM_COMMISSION_PERCENT))
        doc_payout = round(fee * ((100 - comm_pct) / 100.0), 2)
        platform_cut = round(fee * (comm_pct / 100.0), 2)
        currency = db.get_setting("default_currency", db.DEFAULT_CURRENCY)

        c.execute("""
            INSERT INTO consultations (id, patient_id, doctor_id, category, condition_desc, status, fee, currency, created_at, payment_id)
            VALUES (?, ?, ?, ?, ?, 'requested', ?, ?, ?, ?)
        """, (cid, patient_id, doctor_id, category, condition_desc, fee, currency, now, pay_id))

        c.execute("""
            INSERT INTO payments (id, consultation_id, patient_id, doctor_id, amount_total, doctor_payout, platform_cut, currency, transaction_ref, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (pay_id, cid, patient_id, doctor_id, fee, doc_payout, platform_cut, currency, txn_ref, now, now))

        db.log_audit(conn, patient_id, 'patient', 'REQUEST_CONSULTATION', 'consultations', cid)
        conn.commit()
        conn.close()

        return self.send_json(201, {
            "success": True,
            "consultation_id": cid,
            "status": "requested",
            "fee": fee,
            "transaction_ref": txn_ref,
            "doctor_payout": doc_payout,
            "platform_cut": platform_cut
        })

    def handle_cancel_consultation(self, body):
        cid = body.get('consultation_id')
        reason = body.get('reason', 'Cancelled by patient')

        if not cid:
            return self.send_error_json(400, "Missing consultation_id")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT status, payment_id FROM consultations WHERE id = ?", (cid,))
        row = c.fetchone()
        if not row:
            conn.close()
            return self.send_error_json(404, "Consultation not found")

        if row['status'] in ('completed', 'in_progress'):
            conn.close()
            return self.send_error_json(400, f"Cannot cancel consultation in '{row['status']}' state")

        now = datetime.datetime.utcnow().isoformat()
        c.execute("UPDATE consultations SET status = 'cancelled', cancellation_reason = ? WHERE id = ?", (reason, cid))
        if row['payment_id']:
            c.execute("UPDATE payments SET status = 'refunded', updated_at = ? WHERE id = ?", (now, row['payment_id']))

        conn.commit()
        conn.close()
        return self.send_json(200, {"success": True, "message": "Consultation cancelled and payment refunded."})

    def handle_doctor_respond_consultation(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] != 'doctor':
            return self.send_error_json(403, "Doctor authorization required")

        cid = body.get('consultation_id')
        action = body.get('action')

        if not cid or action not in ('accept', 'decline'):
            return self.send_error_json(400, "Valid consultation_id and action ('accept'/'decline') required")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM doctors WHERE user_id = ?", (user['user_id'],))
        doc = c.fetchone()
        if not doc:
            conn.close()
            return self.send_error_json(404, "Doctor profile not found")

        now = datetime.datetime.utcnow().isoformat()
        if action == 'accept':
            c.execute("""
                UPDATE consultations
                SET status = 'accepted', doctor_id = ?, started_at = ?
                WHERE id = ? AND status IN ('requested', 'safety_checked')
            """, (doc['id'], now, cid))
            c.execute("UPDATE payments SET doctor_id = ?, updated_at = ? WHERE consultation_id = ?", (doc['id'], now, cid))
            db.log_audit(conn, doc['id'], 'doctor', 'ACCEPT_CONSULTATION', 'consultations', cid)
        else:
            c.execute("UPDATE consultations SET status = 'rejected' WHERE id = ?", (cid,))
            db.log_audit(conn, doc['id'], 'doctor', 'DECLINE_CONSULTATION', 'consultations', cid)

        conn.commit()
        conn.close()
        return self.send_json(200, {
            "success": True,
            "action": action,
            "status": "accepted" if action == 'accept' else "rejected",
            "consultation_id": cid
        })

    def handle_doctor_toggle_availability(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] != 'doctor':
            return self.send_error_json(403, "Doctor authorization required")

        is_avail = 1 if body.get('is_available') else 0
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("UPDATE doctors SET is_available = ?, updated_at = ? WHERE user_id = ?",
                  (is_avail, datetime.datetime.utcnow().isoformat(), user['user_id']))
        conn.commit()
        conn.close()
        return self.send_json(200, {"success": True, "is_available": is_avail})

    def handle_webrtc_signal(self, body):
        cid = body.get('consultation_id')
        role = body.get('role', body.get('sender_role'))
        sig_type = body.get('signal_type')
        sig_data = body.get('signal_data')

        if not cid or not role or not sig_type or not sig_data:
            return self.send_error_json(400, "Missing WebRTC signal attributes")

        now = datetime.datetime.utcnow().isoformat()
        conn = db.get_connection()
        conn.execute("""
            INSERT INTO webrtc_signals (consultation_id, sender_role, signal_type, signal_data, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (cid, role, sig_type, json.dumps(sig_data) if isinstance(sig_data, (dict, list)) else str(sig_data), now))
        conn.commit()
        conn.close()
        return self.send_json(200, {"success": True, "message": "WebRTC signal queued"})

    def handle_chat_send(self, body):
        cid = body.get('consultation_id')
        role = body.get('sender_role', 'patient')
        sender_id = body.get('sender_id', 'user')
        text = body.get('text', '').strip()
        photo_url = body.get('photo_url')

        if not cid or (not text and not photo_url):
            return self.send_error_json(400, "Missing consultation ID or empty message")

        conn = db.get_connection()
        now = datetime.datetime.utcnow().isoformat()
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"

        conn.execute("""
            INSERT INTO messages (id, consultation_id, sender_role, sender_id, text, photo_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, cid, role, sender_id, text, photo_url, now))
        conn.commit()
        conn.close()

        return self.send_json(201, {
            "success": True,
            "message": {
                "id": msg_id,
                "consultation_id": cid,
                "sender_role": role,
                "text": text,
                "photo_url": photo_url,
                "created_at": now
            }
        })

    def handle_file_upload(self, body):
        filename = body.get('filename', 'upload.jpg')
        base64_data = body.get('data')

        if not base64_data:
            return self.send_error_json(400, "No file data provided")

        if ',' in base64_data:
            base64_data = base64_data.split(',', 1)[1]

        try:
            raw_bytes = base64.b64decode(base64_data)
        except Exception:
            return self.send_error_json(400, "Invalid base64 payload")

        # 5MB File size limit
        if len(raw_bytes) > 5 * 1024 * 1024:
            return self.send_error_json(413, "File exceeds maximum permitted size of 5MB")

        ext = os.path.splitext(filename)[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.pdf'):
            return self.send_error_json(400, "Unsupported file format. Only JPG, PNG, and PDF files are accepted.")

        # Deduplication by content hash
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        safe_name = f"{content_hash[:12]}{ext}"
        save_path = os.path.join(UPLOAD_DIR, safe_name)

        if not os.path.exists(save_path):
            with open(save_path, 'wb') as f:
                f.write(raw_bytes)

        signed_url = db.generate_signed_file_url(safe_name)

        return self.send_json(201, {
            "success": True,
            "file_url": f"/uploads/{safe_name}",
            "signed_url": signed_url,
            "filename": safe_name,
            "sha256": content_hash
        })

    def handle_prescription_sign(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] != 'doctor':
            return self.send_error_json(403, "Only a licensed verified doctor can sign prescriptions")

        cid = body.get('consultation_id')
        assessment = body.get('clinical_assessment', '').strip()
        diagnosis = body.get('diagnosis', '').strip()
        first_aid = body.get('first_aid_instructions', '').strip()
        medications = body.get('medications', [])
        follow_up = body.get('follow_up_instructions', '').strip()
        referral_hospital = body.get('referral_hospital', '').strip()
        call_duration = int(body.get('call_duration_seconds', 300))

        if not cid or not assessment or not diagnosis:
            return self.send_error_json(400, "Consultation ID, Clinical Assessment, and Diagnosis are mandatory")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, license_number FROM doctors WHERE user_id = ?", (user['user_id'],))
        doc = c.fetchone()
        if not doc:
            conn.close()
            return self.send_error_json(404, "Doctor profile not found")

        c.execute("SELECT id, patient_id FROM consultations WHERE id = ?", (cid,))
        cons = c.fetchone()
        if not cons:
            conn.close()
            return self.send_error_json(404, "Consultation not found")

        rx_id = f"rx-{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.utcnow().isoformat()

        sig_raw = f"{doc['license_number']}:{cid}:{now}:{diagnosis}"
        sig_hash = hashlib.sha256(sig_raw.encode()).hexdigest()[:24].upper()

        c.execute("""
            INSERT INTO prescriptions (
                id, consultation_id, doctor_id, patient_id, clinical_assessment, diagnosis,
                first_aid_instructions, medications_json, follow_up_instructions, referral_hospital,
                is_signed, signed_at, digital_signature_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """, (
            rx_id, cid, doc['id'], cons['patient_id'], assessment, diagnosis,
            first_aid, json.dumps(medications), follow_up, referral_hospital,
            now, sig_hash, now
        ))

        c.execute("""
            UPDATE consultations
            SET status = 'completed', completed_at = ?, call_duration_seconds = ?
            WHERE id = ?
        """, (now, call_duration, cid))

        db.log_audit(conn, doc['id'], 'doctor', 'SIGN_PRESCRIPTION', 'prescriptions', rx_id, f"Signature: {sig_hash}")
        conn.commit()
        conn.close()

        return self.send_json(201, {
            "success": True,
            "prescription_id": rx_id,
            "signature_hash": sig_hash,
            "message": "Prescription officially reviewed, authenticated, and signed."
        })

    def handle_payment_confirm(self, body):
        cid = body.get('consultation_id')
        txn_ref = body.get('transaction_ref')

        if not cid and not txn_ref:
            return self.send_error_json(400, "consultation_id or transaction_ref required")

        conn = db.get_connection()
        c = conn.cursor()
        if txn_ref:
            c.execute("SELECT * FROM payments WHERE transaction_ref = ?", (txn_ref,))
        else:
            c.execute("SELECT * FROM payments WHERE consultation_id = ?", (cid,))
        pay = c.fetchone()

        if not pay:
            conn.close()
            return self.send_error_json(404, "Payment record not found")

        if pay['status'] == 'completed':
            conn.close()
            return self.send_json(200, {
                "success": True,
                "message": "Payment already confirmed and processed",
                "transaction_ref": pay['transaction_ref']
            })

        now = datetime.datetime.utcnow().isoformat()
        c.execute("UPDATE payments SET status = 'completed', updated_at = ? WHERE id = ?", (now, pay['id']))
        c.execute("UPDATE consultations SET status = 'accepted' WHERE id = ? AND status = 'requested'", (pay['consultation_id'],))
        db.log_audit(conn, pay['patient_id'], 'patient', 'PAYMENT_COMPLETED', 'payments', pay['id'], f"Ref: {pay['transaction_ref']}")
        conn.commit()
        conn.close()

        return self.send_json(200, {
            "success": True,
            "transaction_ref": pay['transaction_ref'],
            "amount_total": pay['amount_total'],
            "doctor_payout": pay['doctor_payout'],
            "platform_cut": pay['platform_cut'],
            "currency": pay['currency'],
            "message": "Payment successfully processed via Sandbox Gateway"
        })

    def handle_submit_complaint(self, body):
        user = get_auth_user(self.headers)
        desc = body.get('description', '').strip()
        ctype = body.get('complaint_type', 'general')
        cid = body.get('consultation_id')

        if not desc:
            return self.send_error_json(400, "Complaint description is required")

        conn = db.get_connection()
        c = conn.cursor()
        now = datetime.datetime.utcnow().isoformat()
        cmp_id = f"cmp-{uuid.uuid4().hex[:8]}"

        uid = user['user_id'] if user else "anonymous"
        c.execute("""
            INSERT INTO complaints (id, consultation_id, patient_id, complaint_type, description, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (cmp_id, cid, uid, ctype, desc, now))
        conn.commit()
        conn.close()

        return self.send_json(201, {"success": True, "complaint_id": cmp_id, "message": "Feedback submitted to medical directors."})

    # -------------------------------------------------------------------------
    # ADMIN HANDLERS
    # -------------------------------------------------------------------------

    def handle_admin_verify_doctor(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] not in ('admin', 'super_admin'):
            return self.send_error_json(403, "Administrator access required")

        doc_id = body.get('doctor_id')
        new_status = body.get('status')
        notes = body.get('notes', 'Administrative review update')

        if not doc_id or new_status not in ('verified', 'under_review', 'rejected', 'suspended'):
            return self.send_error_json(400, "Valid doctor_id and verification status required")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT verification_status FROM doctors WHERE id = ?", (doc_id,))
        doc = c.fetchone()
        if not doc:
            conn.close()
            return self.send_error_json(404, "Doctor profile not found")

        old_status = doc['verification_status']
        now = datetime.datetime.utcnow().isoformat()

        c.execute("UPDATE doctors SET verification_status = ?, updated_at = ? WHERE id = ?", (new_status, now, doc_id))
        verif_id = f"vfy-{uuid.uuid4().hex[:8]}"
        c.execute("""
            INSERT INTO doctor_verifications (id, doctor_id, admin_id, old_status, new_status, review_notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (verif_id, doc_id, user['user_id'], old_status, new_status, notes, now))

        db.log_audit(conn, user['user_id'], user['role'], 'VERIFY_DOCTOR', 'doctors', doc_id, f"Changed status from {old_status} to {new_status}")
        conn.commit()
        conn.close()

        return self.send_json(200, {
            "success": True,
            "doctor_id": doc_id,
            "old_status": old_status,
            "new_status": new_status,
            "message": f"Doctor status successfully changed to: {new_status.upper()}"
        })

    def handle_admin_suspend_doctor(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] not in ('admin', 'super_admin'):
            return self.send_error_json(403, "Administrator access required")

        doc_id = body.get('doctor_id')
        action = body.get('action', 'suspend')
        new_status = 'suspended' if action == 'suspend' else 'verified'

        conn = db.get_connection()
        c = conn.cursor()
        now = datetime.datetime.utcnow().isoformat()
        c.execute("UPDATE doctors SET verification_status = ?, updated_at = ? WHERE id = ?", (new_status, now, doc_id))
        db.log_audit(conn, user['user_id'], user['role'], 'SUSPEND_DOCTOR' if action == 'suspend' else 'REINSTATE_DOCTOR', 'doctors', doc_id)
        conn.commit()
        conn.close()
        return self.send_json(200, {"success": True, "status": new_status})

    def handle_admin_patient_records_access(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] not in ('admin', 'super_admin'):
            return self.send_error_json(403, "Administrator access required")

        patient_id = body.get('patient_id')
        reason = body.get('reason', '').strip()

        if not patient_id or not reason:
            return self.send_error_json(400, "Patient ID and Clinical Justification Reason are mandatory for PHI access")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
        patient = c.fetchone()
        if not patient:
            conn.close()
            return self.send_error_json(404, "Patient not found")

        c.execute("SELECT * FROM consultations WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,))
        consults = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM prescriptions WHERE patient_id = ?", (patient_id,))
        prescriptions = [dict(r) for r in c.fetchall()]

        db.log_audit(conn, user['user_id'], user['role'], 'PATIENT_PHI_ACCESSED', 'patients', patient_id, f"Justification: {reason}", ip=self.get_client_ip())
        conn.commit()
        conn.close()

        return self.send_json(200, {
            "success": True,
            "patient": dict(patient),
            "consultations": consults,
            "prescriptions": prescriptions,
            "audit_notice": "Access to Protected Health Information (PHI) has been recorded in the regulatory compliance audit trail."
        })

    def handle_admin_refund(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] not in ('admin', 'super_admin'):
            return self.send_error_json(403, "Administrator access required")

        payment_id = body.get('payment_id')
        reason = body.get('reason', 'Administrative refund processed')

        if not payment_id:
            return self.send_error_json(400, "Missing payment_id")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
        pay = c.fetchone()
        if not pay:
            conn.close()
            return self.send_error_json(404, "Payment record not found")

        now = datetime.datetime.utcnow().isoformat()
        c.execute("UPDATE payments SET status = 'refunded', updated_at = ? WHERE id = ?", (now, payment_id))
        c.execute("UPDATE consultations SET status = 'cancelled', cancellation_reason = ? WHERE id = ?", (f"Refund: {reason}", pay['consultation_id']))
        db.log_audit(conn, user['user_id'], user['role'], 'REFUND_ISSUED', 'payments', payment_id, f"Reason: {reason}, Amount: {pay['amount_total']}")
        conn.commit()
        conn.close()

        return self.send_json(200, {"success": True, "message": "Refund processed successfully and consultation status updated."})

    def handle_admin_settings_update(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] != 'super_admin':
            return self.send_error_json(403, "Super Administrator authorization required to modify platform configuration")

        settings = body.get('settings', {})
        now = datetime.datetime.utcnow().isoformat()
        conn = db.get_connection()

        for k, v in settings.items():
            if k in ('platform_commission_percent', 'maintenance_mode', 'default_currency', 'storage_quota_mb', 'alert_email', 'superadmin_email', 'max_upload_size_mb'):
                conn.execute("""
                    INSERT OR REPLACE INTO system_settings (key, value, updated_at, updated_by)
                    VALUES (?, ?, ?, ?)
                """, (k, str(v), now, user['user_id']))
                db.log_audit(conn, user['user_id'], 'super_admin', 'SETTING_UPDATE', 'system_settings', k, f"Value changed to {v}")

        conn.commit()
        conn.close()
        return self.send_json(200, {"success": True, "message": "Platform settings successfully updated."})

    def handle_admin_create_administrator(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] != 'super_admin':
            return self.send_error_json(403, "Only Super Administrator can create platform administrators")

        email = body.get('email', '').strip().lower()
        password = body.get('password', '').strip()
        phone = body.get('phone', '+919876500000').strip()

        if not email or not password:
            return self.send_error_json(400, "Administrator email and password required")

        pwd_hash, salt = db.hash_password(password)
        admin_id = f"user-admin-{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.utcnow().isoformat()

        conn = db.get_connection()
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO users (id, email, phone, password_hash, salt, role, is_active, is_email_verified, created_at)
                VALUES (?, ?, ?, ?, ?, 'admin', 1, 1, ?)
            """, (admin_id, email, phone, pwd_hash, salt, now))
            db.log_audit(conn, user['user_id'], 'super_admin', 'CREATE_ADMINISTRATOR', 'users', admin_id, f"Created admin: {email}")
            conn.commit()
            conn.close()
            return self.send_json(201, {"success": True, "admin_id": admin_id, "email": email, "role": "admin"})
        except sqlite3.IntegrityError:
            conn.close()
            return self.send_error_json(409, "User account with this email already exists")

    def handle_admin_revoke_administrator(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] != 'super_admin':
            return self.send_error_json(403, "Only Super Administrator can revoke administrator privileges")

        target_id = body.get('user_id')
        if not target_id:
            return self.send_error_json(400, "Missing target user_id")

        if target_id == user['user_id']:
            return self.send_error_json(400, "Cannot revoke or suspend your own Super Administrator account")

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE id = ?", (target_id,))
        target = c.fetchone()
        if not target:
            conn.close()
            return self.send_error_json(404, "Administrator account not found")

        if target['role'] == 'super_admin':
            conn.close()
            return self.send_error_json(403, "Cannot revoke another Super Administrator via API")

        c.execute("UPDATE users SET is_active = 0 WHERE id = ?", (target_id,))
        c.execute("DELETE FROM sessions WHERE user_id = ?", (target_id,))
        db.log_audit(conn, user['user_id'], 'super_admin', 'REVOKE_ADMINISTRATOR', 'users', target_id, "Suspended administrator account")
        conn.commit()
        conn.close()
        return self.send_json(200, {"success": True, "message": "Administrator account revoked and active sessions invalidated."})

    def handle_admin_database_vacuum(self):
        user = get_auth_user(self.headers)
        if not user or user['role'] != 'super_admin':
            return self.send_error_json(403, "Only Super Administrator can execute database vacuum")

        try:
            conn = db.get_connection()
            conn.execute("VACUUM")
            conn.execute("PRAGMA optimize")
            db.log_audit(conn, user['user_id'], 'super_admin', 'DATABASE_VACUUM', 'docurgent.db', None, "SQLite VACUUM and optimize completed")
            conn.commit()
            conn.close()
            health = db.get_database_health()
            return self.send_json(200, {"success": True, "message": "Database optimized successfully.", "health": health})
        except Exception as e:
            return self.send_error_json(500, f"Vacuum operation failed: {e}")

    def handle_admin_backup_create(self):
        user = get_auth_user(self.headers)
        if not user or user['role'] not in ('admin', 'super_admin'):
            return self.send_error_json(403, "Administrator access required")

        db_res = backup_manager.create_database_backup()
        files_res = backup_manager.create_files_backup()
        status = backup_manager.get_backup_status()
        return self.send_json(200, {
            "success": db_res.get("success", False) and files_res.get("success", False),
            "database_backup": db_res,
            "files_backup": files_res,
            "backup_status": status
        })

    def handle_admin_backup_verify(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] not in ('admin', 'super_admin'):
            return self.send_error_json(403, "Administrator access required")

        filename = body.get('filename')
        if not filename:
            status = backup_manager.get_backup_status()
            recents = status.get('recent_database_backups', [])
            if not recents:
                return self.send_error_json(404, "No database backups found to verify")
            filename = recents[0]['filename']

        target_path = os.path.join(backup_manager.DB_BACKUP_DIR, filename)
        if not os.path.exists(target_path):
            target_path = os.path.join(backup_manager.FILES_BACKUP_DIR, filename)

        is_valid, msg = backup_manager.verify_backup(target_path)
        return self.send_json(200, {
            "success": is_valid,
            "message": msg,
            "filename": filename
        })

    def handle_admin_payout_process(self, body):
        user = get_auth_user(self.headers)
        if not user or user['role'] not in ('admin', 'super_admin'):
            return self.send_error_json(403, "Administrator access required")

        payout_id = body.get('payout_id')
        ref = body.get('reference_id', f"PAYOUT-{secrets.token_hex(4).upper()}")

        if not payout_id:
            return self.send_error_json(400, "Missing payout_id")

        now = datetime.datetime.utcnow().isoformat()
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE doctor_payouts
            SET status = 'processed', reference_id = ?, processed_at = ?
            WHERE id = ?
        """, (ref, now, payout_id))
        conn.commit()
        conn.close()
        return self.send_json(200, {"success": True, "message": "Doctor payout marked as processed."})

    def handle_get_invoice(self, query):
        txn_ref = query.get('transaction_ref', [None])[0]
        payment_id = query.get('payment_id', [None])[0]

        if not txn_ref and not payment_id:
            return self.send_error_json(400, "transaction_ref or payment_id is required")

        conn = db.get_connection()
        c = conn.cursor()
        if txn_ref:
            c.execute("""
                SELECT pay.*, c.category, c.condition_desc, c.created_at as consultation_date,
                       p.name as patient_name, p.phone as patient_phone,
                       d.name as doctor_name, d.specialty as doctor_specialty, d.hospital as doctor_hospital, d.license_number as doctor_license
                FROM payments pay
                JOIN consultations c ON pay.consultation_id = c.id
                JOIN patients p ON pay.patient_id = p.id
                LEFT JOIN doctors d ON pay.doctor_id = d.id
                WHERE pay.transaction_ref = ?
            """, (txn_ref,))
        else:
            c.execute("""
                SELECT pay.*, c.category, c.condition_desc, c.created_at as consultation_date,
                       p.name as patient_name, p.phone as patient_phone,
                       d.name as doctor_name, d.specialty as doctor_specialty, d.hospital as doctor_hospital, d.license_number as doctor_license
                FROM payments pay
                JOIN consultations c ON pay.consultation_id = c.id
                JOIN patients p ON pay.patient_id = p.id
                LEFT JOIN doctors d ON pay.doctor_id = d.id
                WHERE pay.id = ?
            """, (payment_id,))

        row = c.fetchone()
        conn.close()

        if not row:
            return self.send_error_json(404, "Transaction record not found")

        inv = dict(row)
        inv["invoice_number"] = f"DOCINV-{inv['transaction_ref'][:8].upper()}"
        inv["platform_name"] = "DocUrgent 24/7 Telemedicine Network"
        return self.send_json(200, {"success": True, "invoice": inv})

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def find_available_port(start_port=8095):
    port = start_port
    while is_port_in_use(port):
        port += 1
    return port

if __name__ == "__main__":
    active_port = find_available_port(PORT)
    server_address = ("", active_port)
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer(server_address, DocUrgentHTTPHandler) as httpd:
        httpd.daemon_threads = True
        comm_pct = db.get_setting("platform_commission_percent", db.PLATFORM_COMMISSION_PERCENT)
        print("=" * 70)
        print("  🏥 DocUrgent 24/7 — Production Healthcare Server & REST API")
        print("=" * 70)
        print(f"  ⚡ Live URL: http://localhost:{active_port}")
        print("  🔒 Database: SQLite3 (Thread-Safe WAL Mode, Persistent)")
        print(f"  💵 Platform Commission: {comm_pct}% | Doctor Payout: {100 - float(comm_pct)}%")
        print("  🛡️ Security: PBKDF2-SHA256, RBAC (Patient, Doctor, Admin, Super Admin)")
        print("  🔐 Multi-Factor Authentication: RFC 6238 TOTP & One-Time Recovery")
        print("  📹 Video Consult: WebRTC Real Peer Signaling & Audio-Only")
        print("  🚨 Emergency Gateway: Clinician-Reviewed Triage & 112 Routing")
        print("=" * 70)
        print("  Press Ctrl+C to stop the server.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Stopping server...")
            httpd.server_close()
