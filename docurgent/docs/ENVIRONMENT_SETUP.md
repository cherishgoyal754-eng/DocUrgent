# DocUrgent — Environment Configuration & Secrets Management

This document outlines environment variable configuration, secure secret management, and key rotation procedures.

---

## 1. Supported Environment Variables

| Variable Name | Default Value | Description |
| :--- | :--- | :--- |
| `PORT` | `8095` | HTTP server listening port. |
| `NODE_ENV` | `development` | Operating environment (`development`, `staging`, `production`). |
| `APP_BASE_URL` | `http://localhost:8095` | Public canonical URL for callback and link generation. |
| `SUPERADMIN_EMAIL` | `owner@docurgent.in` | Primary Super Admin platform owner email. |
| `SUPERADMIN_PASSWORD` | *(None)* | Initial password for CLI bootstrap. |
| `SUPERADMIN_PHONE` | `+919999999999` | Super Admin contact number. |
| `PLATFORM_COMMISSION_PERCENT` | `15` | Default platform percentage cut (Doctor keeps 85%). |
| `DEFAULT_CURRENCY` | `INR` | Transaction currency symbol (`INR`, `USD`). |
| `SERVER_SECRET_KEY` | *(Auto-generated)* | 32-byte cryptographic secret for short-lived HMAC URL signing. |
| `ALERT_EMAIL` | `admin@docurgent.in` | Administrator notification dispatch email. |
| `STORAGE_QUOTA_MB` | `5000` | Storage threshold quota (5 GB). |
| `MAX_UPLOAD_SIZE_MB` | `5` | Maximum single-file upload size (5 MB). |
| `DATABASE_URL` | *(None)* | PostgreSQL / Supabase connection string (when running in cloud). |

---

## 2. Secrets Management Best Practices

1. **Never Commit Secrets to Git**:
   - The `.gitignore` is pre-configured to strictly exclude `.env`, `.env.*`, and private credentials.
   - Always commit only `.env.example` as a template.
2. **Cloud Secret Managers**:
   - In production (Google Cloud Run / AWS), store sensitive keys (`SERVER_SECRET_KEY`, `DATABASE_URL`, `SUPERADMIN_PASSWORD`) in Google Cloud Secret Manager or AWS Secrets Manager.
   - Inject secrets into the runtime container via environment variable mapping.
3. **Rotating Keys**:
   - If the `SERVER_SECRET_KEY` is compromised, regenerate it in the database:
     ```bash
     python3 -c "import db, secrets; db.set_setting('server_secret_key', secrets.token_hex(32))"
     ```
   - This immediately invalidates all previously issued short-lived download links, protecting patient data.
