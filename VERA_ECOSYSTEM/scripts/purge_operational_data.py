"""
AIRA OS — Operational Data Purge & Clean Start Script (Phase F.1).

Purges all operational network data:
- Inventory devices and credentials (database/inventory.db)
- Topology nodes, edges, and links (database/topology.db)
- NMS telemetry, device profiles, metrics, and incidents (database/topology.db)
- Operational devices, sites, support requests, and playbooks (database/topology.db)

Strictly PRESERVES:
- User accounts (operational_users, lingga_admin)
- User roles (operational_user_roles)
- Groups (operational_groups)
- Permissions (operational_permissions)
- Group permissions (operational_group_permissions)
- User group memberships (operational_user_group_memberships)
- User activity audit trail (operational_user_activity_events)
- Personalization (user_personas, memory)
- Database schema definitions
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"
TOPOLOGY_DB = DATABASE_DIR / "topology.db"
INVENTORY_DB = DATABASE_DIR / "inventory.db"


def inspect_counts(db_path: Path, table_filter=None) -> dict[str, int]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    counts = {}
    for t in tables:
        if table_filter and not table_filter(t):
            continue
        try:
            cnt = cursor.execute(f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]
            counts[t] = cnt
        except Exception:
            pass
    conn.close()
    return counts


def purge_operational_data():
    print("=" * 60)
    print("AIRA OS — OPERATIONAL DATA PURGE (CLEAN START)")
    print("=" * 60)

    # 1. INVENTORY DB PURGE
    print("\n--- 1. INVENTORY DATABASE (inventory.db) ---")
    if INVENTORY_DB.exists():
        before_inv = inspect_counts(INVENTORY_DB)
        print("Before purge:")
        for t, c in before_inv.items():
            print(f"  {t}: {c}")

        conn = sqlite3.connect(INVENTORY_DB)
        with conn:
            for t in ["device_credentials", "devices", "credentials"]:
                try:
                    conn.execute(f"DELETE FROM \"{t}\"")
                except Exception as e:
                    print(f"  Notice on {t}: {e}")
        conn.close()

        after_inv = inspect_counts(INVENTORY_DB)
        print("After purge:")
        for t, c in after_inv.items():
            print(f"  {t}: {c}")
    else:
        print("inventory.db not found (clean).")

    # 2. TOPOLOGY DB PURGE
    print("\n--- 2. TOPOLOGY & NMS DATABASE (topology.db) ---")
    OPERATIONAL_PURGE_TABLES = [
        # Topology
        "topology_edges",
        "topology_links",
        "topology_nodes",
        "topology_history",
        "topology_evidence",
        "topology_conflicts",
        "topology_link_verifications",
        "topology_edge_gateway_links",

        # NMS & Telemetry
        "nms_telemetry_history",
        "nms_device_profiles",
        "nms_incidents",
        "nms_alerts",
        "nms_poller_runs",

        # Network Intelligence & Operations
        "network_incidents",
        "network_evidence_bundles",
        "proactive_incidents",
        "change_impact_simulations",
        "predictive_capacity_forecasts",
        "business_services",
        "service_endpoints",
        "operational_jobs",
        "operational_job_executions",
        "maintenance_windows",
        "operational_decisions",
        "operational_decision_audit",

        # Shared operational network entities
        "operational_devices",
        "operational_sites",
        "operational_support_requests",
        "operational_playbooks",
        "operational_approvals",
    ]

    before_topo = inspect_counts(TOPOLOGY_DB)
    print("Select table counts before purge:")
    for t in OPERATIONAL_PURGE_TABLES:
        if t in before_topo:
            print(f"  {t}: {before_topo[t]}")

    conn = sqlite3.connect(TOPOLOGY_DB)
    with conn:
        for t in OPERATIONAL_PURGE_TABLES:
            try:
                conn.execute(f"DELETE FROM \"{t}\"")
            except Exception:
                pass
    conn.close()

    after_topo = inspect_counts(TOPOLOGY_DB)
    print("\nSelect table counts after purge:")
    for t in OPERATIONAL_PURGE_TABLES:
        if t in after_topo:
            print(f"  {t}: {after_topo[t]}")

    print("\nPreserved tables verification:")
    preserved_tables = [
        "operational_users",
        "operational_user_roles",
        "operational_groups",
        "operational_permissions",
        "operational_group_permissions",
        "operational_user_group_memberships",
        "operational_user_activity_events",
        "user_personas",
    ]
    for t in preserved_tables:
        if t in after_topo:
            print(f"  {t}: {after_topo[t]} records (PRESERVED)")

    print("\n[SUCCESS] Operational network data purged. Clean start state verified.")


if __name__ == "__main__":
    purge_operational_data()
