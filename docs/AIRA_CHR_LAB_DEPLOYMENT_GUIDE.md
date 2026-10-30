# AIRA OS — MikroTik CHR v7 Controlled Lab Deployment Guide
## Architecture, Network Isolation, Read-Only Provisioning, and Rollback Preparation

**Workspace:** `D:\data\agent_ai`  
**Phase:** Phase 8.1 — Controlled CHR Live Verification Preparation  
**Target Environment:** Isolated Virtual Machine / Hypervisor (Proxmox VE, KVM/QEMU, VMware Workstation, VirtualBox)  
**Target Appliance:** MikroTik Cloud Hosted Router (CHR) RouterOS v7.14+ (Stable)  
**Safety Scope:** Strict Read-Only Testing; Zero Production Access; Zero Public WAN Bridging  

---

## 1. Executive Mission & Lab Safety Boundaries

This deployment guide establishes the operational and architectural requirements for spinning up a controlled, completely isolated MikroTik Cloud Hosted Router (CHR) v7 lab instance to verify AIRA OS network intelligence and diagnostic capabilities.

### Mandatory Safety Rules
1. **Air-Gapped / Host-Only Isolation**: The CHR lab virtual machine must **never** be bridged directly to an external production network, campus LAN, or public internet interface.
2. **Zero Auto-Remediation / Read-Only Credentials**: AIRA OS must be provisioned with credentials belonging to a dedicated read-only user group. Administrative or write-capable groups (`full`, `write`, `policy`) are strictly prohibited.
3. **Deterministic Identity Requirement**: The target router must be assigned an explicit identity (e.g. `Lab-CHR-Core-01`) before connection attempts. Probing unverified or default identities is treated as a security fault.
4. **Hypervisor Snapshot Prerequisite**: A verified clean-state VM snapshot must be taken prior to initiating any API or CLI interaction with AIRA OS.

> [!CAUTION]
> Do not connect AIRA OS to production routers or public IP addresses. This deployment guide is intended exclusively for authorized lab virtual machines running on host-only or internal virtual switches.

---

## 2. CHR v7 System Requirements & Sizing

MikroTik CHR is designed to run as an x86_64 guest appliance. For AIRA OS diagnostic verification, minimal compute resources are sufficient.

| Specification | Minimum Required | Recommended Lab Specification | Rationale |
| :--- | :--- | :--- | :--- |
| **vCPU** | 1 Core (x86_64) | 2 Cores | Handles concurrent SSH queries and routing table processing without latency spikes. |
| **RAM** | 256 MB | 512 MB – 1024 MB | Accommodates RouterOS v7 kernel, routing tables, and connection tracking tables. |
| **Virtual Disk** | 128 MB | 1 GB (QCOW2 or VMDK) | RouterOS system image is ~60 MB. 1 GB allows system logs, crash dumps, and snapshot overhead. |
| **Disk Controller** | IDE / SATA | VirtIO SCSI / SATA | High compatibility across KVM, Proxmox, and VirtualBox. |
| **Network Interfaces** | 2 Virtual NICs | 3 Virtual NICs (VirtIO-net or Intel e1000) | Separation of Out-of-Band Management (OOBM) from diagnostic data-plane topologies. |
| **License Level** | Free (64k trial) | Free Demo (1 Mbps) | 1 Mbps interface cap is more than sufficient for management SSH, telemetry, and CLI probing. |
| **RouterOS Version** | v7.12 | **v7.14.3 or latest Stable v7** | Stable RouterOS v7 CLI syntax for routing tables, BGP, and OSPF. |

---

## 3. Isolated Virtual Networking Architecture

The lab utilizes a multi-interface virtual topology where the management channel is strictly separated from simulated traffic interfaces:

