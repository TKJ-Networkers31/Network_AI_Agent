# AIRA OS — NETWORKING VIII: EXTERNAL ACCESS SECURITY SPECIFICATION
## Reverse Proxy, TLS Hardening, Security Headers, Rate Limiting & Denial of Service Protection (WP 8.9)

**Document Reference:** `docs/NETWORKING_VIII/EXTERNAL_ACCESS_SECURITY_SPECIFICATION.md`  
**Milestone:** Networking VIII — Phase D  
**Scope:** Edge Gateway and Customer Portal External Perimeter Defense  
**Date:** 2026-11-04  
**Status:** **AUTHORITATIVE SECURITY SPECIFICATION**

---

### 1. Perimeter Architecture

External customers connect to AIRA OS exclusively via an encrypted reverse proxy layer terminating TLS. Direct connection to the FastAPI application port (`8000`), SQLite databases, or internal MikroTik management networks is strictly prevented by firewall rules.

```
Internet / Customer WAN
          │
          ▼ HTTPS (Port 443)
┌─────────────────────────────────────────────────────────────────────────────┐
│                       REVERSE PROXY (Nginx / Caddy)                         │
│  • TLS 1.2 / TLS 1.3 Termination (Modern Ciphers)                           │
│  • Rate Limiting: 60 req/min for API, 10 req/min for /auth/login            │
│  • Max Body Size: 2 MB (Prevent memory exhaustion)                          │
│  • Security Headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options     │
│  • Trusted Proxy Header Rewriting (X-Forwarded-For, X-Forwarded-Proto)      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Loopback / Private VPC (127.0.0.1:8000)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AIRA FASTAPI BACKEND (Uvicorn)                         │
│  • Trusted Proxy Middleware (Reads Client IP safely)                        │
│  • Explicit CORS Allowlist                                                  │
│  • Input Validation (Pydantic)                                              │
│  • Fail-Closed Structured Error Responses (No Python Traceback Leaks)       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 2. Mandatory HTTP Security Headers

Every response leaving the AIRA reverse proxy or FastAPI middleware must include:

| Security Header | Directive / Value | Security Protection |
| :--- | :--- | :--- |
| **Strict-Transport-Security** | `max-age=31536000; includeSubDomains; preload` | Forces HTTPS, prevents SSL stripping. |
| **X-Content-Type-Options** | `nosniff` | Prevents MIME-type sniffing. |
| **X-Frame-Options** | `DENY` | Prevents clickjacking attacks. |
| **Referrer-Policy** | `strict-origin-when-cross-origin` | Minimizes URL leakage in HTTP referrers. |
| **Permissions-Policy** | `geolocation=(), camera=(), microphone=(), payment=()` | Disables unused browser hardware capabilities. |
| **Content-Security-Policy** | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' wss: https:;` | Defends against Cross-Site Scripting (XSS). |

---

### 3. Rate Limiting & Brute-Force Defense

1. **Authentication Endpoint Throttling:**
   - Target: `POST /api/v1/portal/auth/login`
   - Limit: **5 requests per minute per IP address**.
   - Action upon breach: HTTP 429 Too Many Requests with `Retry-After: 60`.
2. **General API Rate Limiting:**
   - Target: `/api/v1/portal/*`
   - Limit: **120 requests per minute per authenticated user**.
   - Protects against resource exhaustion on dual-core hardware.
3. **Payload Size Restrictions:**
   - HTTP body capped at **2 MB**. Malformed or oversized payloads fail with HTTP 413 Payload Too Large.

---

### 4. Production Nginx Configuration Blueprint

The production reverse proxy configuration is provided in [`deploy/nginx/aira_customer_portal.conf`](file:///D:/data/agent_ai/deploy/nginx/aira_customer_portal.conf):

```nginx
# Rate Limiting Zones
limit_req_zone $binary_remote_addr zone=portal_auth_limit:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=portal_api_limit:10m rate=120r/m;

server {
    listen 443 ssl http2;
    server_name portal.aira.lstechnology.net;

    # SSL Certificates & Modern Ciphers
    ssl_certificate /etc/letsencrypt/live/portal.aira.lstechnology.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/portal.aira.lstechnology.net/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5:!3DES;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 2M;

    # Rate-limited Auth Endpoint
    location /api/v1/portal/auth/login {
        limit_req zone=portal_auth_limit burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # General API Endpoint
    location /api/ {
        limit_req zone=portal_api_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static Frontend SPA
    location / {
        root /var/www/aira_dist;
        try_files $uri $uri/ /index.html;
    }
}
```
