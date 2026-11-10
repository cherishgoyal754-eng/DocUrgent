# 🏥 DocUrgent 24/7 — Production Healthcare Telehealth Platform

> **Emergency-First Doctor-Patient Consultation Network & Clinical Triage Platform**  
> Connect patients experiencing urgent home accidents, eye chemical exposures, stair falls, fractures, burns, and deep bleeding to board-verified medical doctors within seconds.

---

## 🌟 Architecture & Ownership Overview

DocUrgent is engineered with strict adherence to **UI preservation**—maintaining the clean, trustworthy light clinical theme (white, blue, slate, coral, emerald), layouts, cards, and portals—backed by a resilient, production-ready, security-audited infrastructure.

```
                    ┌────────────────────────┐
                    │      "WHO ARE YOU?"    │
                    │   Authentication Gate   │
                    └───────────┬────────────┘
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐
│  PATIENT PORTAL  │  │  DOCTOR PORTAL   │  │    ADMIN / SUPER ADMIN   │
│ • Emergency Gate │  │ • Credential Sheet│ │ • Doctor Verifications   │
│ • Safety Check   │  │   (Comes First!) │  │ • Audited PHI Access     │
│ • Doctor Match   │  │ • 5 Status Badges│  │ • Financial & Commission │
│ • WebRTC Video   │  │ • Live Call Queue│  │ • Emergency Maintenance  │
│ • Live Chat/Photo│  │ • Clinical Rx Pad│  │ • Automated Snapshots    │
│ • Signed Rx Slip │  │ • Net 85% Payout │  │ • Storage & DB Health    │
└──────────────────┘  └──────────────────┘  └──────────────────────────┘
                                │
                 ┌──────────────┴──────────────┐
                 ▼                             ▼
       ┌──────────────────┐          ┌───────────────────┐
       │   SQLite3 WAL    │          │  WebRTC Signaling │
       │ docurgent.db     │          │  & Signed Storage │
       └──────────────────┘          └───────────────────┘
```

---

## 1. 🔒 Production Infrastructure & Security (Phases 1 - 10)

| Security Capability | Implementation | Status |
| :--- | :--- | :---: |
| **Role-Based Access Control** | 4 Roles (`patient`, `doctor`, `admin`, `super_admin`) with privilege escalation defense. | ✅ Active |
| **Super Admin Ownership** | CLI bootstrap tool (`bootstrap_superadmin.py`) with masked inputs & account recovery. | ✅ Active |
| **Multi-Factor Auth (MFA)** | Standard RFC 6238 TOTP (Google Authenticator / Apple Passwords) + 8 emergency recovery codes. | ✅ Active |
| **Rate Limiting & Lockout** | Token-bucket rate limiter + 15-minute account lockout after 5 consecutive failed attempts. | ✅ Active |
| **Private File Storage** | HMAC-SHA256 short-lived signed URLs (15-min expiry) for patient photos & certificates. | ✅ Active |
| **Automated Backups** | Online zero-downtime database snapshots + compressed tar.gz media backups with SHA-256 sidecars. | ✅ Active |
| **Emergency Maintenance** | Dynamic platform lockdown (503 with 112 emergency routing for patients; full admin access). | ✅ Active |
| **Audit Trails & PHI Access** | Mandatory regulatory logging for all logins, prescriptions, payments, and audited PHI accesses. | ✅ Active |
| **Cloud Storage Readiness** | Turn-key PostgreSQL/Supabase schema (`schema_supabase.sql`) with Row-Level Security (RLS). | ✅ Active |
| **CI/CD Automation** | GitHub Actions workflow (`.github/workflows/ci.yml`) running the 32-point verification suite. | ✅ Active |

---

## 2. 📚 Comprehensive Technical Documentation

Complete operational and architecture runbooks are available in the **`docs/`** directory:

1. [**INSTALLATION.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/INSTALLATION.md) — Local workstation and developer environment setup.
2. [**DEPLOYMENT.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/DEPLOYMENT.md) — Cloud Run, Vercel, Supabase, and custom domain (`docurgent.in`) configuration.
3. [**ADMIN_GUIDE.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/ADMIN_GUIDE.md) — Day-to-day administrative operations, doctor approvals, and platform management.
4. [**BACKUP_AND_RECOVERY.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/BACKUP_AND_RECOVERY.md) — Backup schedules, snapshot triggers, and disaster recovery procedures.
5. [**SECURITY.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/SECURITY.md) — HIPAA/telemedicine compliance, PBKDF2 hashing, TOTP MFA, and PHI isolation.
6. [**DATABASE_STRUCTURE.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/DATABASE_STRUCTURE.md) — Relational schema, tables, foreign keys, and ER diagram.
7. [**ENVIRONMENT_SETUP.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/ENVIRONMENT_SETUP.md) — Supported environment variables and secret rotation runbooks.
8. [**MAINTENANCE.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/MAINTENANCE.md) — Routine operations, maintenance mode, and SQLite VACUUM optimization.
9. [**TROUBLESHOOTING.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/TROUBLESHOOTING.md) — Diagnostic guide for port conflicts, account recovery, and WebRTC.
10. [**ROLLBACK_INSTRUCTIONS.md**](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/ROLLBACK_INSTRUCTIONS.md) — Rapid code, database, and storage rollback instructions.

---

## 3. 🚀 Quick Start Guide

### Step 1: Start DocUrgent Server
- **macOS One-Click**: Double-click `Launch_DocUrgent.command` in the project root.
- **Terminal Execution**:
  ```bash
  cd docurgent
  python3 server.py
  ```
The application will launch at **`http://localhost:8095`**.

### Step 2: Super Admin Account Bootstrap & Recovery
To bootstrap or recover the platform owner Super Admin account:
```bash
python3 bootstrap_superadmin.py --email "owner@docurgent.in" --password "YourStrongPassword2026!#" --reset
```
This utility outputs:
- Owner Email & Role (`super_admin`)
- 32-character RFC 6238 Base32 MFA Secret
- Authenticator QR Setup URI
- 8 single-use emergency recovery codes

### Step 3: Run the 32-Point Verification Test Suite
```bash
python3 ../test_docurgent.py
```
Expected output:
```text
🎉 ALL 32 DOCURGENT VERIFICATION TESTS PASSED SUCCESSFULLY!
```

---

## 4. 💰 Financial & Commission Operations

- **Configurable Split**: Super Admin can dynamically set the commission percentage via the Admin Portal or API (default: 85% to verified doctors, 15% platform cut).
- **Payment Sandbox**: Full checkout confirmation with duplicate transaction protection.
- **Refund Processing**: Instant refunds can be initiated by administrators via the financial ledger.
- **Tax Invoices**: Structured digital invoices generated via `/api/payments/invoice?transaction_ref=...`.

---

## 5. 🏥 Telemedicine Regulatory Guidelines Notice

DocUrgent complies with:
- Clinician-reviewed emergency triage gateway (instant physical ER / 112 redirection for chest pain, unconsciousness, severe hemorrhage).
- Clear clinician identification, degree verification, and medical council registration display.
- Cryptographically signed digital prescriptions with HMAC SHA-256 signature hashes.
- Mandatory audit logging of all patient-doctor encounters and PHI data access.
