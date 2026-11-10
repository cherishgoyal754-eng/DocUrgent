# DocUrgent — Super Admin & Medical Director Operational Guide

This guide is designed for the platform owner (Super Admin) and Medical Board Directors to manage DocUrgent on a day-to-day basis.

---

## 1. Accessing the Admin Oversight Portal

1. Open `http://localhost:8095` (or your production URL `https://docurgent.in`).
2. On the gate screen ("Who are you?"), click **Access Admin Oversight Portal →** or type `Admin` and press Enter.
3. The secure Admin Authentication Modal will appear.
4. Enter your Super Admin credentials:
   - **Email**: `owner@docurgent.in` (or configured owner email)
   - **Password**: Your Super Admin password
   - **MFA Code**: 6-digit code from your Authenticator app
5. Click **Authenticate & Access Portal →**.

---

## 2. Navigating the Admin Portal Tabs

### 🩺 Doctor Verifications (Tab 1)
- Inspect all registered doctors and their current status (`pending_verification`, `verified`, `under_review`, `rejected`, `suspended`).
- Click **📄 Inspect Cert** to review their uploaded medical council degree.
- Use the status dropdown to approve genuine doctors to **VERIFIED** status (which instantly publishes them to the patient emergency directory) or **SUSPEND** doctors under investigation.

### 👥 Patients & PHI (Tab 2)
- Browse the patient emergency directory.
- Click **🔒 Inspect PHI (Audited)** to view a patient's medical history, allergies, and past prescriptions.
- You must enter a clinical reason (e.g., "Urgent clinical board review"), which is permanently audited.

### 🏥 Consultations Queue (Tab 3)
- Live overview of all emergency consultation requests across specialties.
- View real-time status: `requested`, `accepted`, `completed`, `cancelled`.

### 💰 Finance & Payouts (Tab 4)
- **Platform Commission Control**: Adjust the platform commission slider (default: 15%) and click **Save Commission**.
- **Financial Ledger**: Inspect payment references, gross fees, doctor earnings, and platform cuts.
- **Refunds**: Click **Issue Refund** on any completed transaction to initiate an immediate refund and cancellation.

### ⚙️ System & Super Admin (Tab 5)
- **Emergency Platform Maintenance Mode**: Toggle maintenance mode ON during server updates or clinical reviews. Normal patients are redirected to emergency services (112), while administrators maintain full operational access.
- **Administrator Accounts**: View all active medical board directors, check their MFA status, or click **+ Provision New Administrator** to invite a new director. Click **Revoke** to suspend an administrator account.

### 🗄️ Storage & DB Health (Tab 6)
- Monitor storage quota usage, file counts, and alert levels (`NORMAL`, `NOTICE`, `WARNING`, `CRITICAL`).
- View SQLite database size and integrity status (`PRAGMA integrity_check`).
- Click **⚡ Run VACUUM & Optimize DB** to defragment storage and reclaim space.

### 💾 Backups & Recovery (Tab 7)
- View recent point-in-time database snapshots.
- Click **+ Create Backup Now** to trigger an instant database and media snapshot.
- Click **✓ Check Hash** to verify SHA-256 integrity and structural consistency.

### 🛡️ Compliance Audit (Tab 8)
- Review the regulatory compliance audit trail tracking logins, consultations, prescription signatures, and admin decisions.
