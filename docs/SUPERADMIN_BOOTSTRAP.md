# AIRA OS — Superadmin Bootstrap Architecture & Operational Guide
**Document Reference:** `docs/SUPERADMIN_BOOTSTRAP.md`  
**Phase:** Phase E — Dual-Site Platform, Identity, Superadmin, Subscriptions & NOC  
**Status:** Implemented & Verified

---

## 1. Executive Summary

AIRA OS provisions a single, authoritative platform owner account:
- **Username:** `lingga_admin`
- **Role:** `PLATFORM_SUPER_ADMIN` / `SUPERADMIN`
- **Tenant:** `tenant_internal` (Platform Management Plane)

This account possesses unrestricted administrative privileges across both Client and Admin sites, including:
- Complete oversight and lifecycle management of all tenant organizations and users.
- Governance over all subscription plans, entitlements, and token metering limits.
- Full access to all **Networking++** capabilities (advanced topology paths, live telemetry, and Ansible playbook execution).
- Audited account impersonation for network incident troubleshooting.

---

## 2. Security Requirements & Hardening Measures

In strict conformance with Directive Section 3:
1. **Zero Hardcoded Passwords:** The initial password is NEVER committed to source code or version control.
2. **Environment Variable & Secure Generation:** The bootstrap script inspects `AIRA_SUPERADMIN_PASSWORD`. If unset, it generates a cryptographically strong 18-character random password using `secrets.choice`.
3. **Argon2 / PBKDF2 Hashing:** Passwords are hashed with PBKDF2-HMAC-SHA256 (100,000 iterations, 16-byte random salt).
4. **Forced First-Login Password Change:** The account is created with `must_change_password = 1`. The user is required to set a permanent password upon first login via `POST /api/v1/auth/change-password-mandatory`.
5. **MFA Enforceable:** The Superadmin account supports standard RFC 6238 TOTP two-factor authentication.
6. **Brute-Force Lockout:** Protected by the 5-attempt rate-limiting threshold (15-minute temporary lockout).
7. **Tamper-Evident Audit Logging:** Bootstrap, password rotation, and impersonation events are appended to `operational_audit_log`.

---

## 3. Bootstrap CLI & Idempotent Runner

The bootstrap module (`core/bootstrap_superadmin.py`) can be executed as a standalone CLI script or imported as a library during deployment or container startup:

```bash
# Provision lingga_admin using secure generated password:
python core/bootstrap_superadmin.py

# Provision lingga_admin using explicit environment variable:
export AIRA_SUPERADMIN_PASSWORD="MySecureAdminPassword2026!"
python core/bootstrap_superadmin.py

# Force reset credentials for account recovery:
python core/bootstrap_superadmin.py --reset --password "NewEmergencyPassword2026!"
```

### CLI Output Example:
```
======================================================================
  AIRA OS — Superadmin Bootstrap Engine
======================================================================
[INFO] Bootstrapping Superadmin account: lingga_admin
[INFO] Organization assigned: Platform Internal (tenant_internal)
[INFO] Role assigned: PLATFORM_SUPER_ADMIN
[INFO] Entitlement granted: Networking++ (Active)
[INFO] Token balance allocated: 10,000,000 credits
[INFO] Security status: must_change_password = 1 (Required on first login)
======================================================================
```

---

## 4. Verification and Recovery Procedures

### 4.1 First Login Workflow
1. Superadmin logs in via `/api/v1/auth/login` (with `admin_only: true`).
2. API validates password and returns:
   ```json
   {
     "success": true,
     "token": "aira_tok_...",
     "must_change_password": true,
     "user": {
       "username": "lingga_admin",
       "roles": ["PLATFORM_SUPER_ADMIN"]
     }
   }
   ```
3. Superadmin sets permanent password via `POST /api/v1/auth/change-password-mandatory`:
   ```json
   {
     "new_password": "NewPermanentSuperSecurePassword!"
   }
   ```
4. Backend updates hash, clears `must_change_password = 0`, and records an audit log entry.

### 4.2 Account Recovery Procedure
If the Superadmin credentials are lost or locked out, a platform operator with server access can invoke the recovery command:
```powershell
.venv\Scripts\python.exe AIRA_ECOSYSTEM/core/bootstrap_superadmin.py --reset
```
This idempotently unlocks the account, resets failed attempts, assigns a fresh random credential, and logs the emergency recovery in `operational_audit_log`.
