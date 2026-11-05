"""
AIRA OS — Secure Edge Gateway Enrollment Service (Networking VIII / WP 8.4.2).

Implements short-lived, single-use enrollment tokens, atomic redemption,
replay protection, mutual credential generation, and tenant-bound gateway activation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import secrets
import time
from typing import Any, Dict, Optional, Tuple
import uuid

from core.edge_gateway.db import ensure_gateway_schema
from core.edge_gateway.models import (
    EdgeGateway,
    EnrollmentTokenStatus,
    GatewayEnrollmentToken,
    GatewayLifecycleState,
)
from core.tenant.manager import AuditLogger, TenantManager
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.edge_gateway.enrollment")


def _hash_token(token: str) -> str:
    """Computes SHA-256 hash of an enrollment or auth token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class GatewayEnrollmentService:
    """Manages secure lifecycle of edge gateway onboarding and enrollment tokens."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_gateway_schema(self.db_path)
        self.audit = AuditLogger(self.db_path)
        self.tenant_mgr = TenantManager(self.db_path)

    def create_enrollment_token(
        self,
        tenant_id: str,
        site_id: str,
        created_by: str,
        duration_minutes: int = 15,
    ) -> Tuple[str, GatewayEnrollmentToken]:
        """
        Generates a short-lived, high-entropy, single-use gateway enrollment token.
        Returns (raw_token, token_record). The raw_token is never stored in plaintext.
        """
        # Validate tenant exists and is active
        tenant = self.tenant_mgr.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found.")
        if tenant.status != "ACTIVE":
            raise ValueError(f"Cannot generate enrollment token: Tenant is {tenant.status}.")

        # Check gateway quota
        quota = self.tenant_mgr.get_tenant_quota(tenant_id)
        if quota.is_gateway_quota_exceeded:
            raise ValueError(f"Quota Exceeded: Tenant {tenant_id} has reached maximum gateways ({quota.max_gateways}).")

        token_id = f"tok_{uuid.uuid4().hex[:12]}"
        raw_token = f"aira_gw_tok_{secrets.token_urlsafe(32)}"
        token_hash = _hash_token(raw_token)

        now_epoch = time.time()
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
        exp_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch + (duration_minutes * 60)))

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_gateway_tokens
                (token_id, token_hash, tenant_id, site_id, created_by, status, expires_at_utc, created_at)
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (token_id, token_hash, tenant_id, site_id, created_by, exp_str, now_str),
            )

        self.audit.log_action(
            username=created_by,
            action="GATEWAY_TOKEN_CREATED",
            resource_type="GATEWAY_TOKEN",
            resource_id=token_id,
            tenant_id=tenant_id,
            details={"site_id": site_id, "duration_minutes": duration_minutes},
        )

        logger.info("Created enrollment token %s for tenant %s site %s", token_id, tenant_id, site_id)
        record = GatewayEnrollmentToken(
            token_id=token_id,
            token_hash=token_hash,
            tenant_id=tenant_id,
            site_id=site_id,
            created_by=created_by,
            status=EnrollmentTokenStatus.ACTIVE.value,
            expires_at_utc=exp_str,
            created_at=now_str,
        )
        return raw_token, record

    def redeem_enrollment_token(
        self,
        raw_token: str,
        gateway_name: str,
        certificate_fingerprint: Optional[str] = None,
        version: str = "1.0.0",
        client_ip: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[EdgeGateway, str]:
        """
        Atomically redeems an enrollment token and registers the edge gateway.
        Guarantees single-use: concurrent redemptions fail safely.
        Returns (EdgeGateway, raw_auth_token).
        """
        if not raw_token or not raw_token.startswith("aira_gw_tok_"):
            raise ValueError("Malformed gateway enrollment token format.")

        token_hash = _hash_token(raw_token)
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=True) as conn:
            # Atomic conditional update: only one process can redeem this token
            cur = conn.execute(
                """
                UPDATE operational_gateway_tokens
                SET status = 'REDEEMED', redeemed_at_utc = ?
                WHERE token_hash = ? AND status = 'ACTIVE' AND expires_at_utc > ?
                """,
                (now_str, token_hash, now_str),
            )

            if cur.rowcount == 0:
                # Determine specific failure for logging
                row = conn.execute(
                    "SELECT status, expires_at_utc, tenant_id FROM operational_gateway_tokens WHERE token_hash = ?",
                    (token_hash,),
                ).fetchone()
                if not row:
                    logger.warning("Gateway enrollment rejected: Token not found.")
                    raise ValueError("Invalid gateway enrollment token.")
                elif row["status"] != "ACTIVE":
                    logger.warning("Gateway enrollment rejected: Token already redeemed or revoked (%s)", row["status"])
                    raise ValueError(f"Enrollment token is already {row['status']}.")
                elif row["expires_at_utc"] <= now_str:
                    logger.warning("Gateway enrollment rejected: Token expired at %s", row["expires_at_utc"])
                    raise ValueError("Enrollment token has expired.")
                else:
                    raise ValueError("Enrollment token could not be redeemed.")

            # Load redeemed token scope
            tok_row = conn.execute(
                "SELECT token_id, tenant_id, site_id, created_by FROM operational_gateway_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            tenant_id = tok_row["tenant_id"]
            site_id = tok_row["site_id"]
            token_id = tok_row["token_id"]

            # Generate Gateway Identity
            gateway_id = f"gw_{tenant_id[:8]}_{site_id[:8]}_{uuid.uuid4().hex[:8]}"
            raw_auth_token = f"aira_gw_auth_{secrets.token_urlsafe(32)}"
            auth_token_hash = _hash_token(raw_auth_token)
            meta_json = json.dumps(metadata or {})

            # Insert Gateway
            conn.execute(
                """
                INSERT INTO operational_gateways
                (gateway_id, tenant_id, site_id, name, status, version, certificate_fingerprint, auth_token_hash, last_seen_at_utc, last_ip, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (gateway_id, tenant_id, site_id, gateway_name.strip(), version, certificate_fingerprint, auth_token_hash, now_str, client_ip, meta_json, now_str, now_str),
            )

            # Initialize sequence tracking
            conn.execute(
                """
                INSERT INTO operational_gateway_sequences
                (gateway_id, last_sequence_number, last_received_at_utc, duplicate_count, dropped_count)
                VALUES (?, 0, ?, 0, 0)
                """,
                (gateway_id, now_str),
            )

        self.audit.log_action(
            username=f"gateway:{gateway_name}",
            action="GATEWAY_ENROLLED",
            resource_type="EDGE_GATEWAY",
            resource_id=gateway_id,
            tenant_id=tenant_id,
            details={"site_id": site_id, "token_id": token_id, "version": version},
            ip_address=client_ip,
        )

        logger.info("Successfully enrolled gateway %s (%s) for tenant %s site %s", gateway_id, gateway_name, tenant_id, site_id)
        gateway = EdgeGateway(
            gateway_id=gateway_id,
            tenant_id=tenant_id,
            site_id=site_id,
            name=gateway_name.strip(),
            status=GatewayLifecycleState.ACTIVE.value,
            version=version,
            certificate_fingerprint=certificate_fingerprint,
            auth_token_hash=auth_token_hash,
            last_seen_at_utc=now_str,
            last_ip=client_ip,
            metadata=metadata or {},
            created_at=now_str,
            updated_at=now_str,
        )
        return gateway, raw_auth_token

    def revoke_gateway(self, gateway_id: str, revoked_by: str, reason: str = "") -> bool:
        """Revokes an edge gateway, immediately invalidating its access."""
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute(
                "UPDATE operational_gateways SET status = 'REVOKED', updated_at = ? WHERE gateway_id = ?",
                (now_str, gateway_id),
            )
            success = cur.rowcount > 0

        if success:
            self.audit.log_action(
                username=revoked_by,
                action="GATEWAY_REVOKED",
                resource_type="EDGE_GATEWAY",
                resource_id=gateway_id,
                details={"reason": reason},
            )
            logger.warning("Revoked edge gateway %s by %s. Reason: %s", gateway_id, revoked_by, reason)
        return success
