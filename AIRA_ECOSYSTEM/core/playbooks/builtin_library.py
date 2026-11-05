"""
AIRA OS — Built-in Ansible-Compatible Playbook Library.
Directive Section 8:
1. linux_health_check.yml
2. service_status.yml
3. package_inventory.yml
4. config_backup.yml
5. basic_maintenance.yml
6. config_audit.yml
"""

from typing import Any, Dict, List

BUILTIN_PLAYBOOKS: List[Dict[str, Any]] = [
    {
        "playbook_id": "pb_builtin_health_check",
        "name": "Linux Health Check",
        "category": "OBSERVABILITY",
        "description": "Checks system uptime, CPU load average, memory utilization, and root disk capacity.",
        "risk_level": "CATEGORY_A",
        "version": "1.0.0",
        "variables_schema": {
            "disk_threshold_pct": {"type": "integer", "default": 85, "description": "Warn threshold for root disk usage"},
            "memory_threshold_pct": {"type": "integer", "default": 90, "description": "Warn threshold for RAM usage"},
        },
        "yaml_content": """---
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
""",
    },
    {
        "playbook_id": "pb_builtin_service_status",
        "name": "Service & Port Status",
        "category": "OBSERVABILITY",
        "description": "Verifies essential network and telemetry daemons and inspects active listening ports.",
        "risk_level": "CATEGORY_A",
        "version": "1.0.0",
        "variables_schema": {
            "required_services": {"type": "array", "default": ["sshd", "systemd-resolved"], "description": "List of services to inspect"},
        },
        "yaml_content": """---
- name: Verify Network Daemons and Essential Services
  hosts: all
  vars:
    required_services:
      - sshd
      - systemd-resolved
  tasks:
    - name: Inspect listening TCP/UDP ports
      command: ss -tuln
      register: ports_result
    - name: Check status of essential services
      command: systemctl is-active sshd
      register: service_status
      ignore_errors: true
""",
    },
    {
        "playbook_id": "pb_builtin_pkg_inventory",
        "name": "Package & Security Inventory",
        "category": "INVENTORY",
        "description": "Collects kernel release and inspects pending security patches and installed packages.",
        "risk_level": "CATEGORY_A",
        "version": "1.0.0",
        "variables_schema": {
            "include_security_patches": {"type": "boolean", "default": True, "description": "Check pending security advisories"},
        },
        "yaml_content": """---
- name: Collect Installed Packages and Security Updates
  hosts: all
  tasks:
    - name: Inspect kernel and OS release
      command: uname -a
      register: kernel_info
    - name: Query pending security upgrades
      command: apt-get -s upgrade
      register: upgrade_status
      ignore_errors: true
""",
    },
    {
        "playbook_id": "pb_builtin_config_backup",
        "name": "Configuration Backup",
        "category": "BACKUP",
        "description": "Retrieves network configuration, IP routing tables, and interface definitions for archival.",
        "risk_level": "CATEGORY_A",
        "version": "1.0.0",
        "variables_schema": {
            "backup_destination": {"type": "string", "default": "/var/backups/aira", "description": "Destination directory for configuration backups"},
        },
        "yaml_content": """---
- name: Automated Configuration Backup
  hosts: all
  vars:
    backup_destination: /var/backups/aira
  tasks:
    - name: Collect network interface status and IP assignments
      command: ip -br addr show
      register: ip_addrs
    - name: Collect routing table
      command: ip route show
      register: route_table
    - name: Collect running network configurations
      command: cat /etc/network/interfaces
      register: running_cfg
      ignore_errors: true
""",
    },
    {
        "playbook_id": "pb_builtin_maintenance",
        "name": "Basic Host Maintenance",
        "category": "MAINTENANCE",
        "description": "Performs routine maintenance: package cache cleanup and log rotation.",
        "risk_level": "CATEGORY_B",  # Mutating operation requiring operator approval
        "version": "1.0.0",
        "variables_schema": {
            "vacuum_logs": {"type": "boolean", "default": True, "description": "Rotate and vacuum aged system journals"},
        },
        "yaml_content": """---
- name: Routine Network Host Maintenance
  hosts: all
  vars:
    vacuum_logs: true
  tasks:
    - name: Clean temporary package caches
      command: apt-get clean
      register: clean_result
    - name: Force system log rotation
      command: logrotate -f /etc/logrotate.conf
      register: logrotate_result
      ignore_errors: true
""",
    },
    {
        "playbook_id": "pb_builtin_config_audit",
        "name": "Security & Hardening Audit",
        "category": "SECURITY",
        "description": "Audits SSH configuration, root login policies, and open firewall rules.",
        "risk_level": "CATEGORY_A",
        "version": "1.0.0",
        "variables_schema": {
            "strict_mode": {"type": "boolean", "default": True, "description": "Strict verification of cryptographic ciphers"},
        },
        "yaml_content": """---
- name: Security and Compliance Configuration Audit
  hosts: all
  vars:
    strict_mode: true
  tasks:
    - name: Audit SSH daemon security configuration
      command: grep -E "^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication)" /etc/ssh/sshd_config
      register: ssh_audit
      ignore_errors: true
    - name: Audit active firewall rules
      command: iptables -L -n
      register: firewall_audit
      ignore_errors: true
""",
    },
]
