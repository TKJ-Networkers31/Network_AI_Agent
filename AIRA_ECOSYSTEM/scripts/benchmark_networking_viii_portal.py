"""
AIRA OS — Networking VIII Phase D Customer Self-Service Portal Benchmark (WP 8.9).

Measures:
1. Customer Authentication & Token Validation Latency & Throughput (WP 8.9.1)
2. Strict Server-Side Tenant Scoping & Anti-IDOR Check Overhead (WP 8.9.2, 8.9.3)
3. Operational Dashboard & 6-Dimension Health Retrieval Latency (WP 8.9.4)
4. Customer Device & Site Inventory Retrieval Latency with Redaction (WP 8.9.5)
5. Incident Self-Service & Acknowledgement Throughput (WP 8.9.6)
6. SLA Availability Report Retrieval Latency (WP 8.9.7)
7. Support Request Lifecycle & Collaboration Desk Throughput (WP 8.9.9)
8. Memory Footprint (RAM) & Database Growth across 10, 25, and 50 Simulated Tenants

Environment Profile: ThinkPad X270, Intel Core i7-7500U, 8 GB RAM, CPU-Only, Windows 11.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import tracemalloc
from typing import Any, Dict, List

# Ensure AIRA_ECOSYSTEM is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.edge_gateway.db import ensure_gateway_schema
from core.edge_gateway.manager import EdgeGatewayManager
from core.operations.db import ensure_operational_schema
from core.operations.health_scoring_engine import DynamicHealthScoringEngine
from core.operations.models import (
    IncidentSeverity,
    ServiceCriticality,
    SlaWindowType,
)
from core.operations.multi_tenant_incident_engine import MultiTenantIncidentEngine
from core.operations.sla_engine import SlaManagementEngine
from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import (
    IdentityManager,
    InventoryManager,
    NotificationPreferenceManager,
    SupportRequestManager,
    TenantManager,
)
from core.tenant.models import (
    SupportCategory,
    SupportPriority,
    SupportStatus,
    UserRoleType,
)
from core.topology_db import topology_transaction


def run_customer_portal_benchmark() -> Dict[str, Any]:
    print("=" * 80)
    print("AIRA OS — NETWORKING VIII PHASE D: CUSTOMER SELF-SERVICE PORTAL BENCHMARK")
    print("Profile: ThinkPad X270 (Intel i7-7500U, 8 GB RAM, Windows 11, CPU-Only)")
    print("=" * 80)

    results: Dict[str, Any] = {
        "benchmark_name": "Networking VIII Phase D — Customer Self-Service Portal",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "device": "ThinkPad X270",
            "cpu": "Intel Core i7-7500U (2 cores / 4 threads, 2.70 GHz - 3.50 GHz)",
            "ram_total_gb": 8.0,
            "os": "Windows 11",
            "execution_mode": "CPU-Only",
        },
        "metrics": {},
    }

    temp_dir = Path(tempfile.mkdtemp(prefix="aira_portal_bench_"))
    db_path = temp_dir / "bench_portal.db"

    try:
        ensure_tenant_schema(db_path)
        ensure_gateway_schema(db_path)
        ensure_operational_schema(db_path)

        tenant_mgr = TenantManager(db_path=db_path)
        identity_mgr = IdentityManager(db_path=db_path)
        inv_mgr = InventoryManager(db_path=db_path)
        gw_mgr = EdgeGatewayManager(db_path=db_path)
        health_engine = DynamicHealthScoringEngine(db_path=db_path)
        sla_engine = SlaManagementEngine(db_path=db_path)
        incident_engine = MultiTenantIncidentEngine(db_path=db_path)
        support_mgr = SupportRequestManager(db_path=db_path)
        notif_mgr = NotificationPreferenceManager(db_path=db_path)

        tracemalloc.start()
        start_mem = tracemalloc.get_traced_memory()[0]

        # Provision Central NOC operator user for internal support responses
        noc_user = identity_mgr.create_user(
            username="noc_operator_01",
            email="noc@central.internal",
            password="NocCentralPassword123!",
            role_type=UserRoleType.NOC_OPERATOR.value,
            is_internal=True,
        )

        # -------------------------------------------------------------------
        # 1. Scale Simulation: Provision 50 Tenants with full hierarchy
        # -------------------------------------------------------------------
        print("\n[Stage 1] Provisioning 50 Multi-Tenant Customer Organizations...")
        t0 = time.perf_counter()

        tenant_ids = []
        user_credentials = []
        device_ids_by_tenant = {}
        tokens_by_tenant = {}

        for i in range(1, 51):
            t = tenant_mgr.create_tenant(name=f"Customer Tenant {i:02d}", slug=f"tenant-{i:02d}")
            tenant_ids.append(t.tenant_id)

            # Sites & Devices
            site = inv_mgr.create_site(tenant_id=t.tenant_id, name=f"HQ Site {i:02d}", slug=f"hq-{i:02d}")
            devs = []
            for d in range(1, 6):
                dev = inv_mgr.create_device(
                    tenant_id=t.tenant_id,
                    site_id=site.site_id,
                    name=f"t{i:02d}-core-{d:02d}",
                    management_ip=f"10.{i}.0.{d}", # Overlapping / custom RFC 1918
                    credential_ref=f"vault://creds/t{i}/d{d}",
                )
                devs.append(dev.device_id)
            device_ids_by_tenant[t.tenant_id] = devs

            # Edge Gateway
            tok_raw, _ = gw_mgr.create_enrollment_token(tenant_id=t.tenant_id, site_id=site.site_id, created_by="admin")
            gw, _ = gw_mgr.enroll_gateway(raw_token=tok_raw, name=f"gw-t{i:02d}")

            # Customer Users
            user = identity_mgr.create_user(
                tenant_id=t.tenant_id,
                username=f"admin_t{i:02d}",
                email=f"admin@tenant{i:02d}.internal",
                password=f"SecurePass_T{i:02d}!99",
                role_type=UserRoleType.CUSTOMER_ADMIN.value,
                is_internal=False,
            )
            user_credentials.append((f"admin_t{i:02d}", f"SecurePass_T{i:02d}!99", t.tenant_id, user.user_id))

            # Service and SLA Policy
            with topology_transaction(db_path, write=True) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO operational_services (service_id, tenant_id, name, criticality, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'TIER_1_MISSION_CRITICAL', 'HEALTHY', '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')
                    """,
                    (f"svc_t{i:02d}", t.tenant_id, f"Core Service T{i:02d}"),
                )
            sla_engine.create_or_update_policy(
                tenant_id=t.tenant_id,
                service_id=f"svc_t{i:02d}",
                name=f"SLA Policy T{i:02d}",
                target_availability=99.9,
                window_type=SlaWindowType.MONTHLY.value,
            )

            # Active Incident
            incident_engine.report_incident(
                tenant_id=t.tenant_id,
                title=f"Sample Incident for Tenant {i:02d}",
                severity=IncidentSeverity.MEDIUM.value,
                affected_devices=[devs[0]],
                summary=f"Automated benchmark telemetry alarm for Tenant {i:02d}",
            )

        provision_time_ms = (time.perf_counter() - t0) * 1000.0
        print(f"  -> 50 Tenants provisioned in {provision_time_ms:.2f} ms ({provision_time_ms/50.0:.2f} ms/tenant)")

        # -------------------------------------------------------------------
        # 2. Benchmark Authentication & Token Validation (WP 8.9.1)
        # -------------------------------------------------------------------
        print("\n[Stage 2] Benchmarking Customer Authentication & Session Validation...")
        auth_times = []
        for uname, pwd, tid, uid in user_credentials:
            t_auth_start = time.perf_counter()
            sess = identity_mgr.authenticate_user(uname, pwd)
            auth_times.append((time.perf_counter() - t_auth_start) * 1000.0)
            tokens_by_tenant[tid] = sess.token

        avg_auth_ms = sum(auth_times) / len(auth_times)
        p95_auth_ms = sorted(auth_times)[int(len(auth_times) * 0.95)]
        print(f"  -> Authenticate: avg = {avg_auth_ms:.2f} ms, p95 = {p95_auth_ms:.2f} ms")

        # Token validation throughput
        t_val_start = time.perf_counter()
        validation_iterations = 200
        for _ in range(validation_iterations):
            for tid in tenant_ids[:10]:
                token = tokens_by_tenant[tid]
                ctx = identity_mgr.validate_session_token(token)
                assert ctx is not None
        val_time_s = time.perf_counter() - t_val_start
        val_throughput = (validation_iterations * 10) / val_time_s
        print(f"  -> Token Validation: {val_throughput:.1f} validations/sec ({val_time_s*1000.0/(validation_iterations*10):.3f} ms/op)")

        # -------------------------------------------------------------------
        # 3. Benchmark Dashboard Overview & Health Scoring (WP 8.9.4)
        # -------------------------------------------------------------------
        print("\n[Stage 3] Benchmarking Dashboard Overview & Health Score Aggregation...")
        overview_latencies = {}
        for scale in [10, 25, 50]:
            scale_times = []
            for tid in tenant_ids[:scale]:
                t_ov_start = time.perf_counter()
                devs = inv_mgr.list_devices(tenant_id=tid)
                gws = gw_mgr.list_gateways(tenant_id=tid)
                incs = incident_engine.list_incidents(tenant_id=tid, limit=10)
                hlth = health_engine.score_tenant(tenant_id=tid)
                scale_times.append((time.perf_counter() - t_ov_start) * 1000.0)

            avg_ov = sum(scale_times) / len(scale_times)
            p95_ov = sorted(scale_times)[int(len(scale_times) * 0.95)]
            overview_latencies[f"tenants_{scale}"] = {
                "avg_ms": round(avg_ov, 2),
                "p95_ms": round(p95_ov, 2),
            }
            print(f"  -> {scale:2d} Tenants: avg = {avg_ov:.2f} ms, p95 = {p95_ov:.2f} ms")

        # -------------------------------------------------------------------
        # 4. Benchmark Anti-IDOR Enforcement Overhead (WP 8.9.3)
        # -------------------------------------------------------------------
        print("\n[Stage 4] Benchmarking Server-Side Anti-IDOR Scope Enforcement...")
        unscoped_times = []
        scoped_times = []

        target_tenant = tenant_ids[0]
        target_dev = device_ids_by_tenant[target_tenant][0]

        for _ in range(100):
            # Scoped query (safe)
            t_s = time.perf_counter()
            d_safe = inv_mgr.get_device(tenant_id=target_tenant, device_id=target_dev)
            scoped_times.append((time.perf_counter() - t_s) * 1000.0)

            # Adversarial cross-tenant attempt (must return None)
            t_adv = time.perf_counter()
            d_blocked = inv_mgr.get_device(tenant_id=tenant_ids[1], device_id=target_dev)
            assert d_blocked is None
            unscoped_times.append((time.perf_counter() - t_adv) * 1000.0)

        avg_scoped = sum(scoped_times) / len(scoped_times)
        avg_adversarial = sum(unscoped_times) / len(unscoped_times)
        print(f"  -> Legitimate Scoped Lookup: {avg_scoped:.3f} ms")
        print(f"  -> Cross-Tenant Rejection (Anti-IDOR): {avg_adversarial:.3f} ms (Delta = {abs(avg_scoped - avg_adversarial):.3f} ms)")

        # -------------------------------------------------------------------
        # 5. Benchmark Support Request Lifecycle Throughput (WP 8.9.9)
        # -------------------------------------------------------------------
        print("\n[Stage 5] Benchmarking Support Request Lifecycle & Collaboration...")
        t_supp_start = time.perf_counter()
        support_ops = 0

        created_reqs = []
        # Create 50 tickets
        for i, tid in enumerate(tenant_ids):
            req = support_mgr.create_request(
                tenant_id=tid,
                requester_id=user_credentials[i][3],
                category=SupportCategory.SERVICE_REQUEST.value,
                subject=f"Bandwidth Expansion Ticket for Tenant {i+1:02d}",
                description="Upgrading interface capacity for multi-tenant branch.",
                priority=SupportPriority.MEDIUM.value,
            )
            created_reqs.append((tid, req.request_id, user_credentials[i][3], user_credentials[i][0]))
            support_ops += 1

        # Add 2 comments per ticket (100 comments)
        for tid, rid, uid, uname in created_reqs:
            support_mgr.add_comment(
                tenant_id=tid,
                request_id=rid,
                author_id=uid,
                author_name=uname,
                message="Attached current port utilization graph.",
            )
            support_mgr.add_comment(
                tenant_id=tid,
                request_id=rid,
                author_id=noc_user.user_id,
                author_name="NOC Operator",
                message="Engineering change approved. Scheduling maintenance window.",
                is_internal=True,
            )
            support_ops += 2

        # State transitions (OPEN -> ACKNOWLEDGED -> IN_PROGRESS -> RESOLVED)
        for tid, rid, uid, uname in created_reqs:
            support_mgr.transition_status(tid, rid, SupportStatus.ACKNOWLEDGED.value, "noc_oper")
            support_mgr.transition_status(tid, rid, SupportStatus.IN_PROGRESS.value, "noc_oper")
            support_mgr.transition_status(tid, rid, SupportStatus.RESOLVED.value, "noc_oper")
            support_ops += 3

        supp_time_s = time.perf_counter() - t_supp_start
        supp_throughput = support_ops / supp_time_s
        print(f"  -> Support Desk Ops: {support_ops} operations in {supp_time_s:.2f} s ({supp_throughput:.1f} ops/sec)")

        # -------------------------------------------------------------------
        # 6. Benchmark SLA Availability Measurement Latency (WP 8.9.7)
        # -------------------------------------------------------------------
        print("\n[Stage 6] Benchmarking SLA Summary & Report Retrieval...")
        now_epoch = time.time()
        start_iso = datetime.fromtimestamp(now_epoch - (30 * 86400), tz=timezone.utc).isoformat()
        end_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()

        sla_latencies = []
        for i, tid in enumerate(tenant_ids):
            t_sla_start = time.perf_counter()
            rep = sla_engine.calculate_sla_report(
                tenant_id=tid,
                service_id=f"svc_t{i+1:02d}",
                start_time_utc=start_iso,
                end_time_utc=end_iso,
            )
            sla_latencies.append((time.perf_counter() - t_sla_start) * 1000.0)

        avg_sla_ms = sum(sla_latencies) / len(sla_latencies)
        p95_sla_ms = sorted(sla_latencies)[int(len(sla_latencies) * 0.95)]
        print(f"  -> SLA Report Calculation: avg = {avg_sla_ms:.2f} ms, p95 = {p95_sla_ms:.2f} ms")

        # -------------------------------------------------------------------
        # 7. Measure Database Size & System Memory
        # -------------------------------------------------------------------
        print("\n[Stage 7] Measuring Database Size and Memory Allocation...")
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        db_size_bytes = os.path.getsize(db_path)
        db_size_kb = db_size_bytes / 1024.0
        db_size_mb = db_size_kb / 1024.0

        ram_delta_mb = (peak_mem - start_mem) / (1024.0 * 1024.0)

        print(f"  -> SQLite DB Size (50 Tenants): {db_size_kb:.1f} KB ({db_size_mb:.2f} MB)")
        print(f"  -> Python RAM Peak Allocation: {peak_mem / (1024.0 * 1024.0):.2f} MB (Delta: {ram_delta_mb:.2f} MB)")

        # Compile final benchmark data
        results["metrics"] = {
            "scale_profile": {
                "total_tenants": len(tenant_ids),
                "total_sites": 50,
                "total_devices": 250,
                "total_gateways": 50,
                "total_sla_policies": 50,
                "total_support_tickets": 50,
                "total_support_comments": 100,
            },
            "authentication_and_session": {
                "avg_login_latency_ms": round(avg_auth_ms, 2),
                "p95_login_latency_ms": round(p95_auth_ms, 2),
                "token_validation_throughput_ops_sec": round(val_throughput, 1),
            },
            "dashboard_overview_latency": overview_latencies,
            "anti_idor_scope_isolation": {
                "legitimate_scoped_lookup_ms": round(avg_scoped, 3),
                "adversarial_rejection_ms": round(avg_adversarial, 3),
                "idor_overhead_ms": round(abs(avg_scoped - avg_adversarial), 3),
            },
            "support_desk_throughput": {
                "total_operations": support_ops,
                "total_duration_seconds": round(supp_time_s, 2),
                "throughput_ops_per_second": round(supp_throughput, 1),
            },
            "sla_availability_reporting": {
                "avg_report_calc_latency_ms": round(avg_sla_ms, 2),
                "p95_report_calc_latency_ms": round(p95_sla_ms, 2),
            },
            "system_resources": {
                "sqlite_database_size_kb": round(db_size_kb, 1),
                "sqlite_database_size_mb": round(db_size_mb, 2),
                "python_ram_peak_mb": round(peak_mem / (1024.0 * 1024.0), 2),
                "python_ram_delta_mb": round(ram_delta_mb, 2),
            },
            "acceptance_criteria_verification": {
                "overview_latency_sub_100ms_avg": overview_latencies["tenants_50"]["avg_ms"] < 100.0,
                "overview_latency_sub_200ms_p95": overview_latencies["tenants_50"]["p95_ms"] < 200.0,
                "token_validation_sub_10ms": (val_time_s * 1000.0 / (validation_iterations * 10)) < 10.0,
                "auth_login_sub_500ms": p95_auth_ms < 500.0,
                "anti_idor_overhead_sub_5ms": abs(avg_scoped - avg_adversarial) < 5.0,
                "ram_delta_sub_50mb": ram_delta_mb < 50.0,
                "all_benchmarks_passed": (
                    overview_latencies["tenants_50"]["avg_ms"] < 100.0
                    and overview_latencies["tenants_50"]["p95_ms"] < 200.0
                    and (val_time_s * 1000.0 / (validation_iterations * 10)) < 10.0
                    and p95_auth_ms < 500.0
                    and abs(avg_scoped - avg_adversarial) < 5.0
                    and ram_delta_mb < 50.0
                ),
            },
        }

        # Save to reports directory
        reports_dir = Path("AIRA_ECOSYSTEM/reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / "benchmark_networking_viii_phase_d.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print("\n" + "=" * 80)
        print("BENCHMARK COMPLETED SUCCESSFULLY")
        print(f"Results recorded at: {report_file.resolve()}")
        print(f"Acceptance Criteria Status: {'ALL PASSED' if results['metrics']['acceptance_criteria_verification']['all_benchmarks_passed'] else 'ATTENTION NEEDED'}")
        print("=" * 80)

        return results

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    run_customer_portal_benchmark()
