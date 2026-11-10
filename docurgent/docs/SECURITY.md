# DocUrgent — Platform Security & Compliance Architecture

This document describes the security controls, cryptographic implementations, authentication mechanisms, and regulatory compliance standards embedded within DocUrgent.

---

## 1. Regulatory Compliance Standards

DocUrgent is designed to align with:
- **HIPAA Security & Privacy Rule** (45 CFR Part 160 and Part 164)
- **Indian Telemedicine Practice Guidelines (2020)** issued by the Ministry of Health and Family Welfare (MoHFW) / NITI Aayog
- **GDPR** Data Protection Principles (Privacy by Design)

---

## 2. Authentication & Access Control (RBAC)

DocUrgent implements a strict four-tier Role-Based Access Control model:

| Role | Permissions & Access Scope |
| :--- | :--- |
| **Patient** | Register, complete emergency triage, request emergency consultation, pay fees, view signed prescriptions, live video/chat. |
| **Doctor** | Register with credential sheet, undergo administrative license review, accept/decline emergency queue calls, author & digitally sign clinical prescriptions, view net earnings ledger. |
| **Admin** | Inspect doctor medical certificates, verify/reject/suspend doctor accounts, view platform statistics, review complaints, audited PHI inspection. |
| **Super Admin** | Platform Owner authority: manage administrator accounts, update platform commission %, toggle emergency maintenance mode, optimize database, configure storage quotas. |

### Protection Against Privilege Escalation
- User registration endpoints strictly hardcode roles to `patient` and `doctor` (`pending_verification`).
- Standard administrators are blocked with `403 Forbidden` from modifying platform configuration or granting administrator rights.
- Super Admin accounts can only be created via the secure server-side CLI (`bootstrap_superadmin.py`).

---

## 3. Cryptography & Password Security

- **Password Hashing**: PBKDF2 with SHA-256 HMAC and 100,000 iterations using unique 16-byte cryptographic salts per user (`hashlib.pbkdf2_hmac`).
- **Timing Attack Resistance**: All hash and token comparisons use constant-time comparison via `secrets.compare_digest`.
- **Multi-Factor Authentication (MFA)**: RFC 6238 standard Time-Based One-Time Passwords (TOTP) compatible with Google Authenticator, Authy, Apple Passwords, and 1Password.
- **Emergency Recovery Codes**: 8 single-use cryptographically hashed backup recovery codes stored as SHA-256 hashes.

---

## 4. Protected Health Information (PHI) & Private Storage

- **Short-Lived Signed URLs**: Patient injury photos and doctor certificates are accessible only via HMAC-SHA256 signed download tokens expiring in 15 minutes (`/api/files/download?file=...&token=...&expires=...`).
- **Separation of Concerns**: Large binary media files are stored on secure object storage, never stored as raw blobs inside the relational database.
- **Audited PHI Inspection**: When an administrator inspects a patient's protected medical record, they must submit a clinical justification reason, which is permanently logged in `audit_logs`.
- **Path Traversal Defense**: All file requests are sanitized using `os.path.basename` and validated against directory boundaries.

---

## 5. Brute-Force & Rate Limiting Defense

- **Rate Limiter**: Token-bucket algorithm per client IP address (25 auth requests/min, 240 general requests/min). Exceeding requests receive `429 Too Many Requests`.
- **Account Lockout**: 5 consecutive failed login attempts automatically lock the user account for 15 minutes (`locked_until`).
