# AIRA OS — OWASP ASVS 5.0 Hardening & Security Implementation Guide
**Document Reference:** `docs/security/OWASP_HARDENING_GUIDE.md`  
**Version:** 1.0.0 (Phase H)  
**Standard Compliance:** OWASP Application Security Verification Standard (ASVS) 5.0 (Level 2/3)

---

## 1. Authentication & Password Security (V2 & V3)

### 1.1 Argon2id Key Derivation
AIRA OS replaces legacy PBKDF2-HMAC-SHA256 password hashing with RFC 9106 compliant **Argon2id**:
- **Algorithm:** `argon2id` (v=19)
- **Time Cost ($t$):** 3 iterations
- **Memory Cost ($m$):** $65,536\text{ KiB}$ ($64\text{ MB}$)
- **Parallelism ($p$):** 4 parallel threads
- **Hash Length:** 32 bytes

```python
# core/security/password.py
from argon2 import PasswordHasher
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32)
```

### 1.2 Transparent Migration of Legacy PBKDF2
To ensure zero user downtime, AIRA OS transparently re-hashes passwords upon successful login:
1. System validates credential against legacy PBKDF2 hash (`salt$hash`).
2. If match is verified, system computes modern `$argon2id$...` hash in memory.
3. Database record in `operational_users` is atomically upgraded.
4. Subsequent logins utilize fast, hardware-hardened Argon2id verification.

### 1.3 Active Session Revocation
When a user updates their password or an administrator disables an account:
$$\text{Password Change} \Longrightarrow \text{UPDATE operational\_user\_sessions SET status='REVOKED' WHERE user\_id=?}$$
All active Bearer tokens (`aira_tok_...`) are instantly invalidated.

---

## 2. Denial of Service & Brute-Force Defense (V13)

### 2.1 In-Memory Sliding-Window IP Rate Limiter
All authentication and token exchange endpoints (`/api/v1/auth/token`, `/api/v1/auth/login`) are protected by `SlidingWindowRateLimiter` (`core/security/rate_limiter.py`):
- **Window Size:** 60 seconds
- **Max Requests:** 10 requests per window per source IP
- **Action on Breach:** Immediate `429 Too Many Requests` with `Retry-After: <seconds>` header.
- **Memory Management:** Auto-evicts timestamps older than window on every evaluation.

---

## 3. Server-Side Request Forgery (SSRF) Defense (V5)

AIRA OS connects to on-premise switches, routers, and SNMP/REST agents. To protect against pivot attacks, `SSRFValidator` (`core/security/ssrf_validator.py`) inspects all outbound URLs and IPs before network sockets open.

### 3.1 Prohibited Address Classes
- **Loopback:** `127.0.0.0/8`, `::1`
- **Link-Local & Cloud Metadata:** `169.254.0.0/16`, `fe80::/10`, `metadata.google.internal`, `169.254.169.254`
- **Multicast & Reserved:** `224.0.0.0/4`, `240.0.0.0/4`, `ff00::/8`
- **Non-Approved Private RFC 1918:** Allowed only when explicitly registered in the tenant's customer site inventory with explicit RFC 1918 customer site binding.

---

## 4. AI Confidentiality & Output Guard (V8 & V14)

Large Language Models integrated with operational platforms can inadvertently output sensitive infrastructure secrets. AIRA OS establishes a dual-direction defense in `core/security/output_guard.py`:

### 4.1 Pre-Retrieval Context Scrubber
Before embedding network state or historical logs into prompt context:
- Callers lacking `ACCESS_SENSITIVE_DATA` have all `RESTRICTED` items scrubbed.
- Real device credentials, vault tokens, SNMP community strings (`public`, `private`), and private keys are stripped from the context payload.

### 4.2 Post-Generation Leak Scrubber
Generated text, explanations, action cards, and diagrams are sanitized with high-precision regex scanners:
- **Private Keys:** `-----BEGIN [A-Z ]*PRIVATE KEY-----`
- **Session Tokens:** `aira_tok_[a-zA-Z0-9_\-]+`, JWT tokens `eyJ...`
- **API Keys & Secrets:** `sk-[a-zA-Z0-9]{32,}`, AWS keys `AKIA[0-9A-Z]{16}`
- **Password Assignments:** `password=[^\s;]+`, `auth-password=[^\s;]+`
- **SNMP Communities:** `snmp-community=[^\s;]+`

All matches are deterministically replaced with:
`[REDACTED_SECRET]` or `[REDACTED_CREDENTIAL]`

### 4.3 Safe SVG & Markdown Sanitization
- Strips `<script>`, `onload`, `onerror`, `javascript:`, and data URIs from SVGs.
- Enforces safe URL schemes (`http`, `https`, `mailto`) in markdown links.

---

## 5. HTTP Security Response Headers (V14)

FastAPI edge middleware enforces strict defense-in-depth headers on all responses:

```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), camera=(), microphone=(), payment=()
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: https:; connect-src 'self' ws: wss:;
```
