"""
AIRA OS — Edge Gateway Telemetry Ingestion Hub (Networking VIII / WP 8.4.3 & 8.4.4).

Provides:
- Gateway authentication & server-side tenant resolution
- Monotonic sequence tracking, replay prevention & duplicate detection
- Payload validation, size limits (512 KB), and evidence provenance
- Strict device ownership verification (rejects cross-tenant device references)
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.edge_gateway.db import ensure_gateway_schema
from core.edge_gateway.models import (
    EdgeGateway,
    GatewayEnvelope,
    GatewayHealth,
    GatewayHealthStatus,
    GatewayHeartbeat,
    GatewayLifecycleState,
    GatewaySequenceState,
    TelemetryType,
)
from core.tenant.manager import AuditLogger, InventoryManager, TenantManager
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.edge_gateway.ingestion")

MAX_PAYLOAD_BYTES = 524288  # 512 KB max per message
HEARTBEAT_TIMEOUT_SEC = 90.0


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class GatewayIngestionHub:
    """Central receiver and gatekeeper for outbound edge gateway telemetry."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_gateway_schema(self.db_path)
        self.tenant_mgr = TenantManager(self.db_path)
        self.inv_mgr = InventoryManager(self.db_path)
        self.audit = AuditLogger(self.db_path)

    def authenticate_gateway(
        self,
        auth_token: str,
        certificate_fingerprint: Optional[str] = None,
    ) -> Optional[EdgeGateway]:
        """
        Authenticates an edge gateway from cryptographic bearer credentials.
        Resolves tenant_id and site_id strictly from server-side database records.
        """
        if not auth_token or not auth_token.startswith("aira_gw_auth_"):
            return None

        token_hash = _hash_token(auth_token)
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT g.gateway_id, g.tenant_id, g.site_id, g.name, g.status, g.version,
                       g.certificate_fingerprint, g.auth_token_hash, g.last_seen_at_utc,
                       g.last_ip, g.metadata_json, g.created_at, g.updated_at,
                       t.status as tenant_status
                FROM operational_gateways g
                JOIN operational_tenants t ON g.tenant_id = t.tenant_id
                WHERE g.auth_token_hash = ?
                """,
                (token_hash,),
            ).fetchone()

            if not row:
                logger.warning("Gateway authentication failed: Auth token not found.")
                return None

            # Verify gateway is not revoked or decommissioned
            if row["status"] != GatewayLifecycleState.ACTIVE.value:
                logger.warning("Gateway authentication rejected: Gateway %s is %s", row["gateway_id"], row["status"])
                return None

            # Verify tenant is active
            if row["tenant_status"] not in ("ACTIVE", "MAINTENANCE"):
                logger.warning("Gateway authentication rejected: Tenant %s is %s", row["tenant_id"], row["tenant_status"])
                return None

            # Certificate fingerprint verification if provided
            if certificate_fingerprint and row["certificate_fingerprint"]:
                if row["certificate_fingerprint"] != certificate_fingerprint:
                    logger.warning("Gateway authentication rejected: Certificate fingerprint mismatch.")
                    return None

            meta = json.loads(row["metadata_json"] or "{}")
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
                metadata=meta,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def record_heartbeat(
        self,
        gateway: EdgeGateway,
        heartbeat: GatewayHeartbeat,
        client_ip: Optional[str] = None,
    ) -> GatewayHealth:
        """Processes periodic health report and updates gateway liveness."""
        hb_id = f"hb_{uuid.uuid4().hex[:12]}"
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        raw_json = json.dumps(heartbeat.to_dict())

        with topology_transaction(self.db_path, write=True) as conn:
            # Update gateway last seen
            conn.execute(
                """
                UPDATE operational_gateways
                SET last_seen_at_utc = ?, last_ip = ?, updated_at = ?
                WHERE gateway_id = ?
                """,
                (now_str, client_ip or gateway.last_ip, now_str, gateway.gateway_id),
            )
            # Insert heartbeat entry
            conn.execute(
                """
                INSERT INTO operational_gateway_heartbeats
                (heartbeat_id, gateway_id, tenant_id, site_id, timestamp_utc, cpu_utilization, memory_utilization, queue_depth, collector_status, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (hb_id, gateway.gateway_id, gateway.tenant_id, gateway.site_id, now_str, heartbeat.cpu_utilization, heartbeat.memory_utilization, heartbeat.queue_depth, heartbeat.collector_status, raw_json),
            )

        status = GatewayHealthStatus.ONLINE.value
        if heartbeat.collector_status != "HEALTHY" or heartbeat.queue_depth > 1000:
            status = GatewayHealthStatus.DEGRADED.value

        return GatewayHealth(
            gateway_id=gateway.gateway_id,
            tenant_id=gateway.tenant_id,
            site_id=gateway.site_id,
            status=status,
            last_heartbeat_at_utc=now_str,
            seconds_since_last_heartbeat=0.0,
            queue_depth=heartbeat.queue_depth,
            collector_status=heartbeat.collector_status,
            software_version=gateway.version,
        )

    def get_gateway_health(self, gateway_id: str) -> Optional[GatewayHealth]:
        """Calculates current gateway health and detects offline timeouts (> 90s)."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT gateway_id, tenant_id, site_id, status, version, last_seen_at_utc 
                FROM operational_gateways WHERE gateway_id = ?
                """,
                (gateway_id,),
            ).fetchone()
            if not row:
                return None

            hb_row = conn.execute(
                """
                SELECT queue_depth, collector_status, timestamp_utc 
                FROM operational_gateway_heartbeats 
                WHERE gateway_id = ? 
                ORDER BY timestamp_utc DESC LIMIT 1
                """,
                (gateway_id,),
            ).fetchone()

        now_epoch = time.time()
        last_seen = row["last_seen_at_utc"]
        elapsed_sec = None
        if last_seen:
            try:
                seen_epoch = time.mktime(time.strptime(last_seen, "%Y-%m-%dT%H:%M:%SZ"))
                elapsed_sec = max(0.0, now_epoch - seen_epoch)
            except Exception:
                pass

        status = GatewayHealthStatus.OFFLINE.value
        if elapsed_sec is not None and elapsed_sec <= HEARTBEAT_TIMEOUT_SEC:
            if hb_row and (hb_row["collector_status"] != "HEALTHY" or hb_row["queue_depth"] > 1000):
                status = GatewayHealthStatus.DEGRADED.value
            else:
                status = GatewayHealthStatus.ONLINE.value

        return GatewayHealth(
            gateway_id=row["gateway_id"],
            tenant_id=row["tenant_id"],
            site_id=row["site_id"],
            status=status,
            last_heartbeat_at_utc=last_seen,
            seconds_since_last_heartbeat=elapsed_sec,
            queue_depth=hb_row["queue_depth"] if hb_row else 0,
            collector_status=hb_row["collector_status"] if hb_row else "UNKNOWN",
            software_version=row["version"],
        )

    def ingest_telemetry_batch(
        self,
        gateway: EdgeGateway,
        envelopes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Validates, deduplicates, and ingests a batch of telemetry envelopes.
        Enforces strict tenant scoping, monotonic sequence checking, and payload size bounds.
        """
        now_epoch = time.time()
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))

        accepted_count = 0
        duplicate_count = 0
        error_items: List[Dict[str, str]] = []

        valid_types = {t.value for t in TelemetryType}

        with topology_transaction(self.db_path, write=True) as conn:
            # Load sequence state
            seq_row = conn.execute(
                "SELECT last_sequence_number, duplicate_count, dropped_count FROM operational_gateway_sequences WHERE gateway_id = ?",
                (gateway.gateway_id,),
            ).fetchone()
            current_seq = seq_row["last_sequence_number"] if seq_row else 0
            dups = seq_row["duplicate_count"] if seq_row else 0

            # Sort envelopes chronologically by sequence_number
            sorted_envelopes = sorted(envelopes, key=lambda e: e.get("sequence_number", 0))

            for env_dict in sorted_envelopes:
                seq = env_dict.get("sequence_number")
                env_id = env_dict.get("envelope_id")
                tel_type = env_dict.get("telemetry_type")
                payload = env_dict.get("payload", {})

                # 1. Basic schema validation
                if not env_id or not isinstance(seq, int) or seq <= 0:
                    error_items.append({"envelope_id": str(env_id), "error": "Invalid envelope_id or sequence_number."})
                    continue

                if tel_type not in valid_types:
                    error_items.append({"envelope_id": env_id, "error": f"Invalid telemetry_type '{tel_type}'."})
                    continue

                # 2. Payload size check (< 512 KB)
                payload_str = json.dumps(payload)
                if len(payload_str.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                    error_items.append({"envelope_id": env_id, "error": "Payload exceeds 512 KB size limit."})
                    continue

                # 3. Device ownership verification (prevents cross-tenant injection)
                target_dev_id = payload.get("device_id")
                if target_dev_id:
                    dev_row = conn.execute(
                        "SELECT tenant_id, site_id FROM operational_devices WHERE device_id = ?",
                        (target_dev_id,),
                    ).fetchone()
                    if not dev_row or dev_row["tenant_id"] != gateway.tenant_id or dev_row["site_id"] != gateway.site_id:
                        error_items.append({
                            "envelope_id": env_id,
                            "error": f"Security Violation: Target device '{target_dev_id}' does not belong to gateway's tenant/site.",
                        })
                        continue

                # 4. Monotonic sequence & duplicate check
                if seq <= current_seq:
                    # Duplicate or replay attempt!
                    duplicate_count += 1
                    dups += 1
                    continue

                # 5. Process Telemetry Payload into NMS Raw Metrics
                if tel_type == TelemetryType.INTERFACE_METRICS.value:
                    if target_dev_id and "interface_name" in payload:
                        conn.execute(
                            """
                            INSERT INTO nms_raw_metrics
                            (device_id, interface_name, metric_name, metric_value, unit, semantic_type, source_protocol, quality, measured_at, collected_at)
                            VALUES (?, ?, 'rx_utilization', ?, '%', 'COUNTER_RATE', 'EDGE_GATEWAY', 'RELIABLE', ?, ?)
                            """,
                            (
                                target_dev_id,
                                str(payload["interface_name"]),
                                float(payload.get("rx_utilization", 0.0)),
                                now_epoch,
                                now_epoch,
                            ),
                        )

                # Update sequence cursor
                current_seq = seq
                accepted_count += 1

            # Persist updated sequence state
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_gateway_sequences
                (gateway_id, last_sequence_number, last_received_at_utc, duplicate_count, dropped_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (gateway.gateway_id, current_seq, now_str, dups, seq_row["dropped_count"] if seq_row else 0),
            )

        logger.info(
            "Gateway %s ingestion completed: %d accepted, %d duplicates, %d errors. Last seq: %d",
            gateway.gateway_id, accepted_count, duplicate_count, len(error_items), current_seq
        )

        return {
            "gateway_id": gateway.gateway_id,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
            "error_count": len(error_items),
            "errors": error_items,
            "last_sequence_number": current_seq,
        }
