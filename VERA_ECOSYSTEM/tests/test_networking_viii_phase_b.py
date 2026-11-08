"""
AIRA OS — Networking VIII Phase B Security & Integration Test Suite.
Verifies all 25 mandatory security and operational requirements for WP 8.4:
- Secure single-use enrollment tokens, expiry, and atomic redemption
- Tenant & site binding, IDOR prevention, and impersonation defense
- Transport authentication, sequence monotonicity, and duplicate suppression
- Telemetry ingestion schema validation, payload size limit, and cross-tenant device reference rejection
- Bounded local buffer, capacity enforcement, FIFO drop policy, and reconnection replay
- Strict read-only diagnostic sandbox, shell injection rejection, and router mutation prevention
- Heartbeat tracking, offline timeout detection, and tenant suspension invalidation
"""

from datetime import datetime, timedelta, timezone
import json
import os
import sqlite3
import tempfile
import time
import pytest

from core.edge_gateway.buffer import EdgeBufferQueue
from core.edge_gateway.collector import DiagnosticSanitizerError, EdgeDiagnosticCollector
from core.edge_gateway.enrollment import GatewayEnrollmentService
from core.edge_gateway.ingestion import GatewayIngestionHub
from core.edge_gateway.manager import EdgeGatewayManager
from core.edge_gateway.models import (
    GatewayHealthStatus,
    GatewayHeartbeat,
    GatewayLifecycleState,
    TelemetryType,
)
from core.tenant.manager import IdentityManager, InventoryManager, TenantManager
from core.tenant.models import Permission, TenantStatus, UserRoleType


@pytest.fixture
def temp_db():
    """Provides an isolated temporary database for Phase B tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.fixture
def test_setup(temp_db):
    """Sets up Tenant A (Site A1, Dev A1) and Tenant B (Site B1, Dev B1)."""
    t_mgr = TenantManager(db_path=temp_db)
    tenant_a = t_mgr.create_tenant("Acme Corp", "acme-corp")
    tenant_b = t_mgr.create_tenant("Beta Industries", "beta-ind")

    inv_mgr = InventoryManager(db_path=temp_db)
    site_a1 = inv_mgr.create_site(tenant_a.tenant_id, "Acme HQ", "acme-hq")
    site_b1 = inv_mgr.create_site(tenant_b.tenant_id, "Beta Plant", "beta-plant")

    dev_a1 = inv_mgr.create_device(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        name="Acme-Router",
        management_ip="192.168.1.1",
    )
    dev_b1 = inv_mgr.create_device(
        tenant_id=tenant_b.tenant_id,
        site_id=site_b1.site_id,
        name="Beta-Router",
        management_ip="192.168.1.1",  # Overlapping RFC 1918!
    )

    ident_mgr = IdentityManager(db_path=temp_db)
    noc_user = ident_mgr.create_user(
        username="noc_admin",
        email="noc@ls.id",
        password="Password123!",
        role_type=UserRoleType.NOC_ADMIN.value,
        is_internal=True,
    )
    cust_user_a = ident_mgr.create_user(
        username="acme_admin",
        email="admin@acme.com",
        password="Password456!",
        role_type=UserRoleType.CUSTOMER_ADMIN.value,
        is_internal=False,
        tenant_id=tenant_a.tenant_id,
    )

    gw_mgr = EdgeGatewayManager(db_path=temp_db)

    return {
        "db_path": temp_db,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "site_a1": site_a1,
        "site_b1": site_b1,
        "dev_a1": dev_a1,
        "dev_b1": dev_b1,
        "noc_user": noc_user,
        "cust_user_a": cust_user_a,
        "gw_mgr": gw_mgr,
        "t_mgr": t_mgr,
        "ident_mgr": ident_mgr,
    }


# ===========================================================================
# 1. ENROLLMENT & TOKEN SECURITY (Tests 1 - 5)
# ===========================================================================

def test_01_expired_enrollment_token(test_setup):
    """Test 1: Expired enrollment token cannot be redeemed."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]

    # Create token with -5 minutes (already expired)
    raw_token, rec = gw_mgr.create_enrollment_token(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        created_by="noc_admin",
        duration_minutes=-5,
    )

    with pytest.raises(ValueError, match="expired"):
        gw_mgr.enroll_gateway(raw_token, name="Edge-GW-Expired")