```
+-------------------------------------------------------------------------------+
| HOST MACHINE (Windows / ThinkPad X270: 10.10.10.1)                             |
|                                                                               |
|   +--------------------------+         +----------------------------------+   |
|   | AIRA OS Backend & PWA    |         | Virtual Switch / Host-Only Net   |   |
|   | (Port 8000 / Port 5173)  | <=====> | (vboxnet0 / vmnet1 / br-lab)     |   |
|   +--------------------------+   SSH   | Subnet: 10.10.10.0/24            |   |
|                                        +-----------------+----------------+   |
+----------------------------------------------------------|--------------------+
                                                           |
                                  +------------------------+--------------------+
                                  | GUEST VM: MikroTik CHR v7                   |
                                  | Identity: Lab-CHR-Core-01                   |
                                  |                                             |
                                  | [ether1: 10.10.10.10/24] (Management OOB)   |
                                  |   - SSH Daemon: Port 22                     |
                                  |   - Firewall: Allow SSH only from .1        |
                                  |                                             |
                                  | [ether2: 172.16.10.1/24] (Simulated LAN)    |
                                  |   - Loopback & Data-plane diagnostics       |
                                  |                                             |
                                  | [ether3: 198.51.100.1/24] (Simulated WAN)   |
                                  |   - Isolated dummy upstream (Blackhole)     |
                                  +---------------------------------------------+
```

### 3.1. Interface Allocation
1. **`ether1` (OOB Management)**: Connected to the host-only virtual switch (`10.10.10.0/24`). Used exclusively by AIRA OS `ConnectionManager` for SSH command execution.
2. **`ether2` (Diagnostic LAN)**: Connected to an isolated internal lab switch (`172.16.10.0/24`). Used to simulate LAN subnets, DHCP leases, and bridge interfaces for diagnostic playbooks.
3. **`ether3` (Diagnostic WAN / Upstream)**: Connected to a blackhole or simulated ISP gateway (`198.51.100.0/24`). Used to simulate default routing, gateway unreachable scenarios, and DNS forwarding failures.

---

## 4. IP Addressing & Subnet Plan

| Interface / Component | IPv4 Address | Subnet Mask | Gateway | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **AIRA OS Host** | `10.10.10.1` | `255.255.255.0` (`/24`) | *None* | Originating IP for diagnostic SSH connections. |
| **CHR Management (`ether1`)** | `10.10.10.10` | `255.255.255.0` (`/24`) | `10.10.10.1` | Static management IP for AIRA OS inventory. |
| **CHR Simulated LAN (`ether2`)** | `172.16.10.1` | `255.255.255.0` (`/24`) | *Local* | Simulated LAN gateway for ARP and DHCP inspection. |
| **CHR Simulated WAN (`ether3`)** | `198.51.100.2` | `255.255.255.0` (`/24`) | `198.51.100.1` | Simulated ISP uplink for routing investigation. |
| **CHR Loopback (`lo-diag`)** | `10.255.255.1` | `255.255.255.255` (`/32`) | *Local* | Router ID anchor for OSPF/BGP verification. |

---

## 5. RouterOS v7 Base Configuration Procedure

Execute the following commands in the MikroTik CHR console during initial provisioning.

### Step 5.1: Device Identity Configuration
Set an explicit, unambiguous identity to satisfy AIRA OS preflight validation:
```routeros
/system identity set name="Lab-CHR-Core-01"
```

### Step 5.2: Management & Lab IP Configuration
Assign IP addresses to the provisioned interfaces:
```routeros
/ip address add address=10.10.10.10/24 interface=ether1 comment="AIRA Management OOB"
/ip address add address=172.16.10.1/24 interface=ether2 comment="Lab Simulated LAN"
/ip address add address=198.51.100.2/24 interface=ether3 comment="Lab Simulated WAN"
/interface bridge add name=lo-diag comment="Diagnostic Loopback"
/ip address add address=10.255.255.1/32 interface=lo-diag comment="Loopback IP"
```

### Step 5.3: Static Routing Setup
Configure a test default route and lab routing entries:
```routeros
/ip route add dst-address=0.0.0.0/0 gateway=198.51.100.1 distance=1 comment="Default Gateway"
/ip route add dst-address=10.0.0.0/8 gateway=172.16.10.2 distance=10 comment="Diagnostic Internal Route"
```

---

## 6. SSH Hardening & Read-Only Account Provisioning

AIRA OS requires a dedicated, unprivileged read-only account. The account must not have permission to execute configuration changes, install packages, write files, or reboot the router.

