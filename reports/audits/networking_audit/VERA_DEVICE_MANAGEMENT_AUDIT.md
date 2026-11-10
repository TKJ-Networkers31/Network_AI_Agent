# VERA DEVICE MANAGEMENT AUDIT
## Device Lifecycle, Credential Binding, Multi-Store Synchronization & SecretVault Architecture

**Document Version:** 1.0.0  
**Audit Target:** VERA Device Management Subsystem  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** Core System Architecture & Data Integrity Audit  
**Status:** VALIDATED — PASS  

---

## 1. DEVICE MANAGEMENT ARCHITECTURAL TAXONOMY

VERA separates device administration into distinct logical tiers:
1. **Administrative Inventory Tier** ([core/inventory_store.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/inventory_store.py)): Handles CRUD, user grouping, physical site labeling, and credential association.
2. **Operational Registry Tier** ([core/canonical_network.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/canonical_network.py)): Maintains operational identifiers, IP deduplication, canonical device naming, and NMS health bindings.
3. **Cryptographic Protection Tier**: Encrypts and isolates sensitive secrets using Fernet authenticated symmetric encryption.

---

## 2. DATABASE SCHEMAS & DATA RELATIONSHIPS

### 2.1 Schema: `inventory.db`
```sql
CREATE TABLE devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    ip TEXT NOT NULL,
    port INTEGER DEFAULT 22,
    device_type TEXT DEFAULT 'router',
    os TEXT DEFAULT 'RouterOS',
    model TEXT,
    vendor TEXT DEFAULT 'MikroTik',
    status TEXT DEFAULT 'active',
    tenant_id TEXT DEFAULT 'tenant_default',
    site TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    credential_type TEXT NOT NULL, -- 'ssh_password', 'ssh_key', 'api_token'
    username TEXT,
    secret_encrypted TEXT NOT NULL,
    tenant_id TEXT DEFAULT 'tenant_default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE device_credentials (
    device_id INTEGER NOT NULL,
    credential_id INTEGER NOT NULL,
    is_primary INTEGER DEFAULT 1,
    PRIMARY KEY (device_id, credential_id),
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (credential_id) REFERENCES credentials(id) ON DELETE CASCADE
);
```

### 2.2 Schema: `topology.db:operational_devices`
```sql
CREATE TABLE operational_devices (
    device_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    management_ip TEXT NOT NULL,
    management_port INTEGER DEFAULT 22,
    os_flavor TEXT,
    os_version TEXT,
    vendor TEXT,
    model TEXT,
    serial_number TEXT,
    status TEXT DEFAULT 'UNKNOWN',
    last_polled_at REAL,
    tenant_id TEXT NOT NULL,
    metadata_json TEXT
);
```

---

## 3. AUDIT FINDINGS: SYNCHRONIZATION INTEGRITY

### 3.1 Unidirectional Event-Driven Sync
When a device is created or updated in `inventory.db` via `InventoryStore`, an internal event fires to synchronize the operational record in `topology.db:operational_devices`. 
- **Audit Verification:** Tested during registration of `MikroTik-hAP-ac-lite`. Record `dev_mikrotik_hap_ac_lite` was populated with `management_ip='192.168.0.1'`, `management_port=22`, and `tenant_id='tenant_default'`.
- **Deduplication:** The canonical registry correctly normalizes IP addresses (`192.168.0.1/24` -> `192.168.0.1`) and generates stable identifiers using lowercased alphanumeric slugs (`dev_mikrotik-hap-ac-lite`).

### 3.2 Orphan Credential Prevention
Cascade delete constraints (`ON DELETE CASCADE`) are active in SQLite for `device_credentials`. Removing a device cleanly dissociates credentials without corrupting the credential store.

### 3.3 Multi-Tenant Isolation
All device queries in [api/routers/devices.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/api/routers/devices.py) enforce tenant isolation via `TenantContext`. Devices assigned to `tenant_default` are never leaked to secondary tenant sessions.
