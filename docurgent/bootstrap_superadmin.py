#!/usr/bin/env python3
"""
DocUrgent 24/7 — Secure Super Admin Bootstrap & Account Recovery CLI
Initializes or resets the primary Super Admin owner account with PBKDF2-SHA256,
RFC 6238 Multi-Factor Authentication (TOTP), and single-use recovery codes.
"""

import sys
import os
import argparse
import getpass
import re
import datetime
import uuid

# Ensure imports resolve to docurgent directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import db

def validate_password_strength(password: str) -> tuple:
    """Enforces clinical-grade password complexity rules."""
    if len(password) < 10:
        return False, "Password must be at least 10 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter (a-z)."
    if not re.search(r"[0-9]", password):
        return False, "Password must include at least one digit (0-9)."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-]", password):
        return False, "Password must include at least one special character (!@#$%^&* etc)."
    return True, ""

def bootstrap_superadmin(email: str, password: str, phone: str = "+919999999999", force_reset: bool = False):
    db.init_db()
    conn = db.get_connection()
    c = conn.cursor()

    # Check if a super admin already exists
    c.execute("SELECT id, email FROM users WHERE role = 'super_admin'")
    existing_super = c.fetchone()

    if existing_super and not force_reset:
        print(f"\n⚠️  A Super Admin account already exists: {existing_super['email']}")
        print("To safely rotate credentials or recover this account, re-run with --reset flag:\n")
        print(f"    python3 {os.path.basename(__file__)} --email {email} --reset\n")
        conn.close()
        return False

    is_valid, err = validate_password_strength(password)
    if not is_valid:
        print(f"\n❌ Password Complexity Requirement Failed: {err}")
        conn.close()
        return False

    now = datetime.datetime.utcnow().isoformat()
    pwd_hash, salt = db.hash_password(password)
    totp_secret = db.generate_totp_secret()
    plain_recovery_codes, hashed_recovery_json = db.generate_recovery_codes(8)

    if existing_super and force_reset:
        user_id = existing_super['id']
        c.execute("""
            UPDATE users SET
                email = ?,
                phone = ?,
                password_hash = ?,
                salt = ?,
                role = 'super_admin',
                is_active = 1,
                is_email_verified = 1,
                mfa_secret = ?,
                mfa_enabled = 1,
                recovery_code_hash = ?,
                failed_login_attempts = 0,
                locked_until = NULL,
                last_login_at = NULL
            WHERE id = ?
        """, (email, phone, pwd_hash, salt, totp_secret, hashed_recovery_json, user_id))
        action = "SUPERADMIN_RECOVERY_RESET"
    else:
        user_id = f"superadmin-{uuid.uuid4().hex[:8]}"
        c.execute("""
            INSERT INTO users (
                id, email, phone, password_hash, salt, role, is_active,
                is_email_verified, mfa_secret, mfa_enabled, recovery_code_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, 'super_admin', 1, 1, ?, 1, ?, ?)
        """, (user_id, email, phone, pwd_hash, salt, totp_secret, hashed_recovery_json, now))
        action = "SUPERADMIN_BOOTSTRAP_CREATED"

    # Update system setting for primary superadmin email
    c.execute("""
        INSERT OR REPLACE INTO system_settings (key, value, updated_at, updated_by)
        VALUES ('superadmin_email', ?, ?, ?)
    """, (email, now, user_id))
    db.log_audit(conn, user_id, 'super_admin', action, 'users', user_id, f"Super Admin configured for {email}")
    conn.commit()
    conn.close()

    current_totp_code = db.get_totp_code(totp_secret)

    print("\n" + "=" * 70)
    print("  👑 DOCURGENT 24/7 — SUPER ADMIN CREDENTIALS CONFIGURED")
    print("=" * 70)
    print(f"  Owner Email      : {email}")
    print(f"  Role             : super_admin (Highest Platform Authority)")
    print(f"  MFA Secret       : {totp_secret}")
    print(f"  MFA Setup URI    : otpauth://totp/DocUrgent:{email}?secret={totp_secret}&issuer=DocUrgent")
    print(f"  Current 6-Digit  : {current_totp_code} (Valid for ~30 seconds)")
    print("-" * 70)
    print("  🔐 EMERGENCY ONE-TIME RECOVERY CODES (Store in a secure vault):")
    for i, code in enumerate(plain_recovery_codes, 1):
        print(f"    [{i}] {code}")
    print("=" * 70)
    print("  ✓ Super Admin is fully verified, MFA-secured, and active.")
    print("=" * 70 + "\n")
    return True

def main():
    parser = argparse.ArgumentParser(description="DocUrgent Super Admin Bootstrap & Account Recovery Tool")
    parser.add_argument("--email", help="Super Admin Owner Email Address")
    parser.add_argument("--password", help="Super Admin Password (minimum 10 chars, uppercase, lowercase, number, symbol)")
    parser.add_argument("--phone", default="+919999999999", help="Super Admin Phone Number")
    parser.add_argument("--reset", action="store_true", help="Reset existing Super Admin account credentials")

    args = parser.parse_args()

    email = args.email or os.environ.get("SUPERADMIN_EMAIL")
    if not email:
        try:
            email = input("Enter Super Admin Email: ").strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(1)

    password = args.password or os.environ.get("SUPERADMIN_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Enter Super Admin Password (min 10 chars): ")
            confirm = getpass.getpass("Confirm Super Admin Password: ")
            if password != confirm:
                print("❌ Passwords do not match.")
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            sys.exit(1)

    success = bootstrap_superadmin(email, password, args.phone, args.reset)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
