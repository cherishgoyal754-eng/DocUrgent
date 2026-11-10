# DocUrgent — Production Rollback & Disaster Recovery Runbook

This runbook defines emergency rollback procedures for the DocUrgent platform in case of critical production regressions, failed deployments, or database inconsistencies.

---

## 1. Quick Emergency Rollback (Code Deployment)

If a newly deployed release exhibits unexpected runtime errors or crashes:

### Step 1: Identify Last Stable Tag
```bash
git tag --sort=-v:refname
# Example output: v2.4.0
```

### Step 2: Roll Back Code to Stable Tag
```bash
git checkout v2.4.0
```

### Step 3: Restart DocUrgent Service
```bash
# macOS local launcher:
kill -9 $(lsof -ti:8095)
./Launch_DocUrgent.command

# Linux / Systemd production:
sudo systemctl restart docurgent

# Docker / Cloud Run:
docker build -t docurgent:v2.4.0 .
docker stop docurgent_app && docker rm docurgent_app
docker run -d --name docurgent_app -p 8095:8095 -v $(pwd)/docurgent_data:/app/data docurgent:v2.4.0
```

### Step 4: Verify System Health
```bash
curl -I http://localhost:8095/api/health
```

---

## 2. Database Disaster Recovery (SQLite / Supabase)

If database corruption or unintended record deletion occurs:

### Step 1: Immediately Stop Incoming Writes
Put the application in maintenance mode or stop the backend service:
```bash
python3 -c "import db; db.set_maintenance_mode(True)"
```

### Step 2: Locate Latest Valid Backup Snapshot
Backups are archived in `docurgent/backups/db/` with SHA-256 integrity hashes:
```bash
ls -lt docurgent/backups/db/
```

### Step 3: Verify Backup Hash Integrity
```bash
python3 docurgent/backup_manager.py --verify docurgent/backups/db/db_backup_YYYYMMDD_HHMMSS.db
```

### Step 4: Restore Snapshot
```bash
# Move corrupted DB to quarantined directory
mv docurgent/docurgent.db docurgent/docurgent.db.corrupted_$(date +%s)

# Restore verified snapshot
cp docurgent/backups/db/db_backup_YYYYMMDD_HHMMSS.db docurgent/docurgent.db

# Run integrity verification
python3 -c "import db; conn=db.get_connection(); print(conn.execute('PRAGMA integrity_check').fetchall())"
```

### Step 5: Resume Platform Traffic
```bash
python3 -c "import db; db.set_maintenance_mode(False)"
```

---

## 3. Storage & Uploads Recovery

If private patient uploads or doctor certificates are damaged or removed:

### Step 1: Locate Upload Archive
```bash
ls -lt docurgent/backups/files/uploads_backup_*.tar.gz
```

### Step 2: Extract to Uploads Directory
```bash
tar -xzvf docurgent/backups/files/uploads_backup_YYYYMMDD.tar.gz -C docurgent/
```

### Step 3: Confirm Access
Test short-lived URL generation:
```bash
curl "http://localhost:8095/api/health"
```

---

## 4. Verification Checklist Post-Rollback
- [ ] `/api/health` returns status: 200 OK
- [ ] Emergency Safety Gateway redirects critical symptoms
- [ ] Patient directory displays verified doctors
- [ ] Database integrity check returns `ok`
- [ ] Admin portal accessible to Super Admin