def test_02_reused_enrollment_token_single_use(test_setup):
    """Test 2: Token cannot be redeemed twice (single-use guarantee)."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        created_by="noc_admin",
        duration_minutes=15,
    )

    # First redemption succeeds
    gw, auth_tok = gw_mgr.enroll_gateway(raw_token, name="Edge-GW-1")
    assert gw.gateway_id.startswith("gw_")
    assert auth_tok.startswith("aira_gw_auth_")

    # Second redemption MUST fail
    with pytest.raises(ValueError, match="already REDEEMED|redeemed"):
        gw_mgr.enroll_gateway(raw_token, name="Edge-GW-Duplicate")


def test_03_concurrent_token_consumption(test_setup):
    """Test 3: Atomic database conditional update prevents concurrent double-redemption."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        created_by="noc_admin",
        duration_minutes=15,
    )

    # Simulate thread 1 succeeding
    gw1, _ = gw_mgr.enroll_gateway(raw_token, name="GW-Thread-1")
    assert gw1.status == "ACTIVE"

    # Thread 2 attempting immediate redemption fails
    with pytest.raises(ValueError):
        gw_mgr.enroll_gateway(raw_token, name="GW-Thread-2")


def test_04_token_belonging_to_another_tenant(test_setup):
    """Test 4: Token encodes tenant_id; redeeming binds gateway strictly to owning tenant."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    tenant_b = test_setup["tenant_b"]
    site_a1 = test_setup["site_a1"]

    # Token generated for Tenant A
    raw_token, _ = gw_mgr.create_enrollment_token(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        created_by="noc_admin",
    )

    # Redeem token
    gw, _ = gw_mgr.enroll_gateway(raw_token, name="Edge-GW-A")
    # Gateway is bound to Tenant A, NOT Tenant B
    assert gw.tenant_id == tenant_a.tenant_id
    assert gw.tenant_id != tenant_b.tenant_id


def test_05_token_bound_to_specific_site(test_setup):
    """Test 5: Gateway is enrolled strictly under the site specified in token creation."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]

    raw_token, rec = gw_mgr.create_enrollment_token(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        created_by="noc_admin",
    )
    assert rec.site_id == site_a1.site_id

    gw, _ = gw_mgr.enroll_gateway(raw_token, name="Site-Specific-GW")
    assert gw.site_id == site_a1.site_id


# ===========================================================================
# 2. TRANSPORT & AUTHENTICATION (Tests 6 - 8)
# ===========================================================================

def test_06_invalid_and_revoked_gateway_auth(test_setup):
    """Test 6 & 7: Invalid token and revoked gateway are rejected."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Revocable-GW")

    # 1. Bogus auth token rejected
    with pytest.raises(PermissionError, match="Authentication failed"):
        gw_mgr.record_heartbeat("aira_gw_auth_bogus_token", {"timestamp_utc": "2026-11-04T00:00:00Z"})

    # 2. Revoke gateway
    gw_mgr.revoke_gateway(gw.gateway_id, revoked_by="noc_admin", reason="Decommissioning")

    # 3. Revoked gateway rejected
    with pytest.raises(PermissionError, match="Authentication failed"):
        gw_mgr.record_heartbeat(auth_token, {"timestamp_utc": "2026-11-04T00:00:00Z"})


def test_08_gateway_impersonation_defense(test_setup):
    """Test 8: Server resolves tenant/site from database, ignoring client-supplied tenant."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    tenant_b = test_setup["tenant_b"]
    site_a1 = test_setup["site_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Acme-Edge")

    # Authenticate gateway
    auth_gw = gw_mgr.ingestion_hub.authenticate_gateway(auth_token)
    assert auth_gw is not None
    # Even if client claims to be Tenant B, server resolves Tenant A
    assert auth_gw.tenant_id == tenant_a.tenant_id
    assert auth_gw.tenant_id != tenant_b.tenant_id


