# AIRA OS — Ansible-Compatible Playbook Engine & Execution Sandbox
**Document Reference:** `docs/ANSIBLE_PLAYBOOK_ENGINE.md`  
**Phase:** Phase E — Dual-Site Platform, Identity, Superadmin, Subscriptions & NOC  
**Status:** Implemented & Verified

---

## 1. Executive Summary

In accordance with Directive Section 8:
> **"Dukung eksekusi playbook network dan host automation dengan sintaks atau compatibility layer yang familiar bagi pengguna Ansible."**

AIRA OS implements a secure, isolated Ansible-compatible Playbook Engine (`core/playbooks/runner.py`) capable of parsing, validating, and executing network configuration, health diagnostics, package inventory, and maintenance playbooks across device and host fleets.

---

## 2. Built-in Playbook Library

AIRA OS provisions 6 production-grade built-in playbooks seeded into `operational_playbooks`:

| Playbook ID | Name | Category | Risk Level | Description |
|---|---|---|---|---|
| `pb_builtin_health_check` | **Linux Health Check** | `OBSERVABILITY` | `CATEGORY_A` | Verifies system uptime, CPU load average, RAM utilization, and root disk capacity. |
| `pb_builtin_service_status` | **Service & Port Status** | `OBSERVABILITY` | `CATEGORY_A` | Inspects status of essential network services (sshd, systemd-resolved) and active listening TCP/UDP ports. |
| `pb_builtin_pkg_inventory` | **Package & Security Inventory** | `INVENTORY` | `CATEGORY_A` | Queries kernel release and pending security upgrade advisories. |
| `pb_builtin_config_backup` | **Configuration Backup** | `BACKUP` | `CATEGORY_A` | Retrieves network interface definitions, IP addresses, and kernel routing tables for archival. |
| `pb_builtin_maintenance` | **Basic Host Maintenance** | `MAINTENANCE` | `CATEGORY_B` | Cleans temporary package manager caches and forces system log rotation. |
| `pb_builtin_config_audit` | **Security & Hardening Audit** | `SECURITY` | `CATEGORY_A` | Audits SSH daemon security configuration (root login, public key auth) and active firewall rules. |

---

## 3. Playbook YAML Structure & Validation

Playbooks follow standard Ansible YAML format with plays, target hosts, variables, and task lists:

```yaml
---
- name: Linux Host and Network Appliance Health Check
  hosts: all
  gather_facts: false
  vars:
    disk_threshold_pct: 85
    memory_threshold_pct: 90
  tasks:
    - name: Verify host reachability
      ping:
    - name: Check system uptime and load average
      command: uptime
      register: uptime_result
    - name: Check memory usage
      command: free -m
      register: memory_result
    - name: Check root disk usage
      command: df -h /
      register: disk_result
```

### Structural Schema Validation (`validate_playbook_yaml`)
- Validates YAML syntax using safe parsers.
- Checks that the root element is a YAML list of plays.
- Enforces mandatory `hosts` specification per play.
- Checks `tasks` definitions and variable schemas.

---

## 4. Execution Sandbox & Credential Redaction

### 4.1 Target Isolation & Safety Controls
- **Target Allowlisting:** Every target must resolve to a valid IP address or inventory device ID.
- **Execution Timeout:** Jobs are bounded by strict timeouts (default 30 seconds) to prevent frozen processes.
- **Non-Destructive Defaults:** Network checks execute safely without altering kernel parameters or routing tables.

### 4.2 Automatic Sensitive Output Redaction (`redact_sensitive_output`)
To prevent credential leakage in logs or chat artifacts, all output streams pass through regex redaction masks before being returned or stored:
- **Passwords & Keys:** `password: '***REDACTED***'`, `api_key: '***REDACTED***'`
- **Private Keys:** `-----BEGIN ENCRYPTED PRIVATE KEY-----\n***REDACTED***\n-----END ENCRYPTED PRIVATE KEY-----`
- **Bearer & Session Tokens:** `bearer ***REDACTED***`, `aira_tok_***REDACTED***`

---

## 5. Risk-Based Approval Engine Integration

The Playbook Engine is deeply integrated with the `CentralizedApprovalEngine`:
- **Category A (Read-only / Diagnostics):**
  - E.g. Health check, service status, package inventory, config audit.
  - Executes **automatically** without delaying the engineer.
- **Category B (Mutating / Maintenance):**
  - E.g. Log vacuuming, cache deletion, configuration backup.
  - Automatically submits an approval request to `operational_pending_approvals`.
  - Returns:
    ```json
    {
      "status": "APPROVAL_PENDING",
      "approval_id": "appr_982ab112",
      "risk_level": "CATEGORY_B",
      "message": "Playbook requires operator approval before running mutating operational tasks."
    }
    ```
  - Only executes once an authorized operator or Superadmin approves via the Control Plane (`/api/v1/admin/approvals/{id}/resolve`).

---

## 6. Playbook API Reference

- `GET /api/v1/playbooks`: Lists available built-in and tenant custom playbooks.
- `GET /api/v1/playbooks/{playbook_id}`: Retrieves complete playbook details and YAML source.
- `POST /api/v1/playbooks/validate`: Validates YAML syntax and playbook structure.
- `POST /api/v1/playbooks/{playbook_id}/execute`:
  ```json
  {
    "targets": ["192.168.1.1", "10.0.0.1"],
    "variables": { "disk_threshold_pct": 90 },
    "bypass_approval": false
  }
  ```
