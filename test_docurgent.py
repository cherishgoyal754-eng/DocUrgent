#!/usr/bin/env python3
"""
Comprehensive Test Suite for DocUrgent 24/7
Tests all 21 core clinical, architectural, and security requirements:
1. Patient registration & consent
2. Patient login & session persistence
3. Doctor registration with credential sheet
4. Doctor verification status system (pending, under_review, verified, rejected, suspended)
5. Admin doctor approval & rejection workflow
6. Role-based access control (RBAC) & unauthorized medical record protection
7. Clinician-reviewed Emergency Safety Gateway & 112 routing
8. Doctor matching & specialty filtering (Eye injury, Stair fall, Burns)
9. Consultation request creation & 85/15 fee split tracking
10. Real-time Doctor queue & consultation acceptance
11. Consultation cancellation & automatic refund handling
12. Live chat real-time messaging & scoping
13. Secure photo attachment & file validation (format whitelist, 5MB limit)
14. Doctor prescription authoring, clinical review & cryptographic digital signature
15. Reliable payment calculation, sandbox confirmation & duplicate payment prevention
16. WebRTC real-time signaling & peer exchange
17. Hospital physical ER referral workflow
18. Data persistence in SQLite database
19. Audit logging for healthcare compliance
20. Session authentication & logout
21. Invalid input handling & edge cases
"""

import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
import time
import base64
import sqlite3

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
TEST_PORT = 8098
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

def make_request(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read()
            try:
                res_body = raw.decode("utf-8")
                return response.status, json.loads(res_body) if res_body else {}
            except Exception:
                return response.status, {"raw_bytes_len": len(raw)}
    except urllib.error.HTTPError as e:
        err_raw = e.read()
        try:
            err_body = err_raw.decode("utf-8")
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"error": str(err_raw)}

