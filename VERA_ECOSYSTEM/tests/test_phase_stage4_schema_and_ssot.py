"""
AIRA OS — Stage 4 Verification Test Suite: Database Schema Reconciliation & SSOT.

Validates:
1. Reconciled NMS metrics store & edge gateway rollups (BUG-06).
2. NMS incidents schema consistency (started_at & forensic columns) (BUG-20).
3. Single Source of Truth (SSOT) device inventory synchronization between
   InventoryStore and operational_devices in topology.db (REC-11).
4. Bidirectional mirroring from InventoryManager to InventoryStore.
5. Removal of tenant_guest from operational_tenants (Decision 2).
6. SQLite PRAGMA integrity_check and foreign_key_check.
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.database.backup_service import check_database_integrity
from core.edge_gateway.db import ensure_gateway_schema
from core.inventory_store import InventoryStore
from core.nms.metrics_store import init_metrics_tables, query_metrics
from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import InventoryManager
from core.topology_db import get_topology_connection, init_topology_database


def test_nms_metrics_store_and_gateway_schema_reconciliation():
    """BUG-06: Booting edge gateway schema and querying across raw, 5m, and 1h tiers succeeds."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "topology_metrics_test.db"

        # 1. Boot Edge Gateway schema first
        ensure_gateway_schema(db_path)

        # 2. Ingest a raw sample
        t_now = time.time()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO nms_raw_metrics (
                    device_id, metric_name, metric_value, unit, semantic_type, source_protocol, quality, measured_at, collected_at
                ) VALUES (?, ?, ?, '%', 'GAUGE', 'SNMP', 'RELIABLE', ?, ?)
                """,
                ("dev_test_gw", "cpu_utilization", 42.5, t_now - 60.0, t_now),
            )
            conn.commit()

        # 3. Query Tier 1: raw
        res_raw = query_metrics(
            device_id="dev_test_gw",
            metric_name="cpu_utilization",
            start_time=t_now - 300.0,
            end_time=t_now,
            step="raw",
            db_path=db_path,
        )
        assert res_raw["count"] == 1
        assert res_raw["points"][0]["value"] == 42.5

        # 4. Query Tier 2: 5m (Must NOT crash with 'no such table: nms_5m_rollups')
        res_5m = query_metrics(
            device_id="dev_test_gw",
            metric_name="cpu_utilization",
            start_time=t_now - 3600.0,
            end_time=t_now,
            step="5m",
            db_path=db_path,
        )
        assert isinstance(res_5m["points"], list)

        # 5. Query Tier 3: 1h (Must NOT crash with 'no such table: nms_1h_rollups')
        res_1h = query_metrics(
            device_id="dev_test_gw",
            metric_name="cpu_utilization",
            start_time=t_now - 86400.0,
            end_time=t_now,
            step="1h",
            db_path=db_path,
        )
        assert isinstance(res_1h["points"], list)


def test_nms_incidents_schema_consistency():
    """BUG-20: nms_incidents uses started_at and has extended forensic columns."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "topology_incidents_test.db"
        init_topology_database(db_path)

        from core.nms.alerts import AlertEngine

        alert_engine = AlertEngine(db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(nms_incidents)").fetchall()}

            # Verify canonical started_at and WP 5.5 columns
            assert "started_at" in cols
            assert "parent_incident_id" in cols
            assert "suppression_reason" in cols
            assert "route_snapshot_id" in cols
            assert "affected_downstream_count" in cols

            # Insert incident using canonical columns
            now_ts = time.time()
            conn.execute(
                """
                INSERT INTO nms_incidents (
                    device_id, incident_type, severity, title, details, status, started_at,
                    parent_incident_id, suppression_reason, route_snapshot_id, affected_downstream_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "dev_core_r1", "high_cpu", "critical", "High CPU Load",
                    "CPU exceeded 95%", "open", now_ts, None, None, "snap_001", 3,
                ),
            )
            conn.commit()

            # Query by started_at works cleanly without OperationalError
            rows = conn.execute("SELECT * FROM nms_incidents WHERE started_at >= ?", (now_ts - 10,)).fetchall()
            assert len(rows) == 1
            assert rows[0]["device_id"] == "dev_core_r1"


def test_device_inventory_ssot_sync():
    """REC-11: Changes in InventoryStore automatically propagate to operational_devices in topology.db."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        inv_db = Path(tmp_dir) / "inv_ssot.db"
        topo_db = Path(tmp_dir) / "topo_ssot.db"

        # Initialize tenant schema on topo_db
        ensure_tenant_schema(topo_db)

        with patch("core.inventory_store.DEFAULT_DB_FILE", inv_db), \
             patch("core.topology_db.DEFAULT_TOPOLOGY_DB_PATH", topo_db):

            inv = InventoryStore(db_path=inv_db, seed=False)

            # 1. Create Device in InventoryStore
            res = inv.create_device(
                name="SSOT-Router-1",
                host="10.20.30.1",
                port=2222,
                device_type="mikrotik",
                note="Core SSOT Device",
                enabled=True,
            )
            assert res["success"] is True

            # Verify it exists in topology.db:operational_devices
            with sqlite3.connect(topo_db) as conn:
                conn.row_factory = sqlite3.Row
                dev_row = conn.execute(
                    "SELECT * FROM operational_devices WHERE name = 'SSOT-Router-1'"
                ).fetchone()
                assert dev_row is not None
                assert dev_row["management_ip"] == "10.20.30.1"
                assert dev_row["management_port"] == 2222
                assert dev_row["device_type"] == "ROUTER"
                assert dev_row["status"] == "ACTIVE"

            # 2. Update Device in InventoryStore
            res_upd = inv.update_device("SSOT-Router-1", host="10.20.30.2", port=22, note="Updated note")
            assert res_upd["success"] is True

            with sqlite3.connect(topo_db) as conn:
                conn.row_factory = sqlite3.Row
                dev_row = conn.execute(
                    "SELECT * FROM operational_devices WHERE name = 'SSOT-Router-1'"
                ).fetchone()
                assert dev_row["management_ip"] == "10.20.30.2"
                assert dev_row["management_port"] == 22
                assert dev_row["notes"] == "Updated note"

            # 3. Delete Device in InventoryStore
            res_del = inv.delete_device("SSOT-Router-1")
            assert res_del["success"] is True

            with sqlite3.connect(topo_db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM operational_devices WHERE name = 'SSOT-Router-1'"
                ).fetchone()[0]
                assert count == 0


def test_bidirectional_mirror_from_inventory_manager():
    """REC-11: Device created in InventoryManager is mirrored to InventoryStore."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        inv_db = Path(tmp_dir) / "inv_mirror.db"
        topo_db = Path(tmp_dir) / "topo_mirror.db"

        ensure_tenant_schema(topo_db)

        with patch("core.inventory_store.DEFAULT_DB_FILE", inv_db), \
             patch("core.topology_db.DEFAULT_TOPOLOGY_DB_PATH", topo_db):

            inv = InventoryStore(db_path=inv_db, seed=False)
            with patch("core.inventory_store._store_singleton", inv):
                mgr = InventoryManager(topo_db)
                # Create a site first
                site = mgr.create_site(tenant_id="tenant_default", name="Branch Site 1", slug="branch-site-1")

                # Create device via InventoryManager
                device = mgr.create_device(
                    tenant_id="tenant_default",
                    site_id=site.site_id,
                    name="Portal-Edge-1",
                    management_ip="172.16.0.1",
                    management_port=22,
                    device_type="ROUTER",
                    notes="Created via Portal Manager",
                )
                assert device.device_id.startswith("dev_")

                # Verify it is mirrored into InventoryStore
                inv_dev = inv.get_device("Portal-Edge-1")
                assert inv_dev["success"] is True
                assert inv_dev["device"]["host"] == "172.16.0.1"


def test_guest_tenant_elimination():
    """Decision 2: tenant_guest is completely absent from operational_tenants."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_tenant.db"
        ensure_tenant_schema(db_path)

        with sqlite3.connect(db_path) as conn:
            tenants = [r[0] for r in conn.execute("SELECT tenant_id FROM operational_tenants").fetchall()]
            assert "tenant_guest" not in tenants
            assert "tenant_default" in tenants


def test_database_integrity_and_foreign_keys():
    """Database integrity and FK constraint checks on live topology.db."""
    from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH

    integrity_ok, fk_ok, msg = check_database_integrity(DEFAULT_TOPOLOGY_DB_PATH)
    assert integrity_ok is True, f"Integrity check failed: {msg}"
    assert fk_ok is True, f"Foreign key check failed: {msg}"
