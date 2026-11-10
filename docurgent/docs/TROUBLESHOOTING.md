# DocUrgent — Diagnostic & Troubleshooting Guide

This guide provides immediate solutions to common operational, networking, and authentication errors encountered in DocUrgent.

---

## 1. Port 8095 Conflict ("Address already in use")

### Symptom:
Starting the server displays `OSError: [Errno 48] Address already in use`.

### Cause:
A previous DocUrgent server process is still bound to port 8095.

### Resolution:
```bash
# Locate and terminate the process on port 8095:
kill -9 $(lsof -ti:8095)

# Restart DocUrgent:
python3 docurgent/server.py
```

---

## 2. Super Admin Account Locked / Password Lost

### Symptom:
Super Admin cannot authenticate, error displays `Account temporarily locked due to consecutive failed attempts` or password has been forgotten.

### Resolution:
Use the server-side CLI bootstrap utility to recover and reset the account without data loss:
```bash
python3 docurgent/bootstrap_superadmin.py --email "owner@docurgent.in" --password "NewSecurePassword2026!#" --reset
```
This utility:
- Unlocks the account immediately (`failed_login_attempts = 0`, `locked_until = NULL`).
- Sets the new strong password.
- Displays a new RFC 6238 Base32 MFA secret and 8 single-use recovery codes.

---

## 3. Database Locked Error (`sqlite3.OperationalError: database is locked`)

### Symptom:
A query fails with `database is locked`.

### Cause:
A long-running query or uncommitted transaction is holding an exclusive write lock.

### Resolution:
DocUrgent uses Write-Ahead Logging (WAL) and `PRAGMA busy_timeout = 5000` to prevent locks. If a lock occurs:
1. Verify WAL mode is active:
   ```bash
   python3 -c "import db; conn=db.get_connection(); print(conn.execute('PRAGMA journal_mode').fetchall())"
   ```
2. Ensure checkpointing completes:
   ```bash
   python3 -c "import db; conn=db.get_connection(); conn.execute('PRAGMA wal_checkpoint(TRUNCATE)'); conn.close()"
   ```

---

## 4. WebRTC Video / Audio Peer Connection Issues

### Symptom:
Consultation opens but video/audio peer stream does not establish.

### Diagnosis:
1. WebRTC requires STUN/TURN servers to traverse Symmetric NAT or corporate firewalls.
2. In local test environments, ensure both browser tabs are running on `localhost` or via HTTPS (WebRTC requires a Secure Context).
3. Check signaling exchange:
   ```bash
   curl "http://localhost:8095/api/webrtc/signal/poll?consultation_id=[ID]&role=doctor&since=0"
   ```

---

## 5. Signed File Download Returns 401 Unauthorized

### Symptom:
Clicking an injury photo or certificate download link returns `401 Signed file link is invalid or has expired`.

### Cause:
Short-lived signed links expire after 15 minutes (900 seconds) for patient privacy compliance.

### Resolution:
Generate a fresh signed link by refreshing the page or fetching a new signed URL from the API.