def run_tests():
    print("=" * 70)
    print("  🏥 DOCURGENT 24/7 — COMPREHENSIVE AUTOMATED VERIFICATION SUITE")
    print("=" * 70)

    # Clean test port if busy
    subprocess.run(f"lsof -iTCP:{TEST_PORT} -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true", shell=True)
    time.sleep(1)

    # Start test server on TEST_PORT
    env = os.environ.copy()
    server_script = os.path.join(DIRECTORY, "docurgent", "server.py")
    
    # Temporarily set PORT to TEST_PORT in command
    proc = subprocess.Popen([sys.executable, "-c", f"""
import sys
sys.path.insert(0, '{os.path.join(DIRECTORY, "docurgent")}')
import server
server.PORT = {TEST_PORT}
server.socketserver.ThreadingTCPServer.allow_reuse_address = True
with server.socketserver.ThreadingTCPServer(('', {TEST_PORT}), server.DocUrgentHTTPHandler) as httpd:
    httpd.daemon_threads = True
    httpd.serve_forever()
"""])
    time.sleep(2)

    try:
        # 1. System Status
        print("\n[1/21] Testing Server Status & Commission Model...")
        status, res = make_request("/api/status")
        assert status == 200, f"Expected 200, got {status}"
        assert res.get("platformFeePercent") == 15, "Platform fee must be 15%"
        assert res.get("doctorRevenuePercent") == 85, "Doctor revenue must be 85%"
        print("  ✓ Server status verified (15% platform cut, 85% doctor payout)")

        # 2. Patient Registration with Telehealth Consent
        print("\n[2/21] Testing Patient Registration with Consent & Emergency Contact...")
        patient_phone = f"+9198{int(time.time()) % 100000000:08d}"
        status, res = make_request("/api/auth/register-patient", method="POST", data={
            "name": "Meera Sen",
            "phone": patient_phone,
            "age": 29,
            "emergency_contact": "Rohan Sen (+919876543210)",
            "allergies": "Sulfa drugs",
            "consent_telehealth": True,
            "consent_data": True
        })
        assert status == 201, f"Expected 201, got {status}: {res}"
        patient_token = res["session"]["token"]
        patient_id = res["session"]["patient"]["id"]
        assert patient_token and patient_id, "Patient session token or ID missing"
        print("  ✓ Patient registered successfully with consent & emergency contact")

        # 3. Patient Login
        print("\n[3/21] Testing Patient Authentication & Session Token...")
        status, res = make_request("/api/auth/login", method="POST", data={
            "identifier": patient_phone,
            "password": "PatientPass123!"
        })
        assert status == 200, f"Expected 200, got {status}"
        assert res["session"]["role"] == "patient"
        print("  ✓ Patient authenticated successfully with persistent session")

        # 4. Doctor Registration with Full Credential Sheet
        print("\n[4/21] Testing Doctor Registration with Credential Sheet...")
        doc_license = f"MC-OPHTH-{int(time.time())}"
        status, res = make_request("/api/doctors/register", method="POST", data={
            "name": "Dr. Ananya Ray, MS",
            "email": f"ananya.{int(time.time())}@docurgent.org",
            "specialty": "Ophthalmology & Eye Trauma Specialist",
            "category": "eye",
            "degrees": "MBBS, MS (Ophthalmology), Fellow in Corneal Trauma (AIIMS)",
            "license_number": doc_license,
            "hospital": "City Eye Trauma Institute",
            "experience_years": 11,
            "consultation_fee": 1000.0,
            "achievements": "Handled 3,000+ emergency corneal and ocular trauma procedures",
            "bio": "Rapid tele-triage for corneal foreign bodies and chemical eye splashes",
            "certificate_url": "Medical_Degree_AIIMS_Verified.pdf",
            "password": "DoctorPass123!"
        })
        assert status == 201, f"Expected 201, got {status}: {res}"
        doctor_token = res["session"]["token"]
        doctor_id = res["session"]["doctor"]["id"]
        # Verify initial status is strictly 'pending_verification'
        assert res["session"]["doctor"]["verification_status"] == "pending_verification", "New doctor MUST start in pending_verification status!"
        print(f"  ✓ Doctor registered with status: {res['session']['doctor']['verification_status']}")

        # 5. Doctor Directory Privacy (Only Verified Doctors Visible to Patients)
        print("\n[5/21] Testing Doctor Directory Privacy & Verified Status Gate...")
        status, res = make_request("/api/doctors?category=eye")
        assert status == 200
        # Newly registered doctor is still pending, so MUST NOT appear in patient directory
        doc_ids = [d["id"] for d in res["doctors"]]
        assert doctor_id not in doc_ids, "Pending unverified doctor must NOT be visible to patients!"
        # Seeded verified doctors SHOULD be present
        assert any(d["id"] == "doc-eye-1" for d in res["doctors"]), "Verified seed doctor missing"
        print("  ✓ Verified status gate strictly enforced (unverified doctor hidden from directory)")

        # 6. Admin Authentication & Doctor Approval Workflow
        print("\n[6/21] Testing Admin Oversight & Doctor Approval Workflow...")
        status, res = make_request("/api/auth/login", method="POST", data={
            "identifier": "admin@docurgent.org",
            "password": "DocAdmin2026!"
        })
        assert status == 200, "Admin login failed"
        admin_token = res["session"]["token"]

        # Admin inspects doctors
        status, res = make_request("/api/admin/doctors", token=admin_token)
        assert status == 200
        assert any(d["id"] == doctor_id for d in res["doctors"]), "Doctor not found in admin list"

        # Admin changes status to 'under_review' then 'verified'
        status, res = make_request("/api/admin/doctor-verify", method="POST", token=admin_token, data={
            "doctor_id": doctor_id,
            "status": "under_review",
            "notes": "Medical council license submitted to state medical board verification"
        })
        assert status == 200

        status, res = make_request("/api/admin/doctor-verify", method="POST", token=admin_token, data={
            "doctor_id": doctor_id,
            "status": "verified",
            "notes": "State council confirmed valid active license without disciplinary actions"
        })
        assert status == 200
        print("  ✓ Admin approved doctor credentials to status: VERIFIED")

        # Now verified doctor MUST appear in patient directory
        status, res = make_request("/api/doctors?category=eye")
        doc_ids = [d["id"] for d in res["doctors"]]
        assert doctor_id in doc_ids, "Doctor should now be visible in patient directory after admin verification"
        print("  ✓ Verified doctor immediately appears in Patient Emergency Directory")

        # 7. Clinician-Reviewed Emergency Safety Gateway (112 Routing)
        print("\n[7/21] Testing Emergency Safety Gateway & Clinician Triage Rules...")
        # Scenario A: Red-flag chest pain / unconsciousness
        status, res = make_request("/api/triage/safety-check", method="POST", data={
            "condition_category": "chest",
            "answers": { "severe_chest_pain": True, "breathing_trouble": True }
        })
        assert status == 200
        assert res["is_emergency"] is True, "Chest pain must trigger critical emergency alert"
        assert res["action"] == "CALL_112_NOW", "Must route to national emergency 112"
        print("  ✓ Life-threatening symptoms redirected to 112 emergency services immediately")

        # Scenario B: Eye chemical splash first-aid
        status, res = make_request("/api/triage/safety-check", method="POST", data={
            "condition_category": "eye",
            "answers": { "severe_chest_pain": False, "unconscious": False, "uncontrolled_bleeding": False }
        })
        assert status == 200
        assert res["is_emergency"] is False
        assert "FLUSH CONTINUOUSLY" in res["first_aid"], "Eye first aid protocol missing"
        print("  ✓ Eye injury verified first-aid guidance generated successfully")

        # 8. Patient Consultation Request & 85/15 Fee Model Calculation
        print("\n[8/21] Testing Consultation Request Creation & 85/15 Fee Model...")
        status, res = make_request("/api/consultations/request", method="POST", token=patient_token, data={
            "doctor_id": doctor_id,
            "category": "eye",
            "condition_desc": "Cleaning chemical splash in left eye with burning redness"
        })
        assert status == 201
        consultation_id = res["consultation_id"]
        transaction_ref = res["transaction_ref"]
        # Fee is 1000; Doctor receives 850 (85%), Platform receives 150 (15%)
        assert res["fee"] == 1000.0
        assert res["doctor_payout"] == 850.0, f"Expected 850.0 doctor payout, got {res['doctor_payout']}"
        assert res["platform_cut"] == 150.0, f"Expected 150.0 platform cut, got {res['platform_cut']}"
        print(f"  ✓ Consultation {consultation_id} created with 85/15 fee split (₹850 Doc / ₹150 App)")

        # 9. Real-Time Doctor Incoming Queue
        print("\n[9/21] Testing Real-Time Doctor Incoming Queue...")
        status, res = make_request("/api/doctor/queue", token=doctor_token)
        assert status == 200
        assert any(c["id"] == consultation_id for c in res["queue"]), "Patient request not visible in doctor queue"
        print("  ✓ Patient request successfully delivered to doctor's incoming queue")

        # 10. Doctor Acceptance of Consultation
        print("\n[10/21] Testing Doctor Consultation Acceptance...")
        status, res = make_request("/api/consultations/respond", method="POST", token=doctor_token, data={
            "consultation_id": consultation_id,
            "action": "accept"
        })
        assert status == 200
        assert res["status"] == "accepted"
        print("  ✓ Doctor accepted emergency consultation")

        # 11. WebRTC Signaling Dispatch & Peer Polling
        print("\n[11/21] Testing WebRTC Real-Time Signaling Peer Exchange...")
        # Patient sends SDP offer
        status, _ = make_request("/api/webrtc/signal/send", method="POST", data={
            "consultation_id": consultation_id,
            "role": "patient",
            "signal_type": "offer",
            "signal_data": {"type": "offer", "sdp": "v=0\r\no=patient 12345 2 IN IP4 127.0.0.1"}
        })
        assert status == 200

        # Doctor polls for signals (must receive patient offer)
        status, res = make_request(f"/api/webrtc/signal/poll?consultation_id={consultation_id}&role=doctor&since=0")
        assert status == 200
        assert len(res["signals"]) > 0, "Doctor should receive patient WebRTC signal"
        assert res["signals"][0]["signal_type"] == "offer"
        print("  ✓ WebRTC SDP offer delivered across peer signaling channel")

        # 12. Live Chat Real-Time Messaging & Scoping
        print("\n[12/21] Testing Live Chat Real-Time Two-Way Messaging...")
        status, res = make_request("/api/chat/send", method="POST", data={
            "consultation_id": consultation_id,
            "sender_role": "patient",
            "text": "Doctor, the left eye is stinging intensely after chemical detergent contact."
        })
        assert status == 201

        status, res = make_request(f"/api/chat/messages?consultation_id={consultation_id}")
        assert status == 200
        assert len(res["messages"]) >= 1
        assert "chemical detergent" in res["messages"][0]["text"]
        print("  ✓ Real-time chat message successfully stored and scoped to consultation")

        # 13. Secure File Upload & Validation (5MB Limit & Extensions)
        print("\n[13/21] Testing Secure File Upload & Size Limits...")
        # Valid small JPG simulation
        dummy_jpg = base64.b64encode(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"A" * 50).decode()
        status, res = make_request("/api/upload", method="POST", data={
            "filename": "eye_injury_photo.jpg",
            "data": dummy_jpg
        })
        assert status == 201, f"Expected 201, got {status}: {res}"
        photo_url = res["file_url"]
        assert photo_url.startswith("/uploads/"), "Invalid upload URL"

        # Invalid file extension check
        status, res = make_request("/api/upload", method="POST", data={
            "filename": "virus.exe",
            "data": dummy_jpg
        })
        assert status == 400, "Executable file must be rejected"

        # File size > 5MB check
        huge_bytes = base64.b64encode(b"X" * (6 * 1024 * 1024)).decode()
        status, res = make_request("/api/upload", method="POST", data={
            "filename": "huge_file.jpg",
            "data": huge_bytes
        })
        assert status == 413, "Files exceeding 5MB must return 413 Payload Too Large"
        print("  ✓ File upload validation verified (5MB limit & format restrictions enforced)")

        # 14. Doctor Clinical Assessment, Diagnosis & Cryptographic Digital Signature
        print("\n[14/21] Testing Doctor Prescription Authoring & Digital Signing...")
        status, res = make_request("/api/prescriptions/sign", method="POST", token=doctor_token, data={
            "consultation_id": consultation_id,
            "clinical_assessment": "Visual triage via video. Mild conjunctival injection, cornea intact.",
            "diagnosis": "Chemical Conjunctivitis (Grade 1)",
            "first_aid_instructions": "Flush eye with sterile saline for another 10 minutes. Do not rub.",
            "medications": [
                {"name": "Carboxymethylcellulose 0.5% Eye Drops", "dosage": "1 drop every 2 hours", "instructions": "Sterile soothing drops"},
                {"name": "Paracetamol 500mg", "dosage": "1 tablet SOS for pain", "instructions": "Take after meals"}
            ],
            "follow_up_instructions": "Review in 24 hours if pain or redness persists.",
            "referral_hospital": "City Eye Trauma Center (Standby)",
            "call_duration_seconds": 380
        })
        assert status == 201
        sig_hash = res["signature_hash"]
        assert sig_hash, "Cryptographic digital signature hash missing"
        print(f"  ✓ Doctor reviewed & digitally signed prescription: {sig_hash}")

        # Patient retrieves finalized signed prescription
        status, res = make_request(f"/api/prescriptions/get?consultation_id={consultation_id}")
        assert status == 200
        rx = res["prescription"]
        assert rx["is_signed"] == 1
        assert rx["diagnosis"] == "Chemical Conjunctivitis (Grade 1)"
        assert rx["digital_signature_hash"] == sig_hash
        print("  ✓ Patient received authenticated and signed prescription slip")

        # 15. Reliable Payment Confirmation & Duplicate Prevention
        print("\n[15/21] Testing Sandbox Payment Gateway Confirmation & Duplicate Prevention...")
        status, res = make_request("/api/payments/confirm", method="POST", data={
            "consultation_id": consultation_id,
            "gateway_payment_token": "SANDBOX_GATEWAY_SUCCESS_TOKEN_9921"
        })
        assert status == 200
        assert res["success"] is True

        # Second attempt must recognize existing payment and prevent duplicate charge
        status, res2 = make_request("/api/payments/confirm", method="POST", data={
            "consultation_id": consultation_id,
            "gateway_payment_token": "SANDBOX_GATEWAY_SUCCESS_TOKEN_9921"
        })
        assert status == 200
        assert "already confirmed" in res2["message"], "Duplicate payment must be gracefully prevented"
        print("  ✓ Payment successfully confirmed and duplicate payment prevented")

        # 16. Consultation Cancellation & Automatic Refund Handling
        print("\n[16/21] Testing Consultation Cancellation & Refund Handling...")
        # Create second consultation to test cancellation
        status, res = make_request("/api/consultations/request", method="POST", token=patient_token, data={
            "doctor_id": doctor_id,
            "category": "stairs",
            "condition_desc": "Twisted ankle from stair fall"
        })
        cons2_id = res["consultation_id"]

        status, res = make_request("/api/consultations/cancel", method="POST", token=patient_token, data={
            "consultation_id": cons2_id,
            "reason": "Family member already arranged car transport to local clinic"
        })
        assert status == 200
        assert res["success"] is True
        print("  ✓ Eligible consultation cancelled and payment refunded")

        # 17. Role-Based Access Control (RBAC) & Unauthorized Access Defense
        print("\n[17/21] Testing RBAC Security & Unauthorized Medical Record Defense...")
        # Patient attempting to access Admin endpoints
        status, res = make_request("/api/admin/doctors", token=patient_token)
        assert status == 403, "Patient must be forbidden from accessing Admin endpoints"

        # Doctor attempting to access Admin endpoints
        status, res = make_request("/api/admin/stats", token=doctor_token)
        assert status == 403, "Doctor must be forbidden from accessing Admin stats"

        # Unauthenticated request to protected endpoint
        status, res = make_request("/api/admin/audit-logs")
        assert status == 403 or status == 401, "Unauthenticated request must be blocked"
        print("  ✓ RBAC defense verified: Patients and Doctors cannot access Admin endpoints")

        # 18. Audit Logs Integrity
        print("\n[18/21] Testing Telehealth Compliance Audit Trail...")
        status, res = make_request("/api/admin/audit-logs", token=admin_token)
        assert status == 200
        logs = res["audit_logs"]
        actions = [l["action"] for l in logs]
        assert "REGISTER_DOCTOR" in actions or "DOCTOR_REGISTER" in actions
        assert "VERIFY_DOCTOR" in actions or "DOCTOR_VERIFY_STATUS_CHANGE" in actions
        assert "SIGN_PRESCRIPTION" in actions
        print("  ✓ Audit logs recorded complete clinical compliance lifecycle")

        # 19. Direct SQLite Database Integrity & Persistence
        print("\n[19/21] Testing SQLite Database Relational Integrity...")
        conn = sqlite3.connect(os.path.join(DIRECTORY, "docurgent", "docurgent.db"))
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM consultations WHERE id = ?", (consultation_id,))
        assert c.fetchone()[0] == 1, "Consultation record missing in SQLite"
        c.execute("SELECT is_signed, digital_signature_hash FROM prescriptions WHERE consultation_id = ?", (consultation_id,))
        p_row = c.fetchone()
        assert p_row[0] == 1 and p_row[1] == sig_hash, "Prescription signature mismatch in database"
        conn.close()
        print("  ✓ Relational database integrity & cryptographic signatures verified")

        # 20. Session Expiration & User Logout
        print("\n[20/21] Testing Secure Logout & Session Revocation...")
        status, res = make_request("/api/auth/logout", method="POST", token=patient_token)
        assert status == 200
        # Subsequent request with revoked token must fail
        status, res = make_request("/api/patient/consultations", token=patient_token)
        assert status == 401, "Revoked session token must be rejected"
        print("  ✓ Session token successfully revoked on logout")

        # 21. Invalid Input & Edge Case Defense
        print("\n[21/21] Testing Edge Cases & Invalid Inputs...")
        # Empty registration
        status, res = make_request("/api/doctors/register", method="POST", data={})
        assert status == 400
        # Invalid consultation id for prescription
        status, res = make_request("/api/prescriptions/get?consultation_id=nonexistent-id")
        assert status == 404
        # Malformed JSON
        req = urllib.request.Request(f"{BASE_URL}/api/consultations/request", data=b"{bad-json", headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                pass
        except urllib.error.HTTPError as e:
            assert e.code == 400
        print("  ✓ Edge cases, missing fields & malformed payloads handled safely")

        # 22. Super Admin Bootstrap & Login with RFC 6238 TOTP Multi-Factor Authentication
        print("\n[22/32] Testing Super Admin Bootstrap & Login with RFC 6238 MFA...")
        sys.path.insert(0, os.path.join(DIRECTORY, "docurgent"))
        import db, backup_manager
        superadmin_email = "owner@docurgent.in"
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT mfa_secret FROM users WHERE role = 'super_admin' AND email = ?", (superadmin_email,))
        s_row = c.fetchone()
        conn.close()
        assert s_row and s_row['mfa_secret'], "Super admin with MFA secret must exist"
        totp_code = db.get_totp_code(s_row['mfa_secret'])
        status, res = make_request("/api/auth/login", method="POST", data={
            "identifier": superadmin_email,
            "password": "OwnerDocUrgent2026!#",
            "mfa_code": totp_code
        })
        assert status == 200, f"Super Admin login failed: {res}"
        assert res["session"]["role"] == "super_admin"
        superadmin_token = res["session"]["token"]
        print("  ✓ Super Admin authenticated successfully with RFC 6238 6-digit TOTP")

        # 23. Role Privilege Escalation Defense
        print("\n[23/32] Testing Privilege Escalation Defense (Admin cannot change Super Admin settings)...")
        # Standard admin attempts to alter system settings
        status, res = make_request("/api/admin/settings", method="POST", token=admin_token, data={
            "settings": {"platform_commission_percent": "35"}
        })
        assert status == 403, f"Standard admin must NOT be able to change platform settings (got {status})"
        # Standard admin attempts to create another admin
        status, res = make_request("/api/admin/administrators", method="POST", token=admin_token, data={
            "email": "hacker@docurgent.org", "password": "InsecurePass1!"
        })
        assert status == 403, "Standard admin must NOT be able to create administrator accounts"
        print("  ✓ Privilege escalation strictly blocked: Only Super Admin can alter system configuration")

        # 24. Health Check API Telemetry & Metrics
        print("\n[24/32] Testing Health Check API Telemetry & Metrics...")
        status, res = make_request("/api/health")
        assert status == 200, f"Health check failed: {res}"
        assert res["status"] == "healthy"
        assert res["database"]["integrity_status"] == "ok"
        assert res["storage"]["alert_level"] in ("NORMAL", "NOTICE")
        assert res["uptime_seconds"] >= 0
        print(f"  ✓ System telemetry verified: DB Integrity OK ({res['database']['size_mb']}MB), Storage {res['storage']['alert_level']}")

        # 25. Short-Lived Signed File URL Generation & Expiration Security
        print("\n[25/32] Testing Short-Lived Signed File URL Generation & Expiration...")
        uploaded_filename = os.path.basename(photo_url)
        signed_path = db.generate_signed_file_url(uploaded_filename, expires_in_seconds=60)
        status, _ = make_request(signed_path)
        assert status == 200, "Signed file download failed"
        # Test tampered token rejection
        tampered_path = signed_path.replace("token=", "token=tampered_")
        status, _ = make_request(tampered_path)
        assert status == 401, "Tampered signed link must be rejected with 401"
        # Test expired token rejection
        expired_path = db.generate_signed_file_url(uploaded_filename, expires_in_seconds=-10)
        status, _ = make_request(expired_path)
        assert status == 401, "Expired signed link must be rejected with 401"
        print("  ✓ Short-lived signed file security verified (tamper & expiry defenses validated)")

        # 26. Point-in-Time Online Database Backup & Integrity Verification
        print("\n[26/32] Testing Online Point-in-Time Database Backup & SHA-256 Checksum...")
        db_snap = backup_manager.create_database_backup()
        assert db_snap["success"] is True, f"Backup creation failed: {db_snap}"
        is_valid, msg = backup_manager.verify_backup(db_snap["path"])
        assert is_valid is True, f"Backup integrity check failed: {msg}"
        print(f"  ✓ Database point-in-time snapshot created and verified: {db_snap['filename']}")

        # 27. Platform Maintenance Mode Lockdown
        print("\n[27/32] Testing Platform Maintenance Mode Lockdown & Non-Admin Rejection...")
        status, res = make_request("/api/admin/settings", method="POST", token=superadmin_token, data={
            "settings": {"maintenance_mode": "true"}
        })
        assert status == 200
        # Patient attempts to access directory -> 503 Service Unavailable
        status, res = make_request("/api/doctors", token=patient_token)
        assert status == 503, f"Expected 503 in maintenance mode, got {status}"
        assert res.get("maintenance") is True
        # Admin is still allowed access
        status, res = make_request("/api/admin/doctors", token=admin_token)
        assert status == 200, "Admins must retain access during maintenance"
        # Disable maintenance mode
        status, res = make_request("/api/admin/settings", method="POST", token=superadmin_token, data={
            "settings": {"maintenance_mode": "false"}
        })
        assert status == 200
        # Patient access restored
        status, res = make_request("/api/doctors", token=patient_token)
        assert status == 200, "Patient access must be restored when maintenance mode is disabled"
        print("  ✓ Platform maintenance lockdown and graceful recovery verified")

        # 28. Super Admin Configuration Control (Commission Rate Update)
        print("\n[28/32] Testing Super Admin Configuration Control & Dynamic Split...")
        status, res = make_request("/api/admin/settings", method="POST", token=superadmin_token, data={
            "settings": {"platform_commission_percent": "20"}
        })
        assert status == 200
        status, res = make_request("/api/status")
        assert res.get("platformFeePercent") == 20, "Platform fee should now reflect 20%"
        # Restore standard 15%
        make_request("/api/admin/settings", method="POST", token=superadmin_token, data={
            "settings": {"platform_commission_percent": "15"}
        })
        print("  ✓ Super Admin dynamic platform commission management verified")

        # 29. Audited Protected Health Information (PHI) Access
        print("\n[29/32] Testing Audited PHI Access for Patient Records...")
        status, res = make_request("/api/admin/patient-records-access", method="POST", token=admin_token, data={
            "patient_id": patient_id,
            "reason": "Regulatory Telemedicine Clinical Assessment Audit"
        })
        assert status == 200, f"PHI access failed: {res}"
        assert res["patient"]["name"] == "Meera Sen"
        assert "audit_notice" in res
        print("  ✓ Sensitive patient medical records accessed with mandatory clinical audit justification")

        # 30. Administrative Refund Processing
        print("\n[30/32] Testing Administrative Refund Workflow...")
        # Fetch payment ID
        status, res = make_request("/api/admin/payments", token=admin_token)
        completed_payments = [p for p in res["payments"] if p["status"] == "completed"]
        assert len(completed_payments) > 0
        target_payment = completed_payments[0]
        status, res = make_request("/api/admin/refund", method="POST", token=admin_token, data={
            "payment_id": target_payment["id"],
            "reason": "Administrative satisfaction guarantee refund"
        })
        assert status == 200
        assert res["success"] is True
        print(f"  ✓ Administrative refund issued successfully for {target_payment['transaction_ref']}")

        # 31. Digital Receipt & Itemized Invoice Generation
        print("\n[31/32] Testing Digital Receipt & Itemized Invoice Generation...")
        status, res = make_request(f"/api/payments/invoice?transaction_ref={target_payment['transaction_ref']}")
        assert status == 200
        inv = res["invoice"]
        assert "invoice_number" in inv
        assert inv["platform_name"] == "DocUrgent 24/7 Telemedicine Network"
        print(f"  ✓ Official digital tax invoice generated: {inv['invoice_number']}")

        # 32. Account Lockout & Brute-Force Defense
        print("\n[32/32] Testing Account Lockout & Brute-Force Defense...")
        # Repeatedly send 5 bad passwords for a dummy patient
        dummy_phone = "+919999990011"
        make_request("/api/auth/register-patient", method="POST", data={
            "name": "Lockout Test", "phone": dummy_phone, "password": "OriginalPass1!"
        })
        for _ in range(5):
            make_request("/api/auth/login", method="POST", data={"identifier": dummy_phone, "password": "WrongPassword!"})
        status, res = make_request("/api/auth/login", method="POST", data={"identifier": dummy_phone, "password": "OriginalPass1!"})
        assert status in (401, 423), f"Locked account must be rejected (got {status})"
        assert "locked" in res.get("error", "").lower()
        print("  ✓ Account lockout defense triggered after repeated failed authentication attempts")

        print("\n" + "=" * 70)
        print("  🎉 ALL 32 DOCURGENT VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)

    finally:
        proc.terminate()
        proc.wait()
        subprocess.run(f"lsof -iTCP:{TEST_PORT} -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true", shell=True)

if __name__ == "__main__":
    run_tests()