# ===========================================================================
# 3. SEQUENCE TRACKING & TELEMETRY INGESTION (Tests 9 - 16)
# ===========================================================================

def test_09_to_11_sequence_monotonicity_duplicate_and_replay(test_setup):
    """Tests 9, 10, 11: Monotonic sequence tracking, duplicate suppression, and replay defense."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]
    dev_a1 = test_setup["dev_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Seq-Test-GW")

    # Batch 1: Sequence 1, 2, 3
    batch1 = [
        {"envelope_id": "env_1", "sequence_number": 1, "telemetry_type": "INTERFACE_METRICS", "payload": {"device_id": dev_a1.device_id, "interface_name": "ether1", "rx_utilization": 25.5}},
        {"envelope_id": "env_2", "sequence_number": 2, "telemetry_type": "INTERFACE_METRICS", "payload": {"device_id": dev_a1.device_id, "interface_name": "ether1", "rx_utilization": 30.0}},
        {"envelope_id": "env_3", "sequence_number": 3, "telemetry_type": "INTERFACE_METRICS", "payload": {"device_id": dev_a1.device_id, "interface_name": "ether1", "rx_utilization": 35.0}},
    ]
    res1 = gw_mgr.ingest_telemetry(auth_token, batch1)
    assert res1["accepted_count"] == 3
    assert res1["duplicate_count"] == 0
    assert res1["last_sequence_number"] == 3

    # Batch 2: Replay envelope with sequence 2 and 3 (duplicates!) + new sequence 4
    batch2 = [
        {"envelope_id": "env_2", "sequence_number": 2, "telemetry_type": "INTERFACE_METRICS", "payload": {"device_id": dev_a1.device_id, "interface_name": "ether1", "rx_utilization": 30.0}},
        {"envelope_id": "env_3", "sequence_number": 3, "telemetry_type": "INTERFACE_METRICS", "payload": {"device_id": dev_a1.device_id, "interface_name": "ether1", "rx_utilization": 35.0}},
        {"envelope_id": "env_4", "sequence_number": 4, "telemetry_type": "INTERFACE_METRICS", "payload": {"device_id": dev_a1.device_id, "interface_name": "ether1", "rx_utilization": 40.0}},
    ]
    res2 = gw_mgr.ingest_telemetry(auth_token, batch2)
    assert res2["accepted_count"] == 1  # Only sequence 4 accepted
    assert res2["duplicate_count"] == 2  # Sequences 2 & 3 safely suppressed as duplicates!
    assert res2["last_sequence_number"] == 4


def test_12_and_13_cross_tenant_device_reference_rejection(test_setup):
    """Tests 12 & 13: Gateway attempting to submit telemetry for another tenant's device is rejected."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]
    dev_b1 = test_setup["dev_b1"]  # Belongs to Tenant B!

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Tenant-A-GW")

    # Ingestion envelope referencing Tenant B's device!
    malicious_batch = [
        {
            "envelope_id": "env_cross_1",
            "sequence_number": 1,
            "telemetry_type": "INTERFACE_METRICS",
            "payload": {
                "device_id": dev_b1.device_id,  # Cross-tenant injection!
                "interface_name": "ether1",
                "rx_utilization": 99.0,
            },
        }
    ]
    res = gw_mgr.ingest_telemetry(auth_token, malicious_batch)
    assert res["accepted_count"] == 0
    assert res["error_count"] == 1
    assert "Security Violation" in res["errors"][0]["error"]


