# DocUrgent — Platform Maintenance & Routine Operations Runbook

This runbook outlines standard maintenance tasks, performance optimization, log rotation, and database defragmentation.

---

## 1. Routine Maintenance Schedule

| Cadence | Operational Task | Method |
| :--- | :--- | :--- |
| **Daily (02:00 UTC)** | Database & Uploads Backup | Automated via `backup_manager.py --create` |
| **Weekly** | Backup Pruning (Retain 7 days) | Automated via `backup_manager.py --prune 7` |
| **Monthly** | Test Database Restoration | `backup_manager.py --verify [latest_backup]` |
| **Monthly** | Database Defragmentation (VACUUM) | Admin Portal Tab 6 or `VACUUM` in SQLite |
| **Quarterly** | Security Audit & Key Review | Audit log export & credential inspection |

---

## 2. Enabling Maintenance Mode

When performing sensitive database migrations, infrastructure upgrades, or emergency clinical reviews:

### Via Admin Dashboard:
1. Navigate to **⚙️ System & Super Admin** (Tab 5).
2. Click **Toggle Maintenance**.
3. Status changes to **ON (Platform Restricted)**.

### Via Command-Line:
```bash
python3 -c "import db; db.set_setting('maintenance_mode', 'true')"
```

### Impact of Maintenance Mode:
- **Patient & Doctor Portals**: Display a clean, clinical maintenance screen advising patients to dial **112** for emergency assistance.
- **Admin Portal**: Remains 100% accessible to verified administrators and the Super Admin.

### Disabling Maintenance Mode:
```bash
python3 -c "import db; db.set_setting('maintenance_mode', 'false')"
```

---

## 3. Database Optimization & VACUUM

Over time, SQLite database files accumulate fragmented pages from deleted records and temporary sessions.

To optimize performance and reclaim unused disk space:
```bash
python3 -c "
import db
conn = db.get_connection()
conn.execute('VACUUM')
conn.execute('PRAGMA optimize')
conn.close()
print('Database defragmentation and optimization completed.')
"
```
Or click **⚡ Run VACUUM & Optimize DB** in Tab 6 of the Admin Portal.
