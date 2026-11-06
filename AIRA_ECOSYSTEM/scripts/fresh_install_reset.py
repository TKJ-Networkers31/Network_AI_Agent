"""
AIRA OS — Comprehensive Fresh Install Data Reset Script.
Safely resets all dynamic operational data (memory, devices, topology, NMS metrics,
chat sessions, security findings, actions, incidents, logs, artifacts) back to a pristine
fresh-install state while preserving core schemas, system configurations, and the
platform superadmin account (lingga_admin).

Guarantees:
- Creates an immutable full snapshot backup before making any changes.
- Preserves database schemas, triggers, indexes, and system defaults.
- Reclaims disk space across all SQLite databases via VACUUM.
- Re-bootstraps lingga_admin as Platform Owner.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"
BACKUPS_DIR = DATABASE_DIR / "backups"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("aira.fresh_install")


def create_pre_reset_backup() -> Path:
    """Creates a full timestamped backup of all .db files in database/."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_target = BACKUPS_DIR / f"fresh_install_backup_{timestamp}"
    backup_target.mkdir(parents=True, exist_ok=True)

    for db_path in DATABASE_DIR.glob("*.db"):
        dest = backup_target / db_path.name
        shutil.copy2(db_path, dest)
        logger.info("Backed up %s -> %s", db_path.name, dest.name)

    logger.info("Backup successfully completed at: %s", backup_target)
    return backup_target


