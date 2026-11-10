# DocUrgent — Automated Backup & Disaster Recovery Architecture

This document defines the operational procedures for data protection, automated daily backups, SHA-256 integrity verification, and disaster restoration in DocUrgent.

---

## 1. Backup Strategy Overview

DocUrgent enforces a dual backup architecture:
1. **Online Point-in-Time Database Snapshots**: SQLite Online Backup API creates ACID-consistent database clones without locking writers.
2. **Compressed Private Uploads Archives**: All patient injury photos, clinical certificates, and signed PDFs are archived into `.tar.gz` bundles.
3. **Cryptographic Checksums**: Every snapshot generates a `.sha256` sidecar file to detect tampering or silent bit rot.
4. **Automated Pruning Policy**: Backups older than 7 days are automatically pruned to prevent unbounded storage expansion.

---

## 2. Running Backups

### Automatic Daily Schedule
DocUrgent can be triggered daily at 02:00 UTC via standard system cron or Cloud Scheduler:
```bash
0 2 * * * /usr/bin/python3 /path/to/docurgent/backup_manager.py --create
```

### Manual CLI Execution
```bash
python3 docurgent/backup_manager.py --create
```
Example Output:
```text
Starting point-in-time database snapshot...
✓ Database snapshot: db_backup_20261111_020000.db (188416 bytes, SHA256: 9ce6a8bddf...)
Starting compressed uploaded files archiving...
✓ Uploads archive: uploads_backup_20261111_020000.tar.gz (354 bytes, SHA256: aa4e4fc0...)
```

### Admin Dashboard One-Click Trigger
In the Admin Oversight Portal:
1. Navigate to the **💾 Backups & Recovery** tab.
2. Click **+ Create Backup Now**.
3. The server immediately takes a snapshot, checks its integrity, and refreshes the snapshot list.

---

## 3. Backup Verification

Always verify backup integrity before relying on a snapshot for restoration:
```bash
python3 docurgent/backup_manager.py --verify docurgent/backups/db/db_backup_20261111_020000.db
```
The utility:
1. Recalculates the SHA-256 hash of the snapshot and matches it with the sidecar file.
2. Connects to the database and runs SQLite's `PRAGMA integrity_check`.
3. Returns `✓ VERIFICATION PASSED` or reports structural corruption.

---

## 4. Disaster Recovery Scenarios

### Scenario A: Application Server Hardware Failure
1. Provision a new server instance.
2. Install Python 3.8+ and clone the repository.
3. Copy the latest verified database and uploads archive from remote encrypted storage.
4. Run:
   ```bash
   cp latest_backup.db docurgent/docurgent.db
   tar -xzvf latest_uploads.tar.gz -C docurgent/
   python3 docurgent/server.py
   ```

### Scenario B: Database Accidental Record Deletion
1. Put platform in maintenance mode:
   ```bash
   python3 -c "import db; db.set_setting('maintenance_mode', 'true')"
   ```
2. Stop the server process (`kill -9 $(lsof -ti:8095)`).
3. Back up the damaged database for forensics:
   ```bash
   mv docurgent/docurgent.db docurgent/docurgent_damaged.db
   ```
4. Restore the latest verified snapshot:
   ```bash
   cp docurgent/backups/db/db_backup_YYYYMMDD_HHMMSS.db docurgent/docurgent.db
   ```
5. Restart the server and disable maintenance mode via the Admin Portal.
