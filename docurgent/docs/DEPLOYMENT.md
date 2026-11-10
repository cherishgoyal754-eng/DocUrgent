# DocUrgent — Production Cloud Deployment & Domain Guide

This document details production deployment procedures for Google Cloud Run, Vercel, Docker, custom domain mapping (`docurgent.in`), SSL certificates, and environment configuration.

---

## 1. Google Cloud Run Deployment (Recommended Backend Hosting)

Google Cloud Run provides a serverless, automatically scaling, HIPAA-aligned container environment for the DocUrgent Python server.

### Prerequisites
- Google Cloud SDK (`gcloud` CLI installed and authenticated)
- A Google Cloud Project with Cloud Run and Artifact Registry APIs enabled

### Step 1: Build & Submit Container Image
```bash
cd docurgent
gcloud builds submit --tag gcr.io/[PROJECT_ID]/docurgent:v2.5.0
```

### Step 2: Deploy to Cloud Run
```bash
gcloud run deploy docurgent-service \
    --image gcr.io/[PROJECT_ID]/docurgent:v2.5.0 \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --port 8095 \
    --set-env-vars "NODE_ENV=production,DEFAULT_CURRENCY=INR,PLATFORM_COMMISSION_PERCENT=15" \
    --set-secrets "SUPERADMIN_EMAIL=superadmin-email:latest,SUPERADMIN_PASSWORD=superadmin-password:latest,SERVER_SECRET_KEY=server-secret-key:latest"
```

---

## 2. Supabase Integration (Managed Database & Cloud Storage)

For high-scale multi-region production operations, migrate from local SQLite to Supabase:

### Step 1: Create Supabase Project
1. Log in to [supabase.com](https://supabase.com).
2. Create a new project in your preferred region.

### Step 2: Apply Database Schema
1. Open the Supabase SQL Editor.
2. Paste and execute the contents of `docurgent/schema_supabase.sql`.
3. Verify all tables, enums, indices, and Row Level Security (RLS) policies are active.

### Step 3: Configure Private Medical Storage Bucket
1. Go to Storage in Supabase Dashboard.
2. Create a private bucket named `medical-uploads` (public access disabled).
3. Set maximum file upload size to 5MB and allowed MIME types: `image/jpeg, image/png, application/pdf`.

---

## 3. Custom Domain Setup (`docurgent.in`)

### Step 1: DNS Records Configuration
In your domain registrar (GoDaddy, Cloudflare, Namecheap):
- **A Record**: Point `@` to your Cloud Run load balancer IP or `76.76.21.21` (if proxying).
- **CNAME Record**: Point `www` to `docurgent.in`.

### Step 2: Google Cloud Run Domain Mapping
```bash
gcloud beta run domain-mappings create \
    --service docurgent-service \
    --domain docurgent.in \
    --region us-central1
```
Google Cloud Run automatically provisions and renews managed SSL/TLS certificates via Let's Encrypt at zero extra cost.

---

## 4. Staging vs Production Environments

Always maintain two isolated environments:
1. **Staging Environment**:
   - URL: `https://staging.docurgent.in`
   - Database: Test seed database
   - Gateway Mode: Sandbox
   - Used for verifying code and migrations before production deployment.
2. **Production Environment**:
   - URL: `https://docurgent.in`
   - Database: Persistent encrypted database with automated daily snapshots.
   - Gateway Mode: Live
   - Super Admin with MFA enforced.

---

## 5. Deployment Rollback
If a newly deployed release encounters issues in production:
```bash
# Revert Cloud Run traffic to the previous known stable revision:
gcloud run services update-traffic docurgent-service --to-revisions [PREVIOUS_REVISION_NAME]=100
```
Refer to [ROLLBACK_INSTRUCTIONS.md](file:///Users/cherishgoyal/Downloads/new2/docurgent/docs/ROLLBACK_INSTRUCTIONS.md) for full database and media recovery steps.