def execute_fresh_install_reset() -> dict:
    backup_path = create_pre_reset_backup()

    report = {
        "status": "SUCCESS",
        "backup_path": str(backup_path),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cleared_databases": {},
        "preserved_system_records": {},
    }

    # 1. artifacts.db
    art_db = DATABASE_DIR / "artifacts.db"
    if art_db.exists():
        with sqlite3.connect(art_db) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
            conn.execute("DELETE FROM artifacts")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["artifacts.db"] = {"artifacts": cnt}

    # 2. attachments.db
    att_db = DATABASE_DIR / "attachments.db"
    if att_db.exists():
        with sqlite3.connect(att_db) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
            conn.execute("DELETE FROM attachments")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["attachments.db"] = {"attachments": cnt}

    # 3. chat_sessions.db
    chat_db = DATABASE_DIR / "chat_sessions.db"
    if chat_db.exists():
        with sqlite3.connect(chat_db) as conn:
            s_cnt = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
            t_cnt = conn.execute("SELECT COUNT(*) FROM chat_turns").fetchone()[0]
            conn.execute("DELETE FROM chat_turns")
            conn.execute("DELETE FROM chat_sessions")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["chat_sessions.db"] = {"chat_sessions": s_cnt, "chat_turns": t_cnt}

    # 4. interaction_memory.db
    im_db = DATABASE_DIR / "interaction_memory.db"
    if im_db.exists():
        with sqlite3.connect(im_db) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM interaction_context").fetchone()[0]
            conn.execute("DELETE FROM interaction_context")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["interaction_memory.db"] = {"interaction_context": cnt}

    # 5. inventory.db
    inv_db = DATABASE_DIR / "inventory.db"
    if inv_db.exists():
        with sqlite3.connect(inv_db) as conn:
            d_cnt = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
            c_cnt = conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0]
            dc_cnt = conn.execute("SELECT COUNT(*) FROM device_credentials").fetchone()[0]
            conn.execute("DELETE FROM device_credentials")
            conn.execute("DELETE FROM credentials")
            conn.execute("DELETE FROM devices")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["inventory.db"] = {
                "devices": d_cnt,
                "credentials": c_cnt,
                "device_credentials": dc_cnt,
            }

    # 6. logs.db
    logs_db = DATABASE_DIR / "logs.db"
    if logs_db.exists():
        with sqlite3.connect(logs_db) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
            conn.execute("DELETE FROM logs")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["logs.db"] = {"logs": cnt}

    # 7. long_term_memory.db & semantic_memory.db
    lt_db = DATABASE_DIR / "long_term_memory.db"
    if lt_db.exists():
        with sqlite3.connect(lt_db) as conn:
            f_cnt = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            e_cnt = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            conn.execute("DELETE FROM facts")
            conn.execute("DELETE FROM events")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["long_term_memory.db"] = {"facts": f_cnt, "events": e_cnt}

    sm_db = DATABASE_DIR / "semantic_memory.db"
    if sm_db.exists():
        with sqlite3.connect(sm_db) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0]
            conn.execute("DELETE FROM semantic_memory")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["semantic_memory.db"] = {"semantic_memory": cnt}

    # 8. network_intelligence.db
    ni_db = DATABASE_DIR / "network_intelligence.db"
    if ni_db.exists():
        with sqlite3.connect(ni_db) as conn:
            ni_counts = {}
            for t in ["incidents", "evidence_items", "playbook_runs", "configuration_plans", "intelligence_investigations"]:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                conn.execute(f"DELETE FROM {t}")
                ni_counts[t] = cnt
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["network_intelligence.db"] = ni_counts

    # 9. selection_context.db
    sel_db = DATABASE_DIR / "selection_context.db"
    if sel_db.exists():
        with sqlite3.connect(sel_db) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM selection_context").fetchone()[0]
            conn.execute("DELETE FROM selection_context")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["selection_context.db"] = {"selection_context": cnt}

    # 10. vision_snapshots/
    vis_dir = DATABASE_DIR / "vision_snapshots"
    if vis_dir.exists():
        del_img_cnt = 0
        for f in vis_dir.glob("*.jpg"):
            f.unlink()
            del_img_cnt += 1
        report["cleared_databases"]["vision_snapshots"] = {"deleted_images": del_img_cnt}

    # 11. persona.db
    p_db = DATABASE_DIR / "persona.db"
    if p_db.exists():
        with sqlite3.connect(p_db) as conn:
            conn.execute("UPDATE persona_profile SET user_name = NULL, active_preset = 'akane'")
            conn.execute("DELETE FROM persona_presets WHERE is_builtin = 0")
            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["persona.db"] = {"user_name_reset": True, "custom_presets_cleared": True}

    # 12. topology.db (Central Engine Database)
    top_db = DATABASE_DIR / "topology.db"
    if top_db.exists():
        with sqlite3.connect(top_db) as conn:
            top_cleared = {}

            tables_to_clear = [
                # Topology & Devices
                "topology_nodes",
                "topology_links",
                "topology_evidence",
                "topology_discovery_jobs",
                "topology_conflicts",
                "topology_audit_log",
                "topology_edges",
                "topology_edge_evidence",
                "topology_snapshots",
                "topology_changes",
                "route_snapshots",
                "route_changes",
                "operational_devices",
                "operational_sites",
                "operational_site_groups",
                "operational_gateways",
                "operational_gateway_tokens",
                "operational_gateway_sequences",
                "operational_gateway_heartbeats",
                "network_workspaces",

                # NMS Metrics & Monitoring
                "nms_device_profiles",
                "nms_device_metrics",
                "nms_interface_metrics",
                "nms_incidents",
                "nms_raw_metrics",
                "nms_5m_rollups",
                "nms_1h_rollups",
                "operational_health_scores",
                "operational_sla_reports",

                # Operations & Intelligence
                "operational_services",
                "operational_service_endpoints",
                "operational_jobs",
                "operational_job_runs",
                "operational_maintenance_windows",
                "operational_incidents",
                "operational_notifications",
                "operational_decisions",
                "operational_decision_history",
                "operational_support_requests",
                "operational_support_request_comments",
                "operational_approval_preferences",
                "operational_pending_approvals",
                "operational_action_records",
                "operational_security_findings",
                "operational_security_posture",
                "operational_automations",
                "operational_automation_executions",

                # Sessions & Audits & Memory
                "user_memories",
                "user_preferences",
                "operational_user_sessions",
                "operational_user_activity_events",
                "operational_audit_log",
                "operational_token_usage_ledger",
                "operational_token_quota_adjustments",
                "operational_billing_invoices",
                "operational_billing_transactions",
                "operational_billing_webhook_events",
                "operational_customer_profiles",
                "operational_customer_notification_preferences",
            ]

            # Handle immutable triggers for topology_snapshots and route_snapshots
            conn.execute("DROP TRIGGER IF EXISTS trg_snapshot_no_delete")
            conn.execute("DROP TRIGGER IF EXISTS trg_route_snapshots_no_delete")

            for tbl in tables_to_clear:
                try:
                    cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    conn.execute(f"DELETE FROM {tbl}")
                    top_cleared[tbl] = cnt
                except Exception as e:
                    top_cleared[tbl] = f"SKIPPED ({e})"

            # Re-create immutable triggers
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_snapshot_no_delete
                BEFORE DELETE ON topology_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'Topology snapshots are mathematically immutable and cannot be deleted.');
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_route_snapshots_no_delete
                BEFORE DELETE ON route_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'route_snapshots records are immutable');
                END;
            """)

            # Personas: Delete custom personas, retain default builtin presets
            custom_personas_cnt = conn.execute("SELECT COUNT(*) FROM user_personas WHERE user_id IS NOT NULL").fetchone()[0]
            conn.execute("DELETE FROM user_personas WHERE user_id IS NOT NULL")
            top_cleared["user_personas_custom"] = custom_personas_cnt

            # Users: Delete ephemeral test users, retain superadmin 'lingga_admin'
            test_users = conn.execute("SELECT user_id FROM operational_users WHERE username != 'lingga_admin'").fetchall()
            test_user_ids = [u[0] for u in test_users]
            if test_user_ids:
                placeholders = ",".join(["?"] * len(test_user_ids))
                conn.execute(f"DELETE FROM operational_user_roles WHERE user_id IN ({placeholders})", test_user_ids)
                conn.execute(f"DELETE FROM operational_user_group_memberships WHERE user_id IN ({placeholders})", test_user_ids)
                conn.execute(f"DELETE FROM operational_token_balances WHERE user_id IN ({placeholders})", test_user_ids)
                conn.execute(f"DELETE FROM operational_user_subscriptions WHERE user_id IN ({placeholders})", test_user_ids)
                conn.execute(f"DELETE FROM operational_users WHERE user_id IN ({placeholders})", test_user_ids)
            top_cleared["operational_users_test_removed"] = len(test_user_ids)

            # Record preserved system state from topology.db
            report["preserved_system_records"]["operational_users"] = [r[0] for r in conn.execute("SELECT username FROM operational_users").fetchall()]
            report["preserved_system_records"]["operational_tenants"] = [r[0] for r in conn.execute("SELECT slug FROM operational_tenants").fetchall()]
            report["preserved_system_records"]["operational_groups"] = conn.execute("SELECT COUNT(*) FROM operational_groups").fetchone()[0]
            report["preserved_system_records"]["operational_permissions"] = conn.execute("SELECT COUNT(*) FROM operational_permissions").fetchone()[0]
            report["preserved_system_records"]["operational_playbooks"] = conn.execute("SELECT COUNT(*) FROM operational_playbooks").fetchone()[0]
            report["preserved_system_records"]["user_personas_builtin"] = conn.execute("SELECT COUNT(*) FROM user_personas").fetchone()[0]

            conn.commit()
            conn.execute("VACUUM")
            report["cleared_databases"]["topology.db"] = top_cleared

    # Re-bootstrap superadmin to verify lingga_admin account is pristine & fully privileged
    sys.path.insert(0, str(BASE_DIR))
    from core.bootstrap_superadmin import bootstrap_superadmin
    superadmin_res = bootstrap_superadmin(db_path=top_db, force_reset=False)
    report["superadmin_verification"] = superadmin_res

    return report


if __name__ == "__main__":
    result = execute_fresh_install_reset()
    print(json.dumps(result, indent=2))