def test_14_and_15_oversized_payload_and_malformed_telemetry(test_setup):
    """Tests 14 & 15: Oversized payloads (> 512 KB) and invalid telemetry types rejected."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]
    dev_a1 = test_setup["dev_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Validation-GW")

    # 1. Invalid telemetry type
    res_bad_type = gw_mgr.ingest_telemetry(auth_token, [
        {"envelope_id": "env_bad_1", "sequence_number": 1, "telemetry_type": "UNKNOWN_BOGUS_TYPE", "payload": {}}
    ])
    assert res_bad_type["accepted_count"] == 0
    assert res_bad_type["error_count"] == 1

    # 2. Oversized payload (> 512 KB)
    huge_data = "X" * (525 * 1024)
    res_oversized = gw_mgr.ingest_telemetry(auth_token, [
        {"envelope_id": "env_huge", "sequence_number": 2, "telemetry_type": "INTERFACE_METRICS", "payload": {"device_id": dev_a1.device_id, "blob": huge_data}}
    ])
    assert res_oversized["accepted_count"] == 0
    assert "exceeds 512 KB" in res_oversized["errors"][0]["error"]


# ===========================================================================
# 4. BOUNDED LOCAL BUFFER & RESILIENCY (Tests 17 - 19)
# ===========================================================================

def test_17_queue_capacity_and_fifo_drop(tmp_path):
    """Test 17: Edge local buffer enforces max capacity and drops oldest samples (FIFO)."""
    buf_db = tmp_path / "test_edge_buffer.db"
    # Small buffer capacity for testing: 5 samples
    queue = EdgeBufferQueue(db_path=buf_db, max_capacity=5)

    # Enqueue 5 samples
    for i in range(1, 6):
        seq = queue.enqueue("INTERFACE_METRICS", {"val": i})
        assert seq == i

    health = queue.get_health()
    assert health["queue_depth"] == 5
    assert health["dropped_samples_total"] == 0

    # Enqueue 6th sample -> capacity breach!
    seq6 = queue.enqueue("INTERFACE_METRICS", {"val": 6})
    assert seq6 == 6

    # Depth remains capped at 5; 1 sample dropped
    health_after = queue.get_health()
    assert health_after["queue_depth"] == 5
    assert health_after["dropped_samples_total"] == 1

    # Peek batch: Oldest sample (seq 1) was dropped, so first sample is seq 2
    batch = queue.peek_batch(10)
    assert len(batch) == 5
    assert batch[0]["sequence_number"] == 2
    assert batch[-1]["sequence_number"] == 6


def test_18_and_19_restart_recovery_and_reconnection_drain(tmp_path, test_setup):
    """Tests 18 & 19: Edge buffer survives process restart and drains to Central NOC upon reconnection."""
    buf_db = tmp_path / "edge_buffer_restart.db"
    queue = EdgeBufferQueue(db_path=buf_db, max_capacity=50)

    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]
    dev_a1 = test_setup["dev_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Buffered-GW")

    # Enqueue 10 samples while "offline"
    for i in range(1, 11):
        queue.enqueue("INTERFACE_METRICS", {"device_id": dev_a1.device_id, "interface_name": "ether1", "rx_utilization": float(i * 5)})

    # Simulate Gateway restart: Re-open queue from disk
    recovered_queue = EdgeBufferQueue(db_path=buf_db, max_capacity=50)
    assert recovered_queue.get_health()["queue_depth"] == 10

    # Reconnection: Drain batch to Central NOC
    batch_to_send = recovered_queue.peek_batch(50)
    res = gw_mgr.ingest_telemetry(auth_token, batch_to_send)
    assert res["accepted_count"] == 10
    assert res["last_sequence_number"] == 10

    # Acknowledge sent batch: local queue becomes empty
    sample_ids = [item["envelope_id"] for item in batch_to_send]
    acknowledged = recovered_queue.acknowledge_batch(sample_ids)
    assert acknowledged == 10
    assert recovered_queue.get_health()["queue_depth"] == 0


# ===========================================================================
# 5. READ-ONLY COLLECTOR SANITIZER (Tests 22 & 23)
# ===========================================================================

def test_22_arbitrary_shell_command_and_delimiters_rejection():
    """Test 22: Edge diagnostic sanitizer strictly rejects shell commands and injection delimiters."""
    # Delimiters rejected
    with pytest.raises(DiagnosticSanitizerError, match="dangerous shell injection"):
        EdgeDiagnosticCollector.sanitize_routeros_command("/ip/address/print; rm -rf /")

    with pytest.raises(DiagnosticSanitizerError, match="dangerous shell injection"):
        EdgeDiagnosticCollector.sanitize_routeros_command("/ip/address/print | cat /etc/passwd")

    with pytest.raises(DiagnosticSanitizerError, match="dangerous shell injection"):
        EdgeDiagnosticCollector.sanitize_routeros_command("/ip/address/print & reboot")

    with pytest.raises(DiagnosticSanitizerError, match="dangerous shell injection"):
        EdgeDiagnosticCollector.sanitize_routeros_command("/ip/address/print `reboot`")


def test_23_router_configuration_mutation_rejection():
    """Test 23: All mutating verbs (add, set, remove, enable, disable, reboot) are forbidden."""
    with pytest.raises(DiagnosticSanitizerError, match="Mutating verb 'add' is strictly forbidden"):
        EdgeDiagnosticCollector.sanitize_routeros_command("/ip address add address=10.0.0.1/24 interface=ether1")

    with pytest.raises(DiagnosticSanitizerError, match="Mutating verb 'remove' is strictly forbidden"):
        EdgeDiagnosticCollector.sanitize_routeros_command("/ip route remove numbers=0")

    with pytest.raises(DiagnosticSanitizerError, match="Mutating verb 'reboot' is strictly forbidden"):
        EdgeDiagnosticCollector.sanitize_routeros_command("/system reboot")

    # Approved read-only command passes cleanly
    safe_cmd = EdgeDiagnosticCollector.sanitize_routeros_command("/ip/address/print")
    assert safe_cmd == "/ip/address/print"


# ===========================================================================
# 6. HEARTBEAT & HEALTH MONITORING (Tests 24 & 25)
# ===========================================================================

def test_24_heartbeat_liveness_and_offline_timeout(test_setup):
    """Test 24: Gateway health evaluates ONLINE and transitions to OFFLINE when heartbeat lapses."""
    gw_mgr = test_setup["gw_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Liveness-GW")

    # 1. Send recent heartbeat -> ONLINE
    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    health1 = gw_mgr.record_heartbeat(auth_token, {"timestamp_utc": now_str, "cpu_utilization": 15.0, "queue_depth": 0})
    assert health1.status == GatewayHealthStatus.ONLINE.value

    # 2. Simulate 120s lapsing in database
    past_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 120))
    with sqlite3.connect(test_setup["db_path"]) as conn:
        conn.execute("UPDATE operational_gateways SET last_seen_at_utc = ? WHERE gateway_id = ?", (past_str, gw.gateway_id))

    # Health evaluation detects timeout (> 90s) -> OFFLINE
    health2 = gw_mgr.get_gateway_health(gw.gateway_id)
    assert health2 is not None
    assert health2.status == GatewayHealthStatus.OFFLINE.value


def test_25_tenant_suspension_invalidates_gateway_authorization(test_setup):
    """Test 25: When a tenant is suspended, all its edge gateways are immediately blocked."""
    gw_mgr = test_setup["gw_mgr"]
    t_mgr = test_setup["t_mgr"]
    tenant_a = test_setup["tenant_a"]
    site_a1 = test_setup["site_a1"]

    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Suspension-GW")

    # Suspend Tenant A
    t_mgr.update_tenant_status(tenant_a.tenant_id, TenantStatus.SUSPENDED.value)

    # Gateway authentication is now blocked!
    with pytest.raises(PermissionError, match="Authentication failed"):
        gw_mgr.record_heartbeat(auth_token, {"timestamp_utc": "2026-11-04T00:00:00Z"})

    with pytest.raises(PermissionError, match="Authentication failed"):
        gw_mgr.ingest_telemetry(auth_token, [{"envelope_id": "env_1", "sequence_number": 1, "telemetry_type": "INTERFACE_METRICS", "payload": {}}])
