# 🏥 DocUrgent 24/7 — Emergency-First Telehealth & Clinical Triage Platform

> **Instant Urgent Care Access**: Connect patients facing acute home accidents (eye chemical splashes, stair falls, fractures, burns, deep cuts) to board-verified medical specialists within seconds.

🌐 **Live Demo**: https://docurgent-vercel.vercel.app  
📦 **Repository**: https://github.com/cherishgoyal754-eng/DocUrgent  
🧪 **Automated Verification**: **32 / 32** End-to-End Tests Passing

---

## 🎯 Why DocUrgent?

In acute accidents, patients do not need an appointment calendar for next week—they need immediate emergency guidance, safe triage, and real-time connection with an available verified specialist:

- **Role-Separated Portals**: Dedicated Entry Gate routing directly into **Patient Emergency Care**, **Doctor Credentialing & Workspace**, or **Admin Oversight**.
- **Clinician-Reviewed Emergency Safety Gateway**: Screens immediately for life-threatening red flags (unconsciousness, severe chest pain, uncontrolled bleeding, respiratory distress) and directs critical emergencies to **112 / 102** before queuing a teleconsultation.
- **Verified Doctor Gate**: Doctors submit degrees, state medical council license numbers, hospital affiliations, achievements, and consultation fees. Unverified clinicians stay hidden from patients until approved by an administrator.
- **Transparent 85 / 15 Financial Model**: Patients see exact consultation fees upfront; verified doctors retain **85%** with a **15%** platform triage commission tracked per transaction.
- **Real-Time WebRTC Video + Clinical Chat**: Live browser audio/video room (`RTCPeerConnection`) with audio/chat fallback, consultation-scoped messaging, signed image sharing, and **HMAC-SHA256 digitally signed prescriptions**.

---

## 🏗️ System Architecture

```text
                       ┌──────────────────────────────────┐
                       │      DocUrgent 24/7 Entry Gate   │
                       └─────────────────┬────────────────┘
            ┌────────────────────────────┼────────────────────────────┐
            ▼                            ▼                            ▼
  ┌───────────────────┐       ┌─────────────────────┐      ┌──────────────────────┐
  │  PATIENT PORTAL   │       │    DOCTOR PORTAL    │      │  ADMIN / SUPER ADMIN │
  │ • Injury Filters  │       │ • Credential Sheet  │      │ • License Approval   │
  │ • 112 Safety Gate │       │ • Live Queue Alerts │      │ • Audited PHI Logs   │
  │ • Verified Match  │       │ • WebRTC & Chat     │      │ • 85/15 Ledger       │
  │ • Signed Rx Slip  │       │ • Digital Rx Pad    │      │ • Backups & Vacuum   │
  └───────────────────┘       └─────────────────────┘      └──────────────────────┘
                                         │
                        ┌────────────────┴────────────────┐
                        ▼                                 ▼
              ┌───────────────────┐             ┌───────────────────┐
              │ SQLite3 WAL /     │             │ WebRTC Signaling  │
              │ Supabase Schema   │             │ & Signed Storage  │
              └───────────────────┘             └───────────────────┘
```

### Tech Stack
- **Frontend**: Vanilla HTML5, CSS3 (Light Clinical Theme), ECMAScript (`docurgent/index.html`, `docurgent/styles.css`, `docurgent/app.js`)
- **Backend**: Pure Python 3 standard library (`socketserver.ThreadingTCPServer`, `http.server`, zero external runtime dependencies)
- **Database**: SQLite3 WAL mode locally (`docurgent/db.py`), plus Supabase PostgreSQL + Row-Level Security schema ready in [`docurgent/schema_supabase.sql`](../docurgent/schema_supabase.sql)
- **Serverless Cloud Deployment**: Vercel static Edge CDN (`public/`) + Python Serverless wrapper (`docurgent-vercel/api/router.py`)
- **CI/CD**: GitHub Actions running syntax checks and the 32-point test suite (`.github/workflows/ci.yml`)

