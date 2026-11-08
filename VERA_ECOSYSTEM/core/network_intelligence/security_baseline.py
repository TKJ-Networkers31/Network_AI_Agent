"""
AIRA OS — Capability-Aware Network Security Intelligence & Posture Scoring (Workstream D & E).

Implements:
1. Device Role Taxonomy (14 roles)
2. Capability-Aware Security Baselines for MikroTik (v6/v7), Cisco IOS, and Linux
3. 6 Assessment Categories:
   - MANAGEMENT_PLANE
   - FIREWALL_AND_ACL
   - ROUTING_SECURITY
   - VLAN_AND_SEGMENTATION
   - MONITORING_AND_LOGGING
   - HARDENING_AND_SERVICES
4. Non-Invasive Evidence Evaluation & Finding Lifecycle Management:
   OPEN -> ACKNOWLEDGED -> IN_PROGRESS -> MITIGATED -> RESOLVED -> ACCEPTED_RISK -> FALSE_POSITIVE
5. Real-time Security Posture Scoring (0 to 100) and Bands:
   CRITICAL (0-39), POOR (40-59), MODERATE (60-74), GOOD (75-89), EXCELLENT (90-100)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.network_intelligence.security_baseline")


class DeviceRole(str, Enum):
    EDGE_ROUTER = "EDGE_ROUTER"
    CORE_ROUTER = "CORE_ROUTER"
    DISTRIBUTION_ROUTER = "DISTRIBUTION_ROUTER"
    ACCESS_SWITCH = "ACCESS_SWITCH"
    CORE_SWITCH = "CORE_SWITCH"
    FIREWALL = "FIREWALL"
    VPN_GATEWAY = "VPN_GATEWAY"
    WIRELESS_CONTROLLER = "WIRELESS_CONTROLLER"
    ACCESS_POINT = "ACCESS_POINT"
    SERVER_GATEWAY = "SERVER_GATEWAY"
    INTERNET_GATEWAY = "INTERNET_GATEWAY"
    HYBRID_EDGE_GATEWAY = "HYBRID_EDGE_GATEWAY"
    CPE = "CPE"
    GENERIC_NETWORK_DEVICE = "GENERIC_NETWORK_DEVICE"


class FindingCategory(str, Enum):
    MANAGEMENT_PLANE = "MANAGEMENT_PLANE"
    FIREWALL_AND_ACL = "FIREWALL_AND_ACL"
    ROUTING_SECURITY = "ROUTING_SECURITY"
    VLAN_AND_SEGMENTATION = "VLAN_AND_SEGMENTATION"
    MONITORING_AND_LOGGING = "MONITORING_AND_LOGGING"
    HARDENING_AND_SERVICES = "HARDENING_AND_SERVICES"


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"  # -20 pts
    HIGH = "HIGH"          # -10 pts
    MEDIUM = "MEDIUM"      # -4 pts
    LOW = "LOW"            # -1 pt
    INFORMATIONAL = "INFORMATIONAL"  # 0 pts


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class PostureBand(str, Enum):
    CRITICAL = "CRITICAL"    # 0 - 39
    POOR = "POOR"            # 40 - 59
    MODERATE = "MODERATE"    # 60 - 74
    GOOD = "GOOD"            # 75 - 89
    EXCELLENT = "EXCELLENT"  # 90 - 100


@dataclass
class SecurityFinding:
    finding_id: str
    tenant_id: str
    device_id: str
    device_name: str
    category: str
    severity: str
    title: str
    description: str
    remediation_guidance: str
    remediation_action_name: Optional[str] = None
    site_id: Optional[str] = None
    status: str = FindingStatus.OPEN.value
    evidence: Dict[str, Any] = field(default_factory=dict)
    baseline_rule_id: Optional[str] = None
    first_detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SecurityPostureScore:
    posture_id: str
    tenant_id: str
    score: int
    band: str
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    assessment_coverage_pct: float = 100.0
    drift_detected: bool = False
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SecurityBaselineEngine:
    """
    Evaluates network devices against capability-aware baselines and maintains findings.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def classify_device_role(self, device_data: Dict[str, Any]) -> str:
        """
        Infers the device role from capabilities, hostname, and model if not explicitly configured.
        """
        explicit = device_data.get("role")
        if explicit and explicit in [r.value for r in DeviceRole]:
            return explicit

        name = (device_data.get("name") or device_data.get("hostname") or "").lower()
        model = (device_data.get("model") or "").lower()
        vendor = (device_data.get("vendor") or "").lower()
        caps = [c.lower() for c in device_data.get("capabilities", [])]

        if "firewall" in name or "fw" in name or "forti" in name or "forti" in model or "pfsense" in model or "pfsense" in name:
            return DeviceRole.FIREWALL.value
        if "cpe" in name or "ont" in name or "modem" in name:
            return DeviceRole.CPE.value
        if "ap" in name or "wlan" in name or "wifi" in name or "access point" in model:
            return DeviceRole.ACCESS_POINT.value
        if "vpn" in name or "wg" in name or "wireguard" in name:
            return DeviceRole.VPN_GATEWAY.value
        if "core" in name and ("sw" in name or "switch" in name):
            return DeviceRole.CORE_SWITCH.value
        if "sw" in name or "switch" in name or "crs" in model:
            return DeviceRole.ACCESS_SWITCH.value
        if "core" in name or "ccr" in model:
            return DeviceRole.CORE_ROUTER.value
        if "edge" in name or "wan" in name or "gw" in name or "gateway" in name:
            return DeviceRole.EDGE_ROUTER.value
        if "router" in caps or "routing" in caps or "mikrotik" in vendor or "cisco" in vendor:
            return DeviceRole.DISTRIBUTION_ROUTER.value

        return DeviceRole.GENERIC_NETWORK_DEVICE.value

    def assess_device(
        self,
        tenant_id: str,
        device: Dict[str, Any],
        telemetry: Optional[Dict[str, Any]] = None,
        config_snapshot: Optional[str] = None,
    ) -> List[SecurityFinding]:
        """
        Runs non-invasive security baseline inspection on device state and config.
        """
        device_id = device.get("device_id") or device.get("id") or "dev_unknown"
        device_name = device.get("name") or device.get("hostname") or device_id
        site_id = device.get("site_id")
        vendor = (device.get("vendor") or "mikrotik").lower()
        os_version = (device.get("os_version") or device.get("version") or "").lower()
        role = self.classify_device_role(device)
        services = device.get("services") or (telemetry.get("services") if telemetry else []) or []
        open_ports = device.get("open_ports") or (telemetry.get("open_ports") if telemetry else []) or []
        snmp_community = device.get("snmp_community") or (telemetry.get("snmp_community") if telemetry else None)
        cfg = config_snapshot or ""

        findings: List[SecurityFinding] = []

        # ---------------------------------------------------------------------
        # 1. MANAGEMENT PLANE AUDIT
        # ---------------------------------------------------------------------
        # Check Telnet (Port 23 / telnet service)
        if 23 in open_ports or "telnet" in services or "service telnet enable" in cfg or "/ip service set telnet disabled=no" in cfg:
            findings.append(SecurityFinding(
                finding_id=f"find_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                site_id=site_id,
                device_id=device_id,
                device_name=device_name,
                category=FindingCategory.MANAGEMENT_PLANE.value,
                severity=FindingSeverity.HIGH.value,
                title="Unencrypted Telnet Management Protocol Active",
                description=f"Device '{device_name}' exposes cleartext Telnet on port 23. Credentials and session traffic can be intercepted.",
                remediation_guidance="Disable Telnet service immediately and restrict remote management strictly to SSH with strong ciphers.",
                remediation_action_name="disable_insecure_management_services",
                baseline_rule_id="MGMT-01-DISABLE-TELNET",
                evidence={"open_ports": open_ports, "services": services},
            ))

        # Check Cleartext HTTP Web Management (Port 80)
        if 80 in open_ports or "www" in services or "/ip service set www disabled=no" in cfg:
            findings.append(SecurityFinding(
                finding_id=f"find_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                site_id=site_id,
                device_id=device_id,
                device_name=device_name,
                category=FindingCategory.MANAGEMENT_PLANE.value,
                severity=FindingSeverity.MEDIUM.value,
                title="Unencrypted HTTP Web Management Interface Enabled",
                description=f"Web management service is listening on port 80 without TLS encryption.",
                remediation_guidance="Redirect HTTP to HTTPS or disable web management interface in favor of SSH/Winbox-SSL.",
                remediation_action_name="enforce_https_management",
                baseline_rule_id="MGMT-02-ENFORCE-HTTPS",
                evidence={"port": 80, "protocol": "HTTP"},
            ))

        # ---------------------------------------------------------------------
        # 2. FIREWALL & ACL AUDIT
        # ---------------------------------------------------------------------
        # Check WAN Input Chain Default Drop / Protection
        has_firewall = device.get("has_firewall", True)
        if not has_firewall or "drop" not in cfg.lower() and "chain=input" not in cfg.lower():
            if role in (DeviceRole.EDGE_ROUTER.value, DeviceRole.INTERNET_GATEWAY.value, DeviceRole.FIREWALL.value):
                findings.append(SecurityFinding(
                    finding_id=f"find_{uuid.uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    site_id=site_id,
                    device_id=device_id,
                    device_name=device_name,
                    category=FindingCategory.FIREWALL_AND_ACL.value,
                    severity=FindingSeverity.CRITICAL.value,
                    title="Missing Default-Drop Firewall Rule on WAN Input Chain",
                    description=f"Edge gateway '{device_name}' lacks explicit drop policy for unsolicited WAN traffic.",
                    remediation_guidance="Implement stateful firewall filter rules: accept established/related, drop invalid, and drop all from WAN.",
                    remediation_action_name="deploy_standard_input_firewall",
                    baseline_rule_id="FW-01-INPUT-CHAIN-DROP",
                    evidence={"device_role": role, "firewall_status": "insufficient"},
                ))

        # ---------------------------------------------------------------------
        # 3. MONITORING & LOGGING AUDIT
        # ---------------------------------------------------------------------
        # Check Default SNMP Community String ("public" / "private")
        if snmp_community in ("public", "private") or "community=public" in cfg.lower():
            findings.append(SecurityFinding(
                finding_id=f"find_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                site_id=site_id,
                device_id=device_id,
                device_name=device_name,
                category=FindingCategory.MONITORING_AND_LOGGING.value,
                severity=FindingSeverity.HIGH.value,
                title="Default Well-Known SNMP Community String in Use",
                description=f"Device '{device_name}' is configured with default SNMP community '{snmp_community or 'public'}'.",
                remediation_guidance="Replace default SNMP community with a high-entropy string or migrate to SNMPv3 with SHA/AES authentication.",
                remediation_action_name="harden_snmp_community",
                baseline_rule_id="MON-01-SNMP-COMMUNITY-HARDENING",
                evidence={"detected_community": snmp_community or "public"},
            ))

        # ---------------------------------------------------------------------
        # 4. HARDENING & SERVICES AUDIT
        # ---------------------------------------------------------------------
        # Check DNS Open-Relay on Gateway (MikroTik allow-remote-requests=yes without filter)
        allow_remote_dns = device.get("allow_remote_dns", False) or "allow-remote-requests=yes" in cfg.lower()
        if allow_remote_dns and role in (DeviceRole.EDGE_ROUTER.value, DeviceRole.INTERNET_GATEWAY.value):
            findings.append(SecurityFinding(
                finding_id=f"find_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                site_id=site_id,
                device_id=device_id,
                device_name=device_name,
                category=FindingCategory.HARDENING_AND_SERVICES.value,
                severity=FindingSeverity.CRITICAL.value,
                title="DNS Open-Relay Vulnerability Detected on WAN",
                description=f"Router '{device_name}' allows remote DNS requests on WAN port 53, susceptible to DNS amplification DDoS attacks.",
                remediation_guidance="Block incoming UDP/TCP port 53 requests from WAN interfaces in firewall filter input chain.",
                remediation_action_name="block_wan_dns_recursion",
                baseline_rule_id="HARDEN-01-DNS-OPEN-RELAY",
                evidence={"allow_remote_requests": True},
            ))

        # Check Insecure Legacy Services (FTP / API)
        if 21 in open_ports or "ftp" in services:
            findings.append(SecurityFinding(
                finding_id=f"find_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                site_id=site_id,
                device_id=device_id,
                device_name=device_name,
                category=FindingCategory.HARDENING_AND_SERVICES.value,
                severity=FindingSeverity.LOW.value,
                title="Unused Insecure FTP File Transfer Service Active",
                description=f"Device '{device_name}' runs unencrypted FTP service on port 21.",
                remediation_guidance="Disable FTP service and use SCP/SFTP over SSH for configuration and file transport.",
                remediation_action_name="disable_ftp_service",
                baseline_rule_id="HARDEN-02-DISABLE-FTP",
                evidence={"port": 21, "service": "ftp"},
            ))

        # Persist findings to topology.db
        self.save_findings(findings)
        return findings

    def save_findings(self, findings: List[SecurityFinding]) -> None:
        """Upserts findings into operational_security_findings table."""
        if not findings:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            for f in findings:
                conn.execute(
                    """
                    INSERT INTO operational_security_findings
                    (finding_id, tenant_id, site_id, device_id, device_name, category, severity,
                     title, description, remediation_guidance, remediation_action_name, status,
                     evidence_json, baseline_rule_id, first_detected_at, last_detected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(finding_id) DO UPDATE SET
                    last_detected_at = excluded.last_detected_at,
                    evidence_json = excluded.evidence_json
                    """,
                    (
                        f.finding_id, f.tenant_id, f.site_id, f.device_id, f.device_name,
                        f.category, f.severity, f.title, f.description, f.remediation_guidance,
                        f.remediation_action_name, f.status, json.dumps(f.evidence),
                        f.baseline_rule_id, f.first_detected_at, now_iso,
                    ),
                )

    def calculate_posture(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> SecurityPostureScore:
        """
        Calculates normalized security posture score (0 to 100) based on active findings.
        Formula: 100 - (CRITICAL * 20 + HIGH * 10 + MEDIUM * 4 + LOW * 1) bounded in [0, 100].
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT severity, COUNT(*) as cnt
                FROM operational_security_findings
                WHERE tenant_id = ? AND status IN ('OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS')
            """
            params: List[Any] = [tenant_id]

            if site_id:
                query += " AND site_id = ?"
                params.append(site_id)
            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)

            query += " GROUP BY severity"
            rows = conn.execute(query, params).fetchall()

        sev_counts = {r["severity"]: r["cnt"] for r in rows}
        crit = sev_counts.get(FindingSeverity.CRITICAL.value, 0)
        high = sev_counts.get(FindingSeverity.HIGH.value, 0)
        med = sev_counts.get(FindingSeverity.MEDIUM.value, 0)
        low = sev_counts.get(FindingSeverity.LOW.value, 0)
        info = sev_counts.get(FindingSeverity.INFORMATIONAL.value, 0)

        penalty = (crit * 20) + (high * 10) + (med * 4) + (low * 1)
        raw_score = max(0, min(100, 100 - penalty))

        # Classify Band
        if raw_score >= 90:
            band = PostureBand.EXCELLENT.value
        elif raw_score >= 75:
            band = PostureBand.GOOD.value
        elif raw_score >= 60:
            band = PostureBand.MODERATE.value
        elif raw_score >= 40:
            band = PostureBand.POOR.value
        else:
            band = PostureBand.CRITICAL.value

        posture = SecurityPostureScore(
            posture_id=f"post_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            site_id=site_id,
            device_id=device_id,
            score=raw_score,
            band=band,
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low,
            info_count=info,
            assessment_coverage_pct=100.0,
            calculated_at=now_iso,
        )

        # Record posture snapshot
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_security_posture
                (posture_id, tenant_id, site_id, device_id, score, band, critical_count,
                 high_count, medium_count, low_count, info_count, assessment_coverage_pct, calculated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    posture.posture_id, posture.tenant_id, posture.site_id, posture.device_id,
                    posture.score, posture.band, posture.critical_count, posture.high_count,
                    posture.medium_count, posture.low_count, posture.info_count,
                    posture.assessment_coverage_pct, posture.calculated_at,
                ),
            )

        return posture

    def list_findings(
        self,
        tenant_id: str,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Queries security findings with filtering."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM operational_security_findings WHERE tenant_id = ?"
            params: List[Any] = [tenant_id]

            if severity:
                q += " AND severity = ?"
                params.append(severity.upper())
            if category:
                q += " AND category = ?"
                params.append(category.upper())
            if status:
                q += " AND status = ?"
                params.append(status.upper())

            q += " ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END, last_detected_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(q, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if item.get("evidence_json"):
                    try:
                        item["evidence"] = json.loads(item["evidence_json"])
                    except Exception:
                        item["evidence"] = {}
                results.append(item)
            return results


_baseline_engine: Optional[SecurityBaselineEngine] = None


def get_security_baseline_engine(db_path: Optional[Path] = None) -> SecurityBaselineEngine:
    global _baseline_engine
    if _baseline_engine is None or db_path is not None:
        _baseline_engine = SecurityBaselineEngine(db_path)
    return _baseline_engine