### Step 6.1: Define the Read-Only Group
Create the `aira-readonly` group with restricted policies:
```routeros
/user group add name=aira-readonly policy=read,api,ssh,!write,!policy,!test,!password,!sniff,!sensitive,!reboot,!romon
```
*Verification of policies:*
- `read`: Permitted (allows `/... print` commands).
- `ssh`: Permitted (allows incoming SSH connections).
- `write`: **FORBIDDEN** (blocks `/... add`, `set`, `remove`, `enable`, `disable`).
- `policy`: **FORBIDDEN** (blocks user and privilege management).
- `reboot`: **FORBIDDEN** (blocks `/system reboot`, `/system shutdown`).
- `sensitive`: **FORBIDDEN** (blocks unmasking of plaintext secrets in exports).
- `test`: **FORBIDDEN** (blocks bandwidth tests and raw ping tools from mutating interface states).

### Step 6.2: Create the Dedicated Audit User
Create the `aira-audit` user bound to the `aira-readonly` group and restricted to the management IP:
```routeros
/user add name=aira-audit group=aira-readonly password="AiraSecureAudit2026!#" address=10.10.10.1/32 comment="Dedicated AIRA OS Read-Only Diagnostic Service Account"
```

### Step 6.3: SSH Daemon Hardening
Configure RouterOS SSH daemon to enforce strong cryptographic ciphers and disable interactive TCP forwarding:
```routeros
/ip ssh set strong-crypto=yes forwarding-enabled=no always-allow-password-login=yes
/ip service set ssh port=22 address=10.10.10.0/24 disabled=no
/ip service set telnet disabled=yes
/ip service set ftp disabled=yes
/ip service set www disabled=yes
/ip service set api disabled=yes
/ip service set winbox disabled=yes
/ip service set api-ssl disabled=yes
```

### Step 6.4: Management Interface Firewalling
Protect the management port from unauthorized probes:
```routeros
/ip firewall filter add chain=input in-interface=ether1 src-address=10.10.10.1 protocol=tcp dst-port=22 action=accept comment="Allow SSH from AIRA OS Host"
/ip firewall filter add chain=input in-interface=ether1 protocol=tcp dst-port=22 action=drop comment="Drop SSH from any other source"
/ip firewall filter add chain=input connection-state=established,related action=accept comment="Allow established/related"
```

---

## 7. Hypervisor Snapshot & Rollback Preparation

Before connecting AIRA OS to the CHR instance, create a hypervisor snapshot to ensure instantaneous rollback to a known baseline.

### 7.1. RouterOS Internal Configuration Backup
Run from the CHR console:
```routeros
/system backup save name=clean_baseline_v7 encryption=none
/export file=clean_baseline_v7
```

### 7.2. Hypervisor VM Snapshot Creation
Depending on the lab hypervisor, execute the corresponding command:

**KVM / Proxmox VE:**
```bash
qm snapshot <VM_ID> BASELINE_READY --description "Clean RouterOS v7.14 with aira-audit read-only user"
```

**VMware Workstation / ESXi:**
```bash
vim-cmd vmsvc/snapshot.create <VM_ID> "BASELINE_READY" "Clean RouterOS v7 baseline" 0 0
```

**VirtualBox:**
```bash
VBoxManage snapshot "MikroTik-CHR-Lab" take "BASELINE_READY" --description "Clean RouterOS v7 baseline"
```

---

## 8. Pre-Flight Verification Checklist

Before initiating any test from AIRA OS, the lab operator must manually verify each checklist item:

- [ ] **Hypervisor Isolation**: VM network interface 1 is connected to Host-Only switch (`10.10.10.0/24`). Zero bridge to WAN/Internet.
- [ ] **Host Reachability**: Ping from host to `10.10.10.10` succeeds with latency < 5 ms.
- [ ] **SSH Banner Verification**: Running `nc -vn 10.10.10.10 22` or `Test-NetConnection 10.10.10.10 -Port 22` returns standard SSH banner (`SSH-2.0-MikroTik...`).
- [ ] **Account Validation**: Manual SSH login with `aira-audit` succeeds and lands in RouterOS CLI prompt.
- [ ] **Read-Only Policy Test**: Running `/system identity set name="Hacked"` inside `aira-audit` session returns `action failed: not enough permissions (9)`.
- [ ] **Snapshot Verified**: `BASELINE_READY` snapshot confirmed present in hypervisor management console.
- [ ] **AIRA Inventory Registered**: Target `10.10.10.10` registered in AIRA OS inventory with label `Lab-CHR-Core-01`.