---

## 🔒 Security & Compliance Highlights

| Layer | Implementation |
| :--- | :--- |
| **Password Security** | PBKDF2-SHA256 with 100,000 iterations and unique 16-byte per-user salts |
| **Multi-Factor Auth (MFA)** | Pure Python RFC 6238 6-digit TOTP + single-use emergency recovery codes for Super Admin |
| **Brute-Force Protection** | Token-bucket IP rate limiter + 15-minute account lockout after 5 failed attempts |
| **Role-Based Access Control** | Strict separation across `patient`, `doctor`, `admin`, and `super_admin` |
| **Signed File Downloads** | Magic-byte upload validation + short-lived HMAC-SHA256 signed download URLs |
| **Prescription Integrity** | Tamper-evident HMAC-SHA256 digital signature hashes on every signed Rx |
| **Compliance Audit Trail** | Immutable `audit_logs` tracking logins, approvals, PHI accesses, refunds, and settings changes |

---

## 🚀 Quick Start (Local Development)

### 1. Run Locally (macOS / Linux / Windows)
```bash
git clone https://github.com/cherishgoyal754-eng/DocUrgent.git
cd DocUrgent/docurgent
python3 server.py
```
Open **`http://localhost:8095`** in your browser *(or double-click `Launch_DocUrgent.command` on macOS)*.

### 2. Run the 32-Point Automated Verification Suite
Tests execute cleanly against an isolated temporary SQLite copy so local data stays untouched:
```bash
python3 test_docurgent.py
```

### 3. Bootstrap or Reset Super Admin Account (Optional)
Configure secrets in `.env` from [`docurgent/.env.example`](../docurgent/.env.example), then run:
```bash
python3 docurgent/bootstrap_superadmin.py --email "owner@docurgent.in" --reset
```

### 4. Deploy to Vercel
```bash
./deploy_docurgent_to_vercel.command
```

---

## 📂 Repository Structure

```text
DocUrgent/
├── .github/
│   ├── README.md                    # Project overview (displayed on GitHub)
│   └── workflows/ci.yml             # Automated GitHub Actions CI verification
├── docurgent/                       # Primary full-stack application
│   ├── index.html                   # SPA portals, triage modals & video room
│   ├── styles.css                   # Light clinical theme & responsive UI
│   ├── app.js                       # Client controller, WebRTC & chat logic
│   ├── server.py                    # Multi-threaded REST API & static server
│   ├── db.py                        # Relational SQLite engine, PBKDF2 & TOTP MFA
│   ├── backup_manager.py            # Point-in-time DB snapshots & SHA-256 checks
│   ├── bootstrap_superadmin.py      # Owner account provisioning CLI
│   ├── schema_supabase.sql          # Managed PostgreSQL + RLS migration schema
│   ├── Dockerfile                   # Non-root container image for Cloud Run
│   └── docs/                        # 10 operational & security runbooks
├── docurgent-vercel/                # Isolated Vercel CDN + Python Serverless bundle
│   ├── api/router.py                # Rewritten serverless API wrapper
│   ├── public/                      # Static CDN assets
│   └── vercel.json                  # Edge rewrites & private bundle config
├── test_docurgent.py                # 32-point automated end-to-end test suite
├── DOCURGENT_PRODUCT_AUDIT.md       # Full 10-dimension product audit & roadmap
└── INFRASTRUCTURE_AUDIT.md          # Cloud, security & India pilot architecture
```

---

## 📚 Additional Documentation

- [Product Audit & Differentiation Blueprint](../DOCURGENT_PRODUCT_AUDIT.md)
- [Infrastructure & Security Audit](../INFRASTRUCTURE_AUDIT.md)
- [Installation Guide](../docurgent/docs/INSTALLATION.md) | [Deployment Guide](../docurgent/docs/DEPLOYMENT.md) | [Security Architecture](../docurgent/docs/SECURITY.md) | [Database Schema](../docurgent/docs/DATABASE_STRUCTURE.md)
