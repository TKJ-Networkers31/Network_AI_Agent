"""
AIRA OS — Edge Gateway Unified Manager Facade (Networking VIII / WP 8.4.7 & 8.4.8).

Provides unified operational access for Central NOC operators, customer portals,
and ingestion endpoints:
- Gateway listing and tenant-scoped lookups
- Token enrollment and gateway activation
- Periodic heartbeat recording and liveness audits
- Telemetry ingestion and deduplication
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.edge_gateway.db import ensure_gateway_schema
from core.edge_gateway.enrollment import GatewayEnrollmentService
from core.edge_gateway.ingestion import GatewayIngestionHub
from core.edge_gateway.models import (
    EdgeGateway,
    GatewayEnrollmentToken,
    GatewayHealth,
    GatewayHeartbeat,
    GatewayLifecycleState,
)
from core.tenant.manager import AuditLogger, TenantManager
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.edge_gateway.manager")


class EdgeGatewayManager:
    """Authoritative service for edge gateway management and operations."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_gateway_schema(self.db_path)
        self.enrollment_svc = GatewayEnrollmentService(self.db_path)
        self.ingestion_hub = GatewayIngestionHub(self.db_path)
        self.tenant_mgr = TenantManager(self.db_path)
        self.audit = AuditLogger(self.db_path)

    def create_enrollment_token(
        self,
        tenant_id: str,
        site_id: str,
        created_by: str,
        duration_minutes: int = 15,
    ) -> Tuple[str, GatewayEnrollmentToken]:
        """Creates a single-use onboarding token."""
        return self.enrollment_svc.create_enrollment_token(
            tenant_id=tenant_id,
            site_id=site_id,
            created_by=created_by,
            duration_minutes=duration_minutes,
        )

    def enroll_gateway(
        self,
        raw_token: str,
        name: str,
        certificate_fingerprint: Optional[str] = None,
        version: str = "1.0.0",
        client_ip: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[EdgeGateway, str]:
        """Redeems an enrollment token and returns (EdgeGateway, raw_auth_token)."""
        return self.enrollment_svc.redeem_enrollment_token(
            raw_token=raw_token,
            gateway_name=name,
            certificate_fingerprint=certificate_fingerprint,
            version=version,
            client_ip=client_ip,
            metadata=metadata,
        )

    def get_gateway(self, tenant_id: str, gateway_id: str) -> Optional[EdgeGateway]:
        """Retrieves a gateway ensuring tenant isolation (IDOR safe)."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT gateway_id, tenant_id, site_id, name, status, version,
                       certificate_fingerprint, auth_token_hash, last_seen_at_utc,
                       last_ip, metadata_json, created_at, updated_at
                FROM operational_gateways
                WHERE tenant_id = ? AND gateway_id = ?
                """,
                (tenant_id, gateway_id),
            ).fetchone()
            if not row:
                return None
            return EdgeGateway(
                gateway_id=row["gateway_id"],
                tenant_id=row["tenant_id"],
                site_id=row["site_id"],
                name=row["name"],
                status=row["status"],
                version=row["version"],
                certificate_fingerprint=row["certificate_fingerprint"],
                auth_token_hash=row["auth_token_hash"],
                last_seen_at_utc=row["last_seen_at_utc"],
                last_ip=row["last_ip"],
                metadata=json.loads(row["metadata_json"] or "{}"),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_gateways(
        self,
        tenant_id: Optional[str] = None,
        site_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[EdgeGateway]:
        """Lists gateways with optional tenant and site filters."""
        query = """
            SELECT gateway_id, tenant_id, site_id, name, status, version,
                   certificate_fingerprint, auth_token_hash, last_seen_at_utc,
                   last_ip, metadata_json, created_at, updated_at
            FROM operational_gateways
            WHERE 1=1
        """
        params: List[Any] = []
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if site_id:
            query += " AND site_id = ?"
            params.append(site_id)
        if status:
            query += " AND status = ?"
            params.append(status.upper())
        query += " ORDER BY name ASC"

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                EdgeGateway(
                    gateway_id=r["gateway_id"],
                    tenant_id=r["tenant_id"],
                    site_id=r["site_id"],
                    name=r["name"],
                    status=r["status"],
                    version=r["version"],
                    certificate_fingerprint=r["certificate_fingerprint"],
                    auth_token_hash=r["auth_token_hash"],
                    last_seen_at_utc=r["last_seen_at_utc"],
                    last_ip=r["last_ip"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def revoke_gateway(self, gateway_id: str, revoked_by: str, reason: str = "") -> bool:
        """Revokes gateway access."""
        return self.enrollment_svc.revoke_gateway(gateway_id, revoked_by, reason)

    def record_heartbeat(
        self,
        auth_token: str,
        heartbeat_dict: Dict[str, Any],
        client_ip: Optional[str] = None,
    ) -> GatewayHealth:
        """Authenticates gateway and records health heartbeat."""
        gateway = self.ingestion_hub.authenticate_gateway(auth_token)
        if not gateway:
            raise PermissionError("Authentication failed: Invalid or revoked gateway credentials.")

        hb = GatewayHeartbeat(
            gateway_id=gateway.gateway_id,
            tenant_id=gateway.tenant_id,
            site_id=gateway.site_id,
            timestamp_utc=heartbeat_dict.get("timestamp_utc", ""),
            cpu_utilization=float(heartbeat_dict.get("cpu_utilization", 0.0)),
            memory_utilization=float(heartbeat_dict.get("memory_utilization", 0.0)),
            queue_depth=int(heartbeat_dict.get("queue_depth", 0)),
            oldest_message_age_sec=float(heartbeat_dict.get("oldest_message_age_sec", 0.0)),
            collector_status=heartbeat_dict.get("collector_status", "HEALTHY"),
            version=gateway.version,
        )
        return self.ingestion_hub.record_heartbeat(gateway, hb, client_ip)

    def ingest_telemetry(
        self,
        auth_token: str,
        envelopes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Authenticates gateway and ingests telemetry batch."""
        gateway = self.ingestion_hub.authenticate_gateway(auth_token)
        if not gateway:
            raise PermissionError("Authentication failed: Invalid or revoked gateway credentials.")

        return self.ingestion_hub.ingest_telemetry_batch(gateway, envelopes)

    def get_gateway_health(self, gateway_id: str) -> Optional[GatewayHealth]:
        """Returns health status of a gateway."""
        return self.ingestion_hub.get_gateway_health(gateway_id)
