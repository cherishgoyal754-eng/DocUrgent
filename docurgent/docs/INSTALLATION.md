# DocUrgent — Installation & Local Setup Guide

This guide describes how to install, configure, and run DocUrgent on macOS, Linux, and Windows development workstations.

---

## 1. Prerequisites

DocUrgent is designed with zero external third-party package dependencies for its core execution engine, running purely on Python 3.8+ standard libraries.

- **Python**: Version 3.8 or higher (`python3 --version`)
- **Git**: For version control (`git --version`)
- **Web Browser**: Any modern browser (Google Chrome, Apple Safari, Mozilla Firefox, Microsoft Edge)

---

## 2. Installation Steps

### Step 1: Clone Repository
```bash
git clone https://github.com/your-username/docurgent.git
cd docurgent/docurgent
```

### Step 2: Configure Environment Variables
Copy the sample environment template:
```bash
cp .env.example .env
```
Open `.env` in any text editor and customize the parameters:
- `PORT`: Server port (default: `8095`)
- `SUPERADMIN_EMAIL`: Your primary owner email (e.g., `owner@docurgent.in`)
- `SUPERADMIN_PASSWORD`: Strong password (min 10 characters with numbers and symbols)

### Step 3: Initialize Database & Migrations
```bash
python3 db.py
```
This automatically initializes the SQLite persistent database in WAL mode with all 15 relational tables, triggers, and indices.

### Step 4: Bootstrap the Super Admin Account
```bash
python3 bootstrap_superadmin.py --email "owner@docurgent.in" --password "YourStrongPassword2026!#"
```
The console will display:
- Your Owner Email
- Your 32-character RFC 6238 Base32 MFA Secret
- The Authenticator setup URI (`otpauth://totp/...`)
- 8 single-use emergency recovery codes (save these securely!)

---

## 3. Starting the Server

### Option A: Standard Terminal Execution
```bash
python3 server.py
```
DocUrgent will start on `http://localhost:8095`.

### Option B: macOS One-Click Launcher
Double-click `Launch_DocUrgent.command` in the project root. It automatically detects port availability, starts the background daemon, and opens your default browser.

---

## 4. Verification

Verify that your installation is operating normally by running the automated test suite:
```bash
cd ..
python3 test_docurgent.py
```
You should see:
```text
🎉 ALL 32 DOCURGENT VERIFICATION TESTS PASSED SUCCESSFULLY!
```

---

## 5. Stopping the Server
- If running in terminal: Press `Ctrl + C`.
- If running as background daemon on port 8095:
  ```bash
  kill -9 $(lsof -ti:8095)
  ```
