"""
api/routers/topology.py — REST API for AIRA Topology Fabric V2:
Evidence-Based Discovery, ISP Boundary Detection, Device Ownership & Physical-Link Confidence.

Maintains 100% backward compatibility with existing endpoints while adding:
- Typed V2 governance, policy, evidence, conflict review, and link verification endpoints
- Administrative authorization guard (`require_topology_admin`)
- Rate-limited, timeout-bounded ICMP probing (`probe_node_icmp`)
- Single-flight bounded discovery restricted to authorized Inventory devices (zero secret leakage)
- Explicit `confirm=true` guard on destructive topology reset (`DELETE /api/topology/clear`)
"""

from __future__ import annotations

import hmac
import logging
import os
import socket
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.topology_engine import get_topology_engine
from agents.akane.connection_manager import get_connection_manager
from core.topology_models import bounded_icmp_ping, sanitize_untrusted_text

logger = logging.getLogger("aira.topology")

router = APIRouter(prefix="/api/topology", tags=["topology"])

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

def _probe_tcp_port(host: str, port: int, timeout_sec: float = 3.0) -> tuple[bool, float, str]:
    t0 = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_sec)
    try:
        sock.connect((host, port))
        elapsed_ms = (time.time() - t0) * 1000.0
        return True, elapsed_ms, ""
    except (socket.timeout, OSError) as exc:
        elapsed_ms = (time.time() - t0) * 1000.0
        return False, elapsed_ms, f"Koneksi port {port} gagal: {exc}"
    finally:
        try:
            sock.close()
        except Exception:
            pass



def require_topology_admin(request: Request) -> str:
    """
    Authorization guard for state-mutating and administrative topology actions.
    - When `AIRA_TOPOLOGY_ADMIN_TOKEN` or `AIRA_ADMIN_TOKEN` is configured, requires a matching
      token via `X-AIRA-Admin-Token` or `Authorization: Bearer <token>`.
    - Otherwise (default local workstation deployment), restricts mutations to loopback/local clients.
    """
    expected_token = (
        os.environ.get("AIRA_TOPOLOGY_ADMIN_TOKEN")
        or os.environ.get("AIRA_ADMIN_TOKEN")
        or ""
    ).strip()

    header_token = (request.headers.get("X-AIRA-Admin-Token") or "").strip()
    if not header_token:
        auth_hdr = (request.headers.get("Authorization") or "").strip()
        if auth_hdr.lower().startswith("bearer "):
            header_token = auth_hdr[7:].strip()

    if expected_token:
        if not header_token or not hmac.compare_digest(header_token, expected_token):
            raise HTTPException(
                status_code=403,
                detail="Unauthorized: valid admin token required for topology modifications.",
            )
    else:
        client_host = (request.client.host if request.client else "").strip().lower()
        if client_host and client_host not in _LOCAL_HOSTS:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: remote topology modifications require AIRA_TOPOLOGY_ADMIN_TOKEN.",
            )

    actor = sanitize_untrusted_text(request.headers.get("X-AIRA-Actor") or "admin", 64)
    return actor or "admin"


# ---------------------------------------------------------------------------
# Request Schemas (V1 Backward-Compatible + V2 Governance Extensions)
# ---------------------------------------------------------------------------


class PositionIn(BaseModel):
    pos_x: float
    pos_y: float


class NodeIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    identity: Optional[str] = None
    ip: Optional[str] = ""
    mac: Optional[str] = ""
    device_type: str = "router"
    status: str = "online"
    pos_x: Optional[float] = 0.0
    pos_y: Optional[float] = 0.0
    metadata: Optional[Dict[str, Any]] = None
    ownership_status: Optional[str] = None
    topology_scope: Optional[str] = None
    trust_zone: Optional[str] = None
    device_role: Optional[str] = None
    # Manajemen & Registrasi Inventory
    port: int = 22
    username: Optional[str] = "admin"
    password: Optional[str] = Field(default=None, repr=False)
    snmp_community: Optional[str] = Field(default=None, repr=False)
    snmp_port: int = 161
    register_inventory: bool = True
    note: str = ""


class NodeTestIn(BaseModel):
    host: str = Field(..., min_length=1, max_length=255)
    port: int = 22
    username: Optional[str] = "admin"
    password: Optional[str] = Field(default=None, repr=False)
    device_type: str = "router"
    snmp_community: Optional[str] = Field(default=None, repr=False)
    snmp_port: int = 161


class NodeUpdateIn(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=128)
    identity: Optional[str] = None
    ip: Optional[str] = ""
    mac: Optional[str] = ""
    device_type: str = "router"
    status: str = "online"
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    ownership_status: Optional[str] = None
    topology_scope: Optional[str] = None
    trust_zone: Optional[str] = None
    device_role: Optional[str] = None


class LinkIn(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=128)
    target_id: str = Field(..., min_length=1, max_length=128)
    source_port: str = ""
    target_port: str = ""
    link_type: str = "ethernet"
    status: str = "up"
    bandwidth: str = ""
    verification_status: str = "manual"
    notes: str = ""


class DiscoverIn(BaseModel):
    device_name: Optional[str] = None
    host: Optional[str] = None
    mode: Optional[str] = None
    # Accepted only for V1 payload compatibility; never persisted, echoed, or used for unverified hosts:
    username: Optional[str] = Field(default=None, repr=False)
    password: Optional[str] = Field(default=None, repr=False)
    port: int = 22


class PolicyUpdateIn(BaseModel):
    enterprise_id: Optional[str] = None
    seed_device_id: Optional[str] = None
    discovery_mode: Optional[str] = None
    view_mode: Optional[str] = None
    management_subnets: Optional[List[str]] = None
    enterprise_subnets: Optional[List[str]] = None
    approved_discovery_scopes: Optional[List[str]] = None
    excluded_subnets: Optional[List[str]] = None
    isp_boundary_interfaces: Optional[List[str]] = None
    known_isp_devices: Optional[List[str]] = None
    known_external_devices: Optional[List[str]] = None
    approved_discovery_protocols: Optional[List[str]] = None
    discovery_depth: Optional[int] = None
    allow_routed_expansion: Optional[bool] = None
    auto_include_unknown_neighbors: Optional[bool] = None
    require_review_for_unknown_devices: Optional[bool] = None
    freshness_threshold_sec: Optional[int] = None
    expire_threshold_sec: Optional[int] = None
    probe_cooldown_sec: Optional[int] = None
    probe_timeout_sec: Optional[int] = None
    probe_retries: Optional[int] = None
    max_concurrency: Optional[int] = None
    max_scan_duration_sec: Optional[int] = None


class NodeClassifyIn(BaseModel):
    name: Optional[str] = None
    identity: Optional[str] = None
    ownership_status: Optional[str] = None
    topology_scope: Optional[str] = None
    trust_zone: Optional[str] = None
    device_role: Optional[str] = None
    is_isp_boundary: Optional[bool] = None
    excluded_from_discovery: Optional[bool] = None
    reason: str = ""


class LinkVerifyIn(BaseModel):
    link_id: str = Field(..., min_length=1, max_length=256)
    verification_status: str = "confirmed"
    source_port: Optional[str] = None
    target_port: Optional[str] = None
    link_type: Optional[str] = None
    notes: Optional[str] = None
    reason: str = ""


class ConflictResolveIn(BaseModel):
    status: str = "resolved"


# ---------------------------------------------------------------------------
# Core Topology Read & Lightweight Refresh Endpoints
# ---------------------------------------------------------------------------


@router.get("")
def get_topology(view_mode: Optional[str] = Query(default=None)):
    """Mengambil data lengkap graf topologi beserta metadata V2 (ownership, scope, confidence, freshness)."""
    engine = get_topology_engine()
    return engine.get_topology(view_mode=view_mode)


@router.post("/refresh-status")
def refresh_topology_statuses():
    """Evaluasi ringan status & kesegaran observasi (fresh/stale/expired) tanpa membuka sesi SSH."""
    return get_topology_engine().refresh_statuses()


# ---------------------------------------------------------------------------
# Policy, Jobs, Review Queue, Conflicts & Audit Log (V2)
# ---------------------------------------------------------------------------


@router.get("/policy")
def get_topology_policy():
    """Mengambil konfigurasi kebijakan batas enterprise/ISP dan mode discovery."""
    return {"success": True, "policy": get_topology_engine().get_policy()}


@router.put("/policy")
def update_topology_policy(body: PolicyUpdateIn, actor: str = Depends(require_topology_admin)):
    """Memperbarui kebijakan batas enterprise/ISP, subnet yang diizinkan/dikecualikan, dan mode discovery."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        updated = get_topology_engine().update_policy(updates, actor=actor)
        return {"success": True, "policy": updated}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=sanitize_untrusted_text(str(exc), 300)) from exc


@router.get("/jobs")
def list_discovery_jobs(limit: int = Query(default=15, ge=1, le=100)):
    """Riwayat eksekusi discovery beserta durasi, batasan observasi, dan error."""
    return {"success": True, "jobs": get_topology_engine().get_discovery_jobs(limit=limit)}


@router.get("/review")
def get_review_queue():
    """Daftar perangkat unknown/pending_review, link belum terverifikasi, dan konflik identitas/port."""
    return get_topology_engine().get_review_queue()


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_topology_conflict(
    conflict_id: int,
    body: ConflictResolveIn,
    actor: str = Depends(require_topology_admin),
):
    """Menandai konflik topologi sebagai resolved atau ignored dengan jejak audit."""
    try:
        ok = get_topology_engine().resolve_conflict(conflict_id, status=body.status, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=sanitize_untrusted_text(str(exc), 200)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Conflict tidak ditemukan.")
    return {"success": True, "conflict_id": conflict_id, "status": body.status}


@router.get("/audit-log")
def get_topology_audit_log(limit: int = Query(default=30, ge=1, le=200)):
    """Jejak audit perubahan kebijakan, klasifikasi ownership/scope, dan verifikasi link."""
    return {"success": True, "audit_log": get_topology_engine().get_audit_log(limit=limit)}


# ---------------------------------------------------------------------------
# Node CRUD, Classification Overrides, Evidence, Ping & Troubleshooting
# ---------------------------------------------------------------------------


@router.put("/nodes/{node_id}/position")
def update_position(node_id: str, body: PositionIn, _actor: str = Depends(require_topology_admin)):
    """Menyimpan posisi koordinat node saat digeser di canvas (drag & drop)."""
    ok = get_topology_engine().update_node_position(node_id, body.pos_x, body.pos_y)
    if not ok:
        raise HTTPException(status_code=404, detail="Node tidak ditemukan.")
    return {"success": True, "node_id": node_id, "pos_x": body.pos_x, "pos_y": body.pos_y}


@router.post("/nodes/test")
@router.post("/test-reachability")
def test_node_connectivity(body: NodeTestIn, _actor: str = Depends(require_topology_admin)):
    """
    Menguji keterjangkauan dan otentikasi perangkat sebelum disimpan ke topologi/inventory.
    - Mengukur latency ICMP dan TCP port (22/8728)
    - Jika SSH username & password diberikan, menguji login SSH secara terisolasi tanpa menyimpan secret.
    - Password TIDAK PERNAH dikembalikan dalam response ataupun dicatat ke log.
    """
    host = (body.host or "").strip()
    port = body.port or 22
    if not host:
        raise HTTPException(status_code=400, detail="Host / IP address tidak boleh kosong.")

    t0 = time.time()
    reachable = False
    port_open = False
    auth_ok = False
    identity = None
    error_msg = ""
    elapsed_ms = 0.0

    # 1. TCP socket probe dengan timeout terikat
    port_open, elapsed_ms, probe_err = _probe_tcp_port(host, port, 3.0)
    reachable = port_open
    if probe_err:
        error_msg = probe_err

    # 2. Jika port gagal, coba ICMP ping sebagai penentu reachability L3
    if not reachable:
        ping_res = bounded_icmp_ping(host, count=1, timeout_sec=2)
        if ping_res.get("alive"):
            reachable = True
            elapsed_ms = float(ping_res.get("avg_rtt_ms") or elapsed_ms)
            error_msg = f"Host merespons ICMP ping ({elapsed_ms:.1f}ms), namun port {port} tertutup/filtered."

    # 3. Jika port terbuka dan kredensial SSH disediakan, uji SSH auth via ConnectionManager
    if port_open and body.username and port in (22, 2222):
        mgr = get_connection_manager()
        preflight_res = mgr.test_target_credentials(
            host=host,
            username=body.username,
            password=body.password,
            port=port,
            timeout=4.0,
        )
        auth_ok = preflight_res.get("authenticated", False)
        if preflight_res.get("identity"):
            identity = preflight_res["identity"]
        if not auth_ok and preflight_res.get("message"):
            error_msg = preflight_res["message"]

    return {
        "success": True,
        "reachable": reachable,
        "port_open": port_open,
        "authenticated": auth_ok,
        "latency_ms": round(elapsed_ms, 1) if reachable else None,
        "identity": identity,
        "message": error_msg or ("Koneksi & autentikasi berhasil!" if auth_ok else ("Host dapat dijangkau." if reachable else "Host tidak merespons.")),
    }


@router.post("/nodes")
def add_node(body: NodeIn, actor: str = Depends(require_topology_admin)):
    """Menambahkan node secara manual ke topologi (provenance='user_managed') dan mendaftarkannya ke Inventory."""
    meta = dict(body.metadata or {})
    host = (body.ip or "").strip()
    inv_id = None
    inv_name = body.name

    # 1. Pendaftaran ke InventoryStore (jika diizinkan dan IP valid)
    if body.register_inventory and host:
        try:
            from core.inventory_store import get_inventory_store
            inv = get_inventory_store()

            existing_dev = None
            inv_list = inv.list_devices().get("devices", [])
            for d in inv_list:
                if d.get("name", "").lower() == body.name.lower() or d.get("host") == host:
                    existing_dev = d
                    break

            dev_type = "mikrotik" if body.device_type in ("router", "switch") else body.device_type
            new_cred = None
            if body.password is not None and body.password != "":
                new_cred = {
                    "type": "ssh_password",
                    "username": body.username or "admin",
                    "secret": body.password,
                    "note": f"Dibuat via Topologi untuk {body.name}",
                }

            if existing_dev:
                inv_id = existing_dev["id"]
                inv_name = existing_dev["name"]
                update_fields = {
                    "host": host,
                    "port": body.port or 22,
                    "username": body.username or "admin",
                    "device_type": dev_type,
                    "snmp_port": body.snmp_port or 161,
                }
                if body.snmp_community:
                    update_fields["snmp_community"] = body.snmp_community
                if new_cred:
                    update_fields["new_credential"] = new_cred
                inv.update_device(inv_name, **update_fields)
            else:
                inv_res = inv.create_device(
                    name=body.name,
                    host=host,
                    port=body.port or 22,
                    username=body.username or "admin",
                    device_type=dev_type,
                    snmp_community=body.snmp_community,
                    snmp_port=body.snmp_port or 161,
                    note=body.note or f"Didaftarkan dari Topology Editor oleh {actor}",
                    new_credential=new_cred,
                )
                if inv_res.get("success") and inv_res.get("device"):
                    inv_id = inv_res["device"]["id"]
                    inv_name = inv_res["device"]["name"]

            if inv_id is not None:
                meta["inventory_device_id"] = inv_id
                meta["inventory_name"] = inv_name
        except Exception as exc:
            logger.warning("INVENTORY | Gagal mendaftarkan node %s ke inventory: %s", body.name, exc)

    # 2. Sinkronisasi profil ke NMS Engine jika engine aktif
    try:
        from core.nms_engine import get_nms_engine
        nms = get_nms_engine()
        mgmt_method = "mikrotik_api" if body.device_type == "router" else "icmp_ping"
        nms.upsert_device_profile(
            device_id=body.id,
            display_name=body.name,
            host=host,
            management_method=mgmt_method,
            snmp_community=body.snmp_community,
            snmp_port=body.snmp_port or 161,
        )
    except Exception as exc:
        logger.warning("NMS | Gagal memperbarui profil pemantauan untuk node %s: %s", body.name, exc)

    # 3. Simpan node ke database graf topologi
    return get_topology_engine().upsert_node(
        node_id=body.id,
        name=body.name,
        identity=body.identity,
        ip=body.ip,
        mac=body.mac,
        device_type=body.device_type,
        status=body.status,
        pos_x=body.pos_x,
        pos_y=body.pos_y,
        metadata=meta,
        ownership_status=body.ownership_status,
        topology_scope=body.topology_scope,
        trust_zone=body.trust_zone,
        device_role=body.device_role,
        provenance="user_managed",
    )


@router.put("/nodes/{node_id}")
def update_node_details(node_id: str, body: NodeUpdateIn, _actor: str = Depends(require_topology_admin)):
    """Koreksi / edit manual detail node perangkat oleh pengguna."""
    return get_topology_engine().upsert_node(
        node_id=node_id,
        name=body.name,
        identity=body.identity,
        ip=body.ip,
        mac=body.mac,
        device_type=body.device_type,
        status=body.status,
        pos_x=body.pos_x,
        pos_y=body.pos_y,
        metadata=body.metadata,
        ownership_status=body.ownership_status,
        topology_scope=body.topology_scope,
        trust_zone=body.trust_zone,
        device_role=body.device_role,
        provenance="user_managed",
    )


@router.post("/nodes/{node_id}/classify")
def classify_node(
    node_id: str,
    body: NodeClassifyIn,
    actor: str = Depends(require_topology_admin),
):
    """Menetapkan override ownership, scope, trust zone, ISP boundary, atau eksklusi discovery."""
    try:
        res = get_topology_engine().classify_node_override(
            node_id,
            name=body.name,
            identity=body.identity,
            ownership_status=body.ownership_status,
            topology_scope=body.topology_scope,
            trust_zone=body.trust_zone,
            device_role=body.device_role,
            is_isp_boundary=body.is_isp_boundary,
            excluded_from_discovery=body.excluded_from_discovery,
            reason=body.reason,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=sanitize_untrusted_text(str(exc), 250)) from exc

    if res.get("not_found"):
        raise HTTPException(status_code=404, detail=res.get("error", "Node tidak ditemukan."))
    return res


@router.get("/nodes/{node_id}/evidence")
def get_node_evidence(node_id: str):
    """Mengambil daftar bukti observasi (MNDP/LLDP/CDP/ARP/Route/Ping/SSH/Manual) untuk sebuah node."""
    return {
        "success": True,
        "node_id": node_id,
        "evidence": get_topology_engine().get_node_evidence(node_id),
    }


@router.delete("/nodes/{node_id}")
def delete_node(node_id: str, _actor: str = Depends(require_topology_admin)):
    """Menghapus node dan semua link yang terhubung dengannya serta sinkron ke Inventory dan NMS."""
    engine = get_topology_engine()
    topo_data = engine.get_topology()
    target_node = next((n for n in topo_data.get("nodes", []) if n.get("id") == node_id), None)

    ok = engine.delete_node(node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Node tidak ditemukan.")

    if target_node:
        try:
            from core.inventory_store import get_inventory_store
            inv = get_inventory_store()
            dev_list = inv.list_devices().get("devices", [])
            for dev in dev_list:
                if dev.get("name") == target_node.get("name") or (target_node.get("ip") and dev.get("host") == target_node.get("ip")):
                    inv.delete_device(dev["name"])
        except Exception as exc:
            logger.warning("Gagal sinkronisasi hapus node ke inventory: %s", exc)

    return {"success": True, "node_id": node_id}


@router.post("/nodes/{node_id}/ping")
def ping_node(node_id: str, _actor: str = Depends(require_topology_admin)):
    """
    Melakukan ICMP ping terukur (rate-limited & timeout-bounded) ke IP node.
    Hanya memperbarui reachability_status & latency; TIDAK mengubah ownership atau membuat kabel fisik.
    """
    res = get_topology_engine().probe_node_icmp(node_id)
    if res.get("not_found"):
        raise HTTPException(status_code=404, detail="Node tidak ditemukan.")
    if res.get("rate_limited"):
        return JSONResponse(status_code=429, content=res)
    return res


@router.get("/nodes/{node_id}/troubleshoot")
def troubleshoot_node(node_id: str):
    """Menjalankan Root Cause Analysis (RCA) dan path tracing untuk node tertentu."""
    res = get_topology_engine().troubleshoot_node(node_id)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error"))
    return res


# ---------------------------------------------------------------------------
# Link CRUD, Evidence & Administrative Verification
# ---------------------------------------------------------------------------


@router.get("/links/evidence")
def get_link_evidence(link_id: str = Query(..., min_length=1)):
    """Mengambil bukti observasi dan verifikasi port untuk sebuah link."""
    return {
        "success": True,
        "link_id": link_id,
        "evidence": get_topology_engine().get_link_evidence(link_id),
    }


@router.post("/links/verify")
def verify_link(body: LinkVerifyIn, actor: str = Depends(require_topology_admin)):
    """Mengonfirmasi atau mengoreksi verifikasi link fisik/port secara eksplisit oleh admin."""
    try:
        res = get_topology_engine().verify_or_override_link(
            body.link_id,
            verification_status=body.verification_status,
            source_port=body.source_port,
            target_port=body.target_port,
            link_type=body.link_type,
            notes=body.notes,
            reason=body.reason,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=sanitize_untrusted_text(str(exc), 250)) from exc

    if res.get("not_found"):
        raise HTTPException(status_code=404, detail=res.get("error", "Link tidak ditemukan."))
    return res


@router.post("/links")
def add_link(body: LinkIn, _actor: str = Depends(require_topology_admin)):
    """Menghubungkan dua node dengan link manual (provenance='user_managed', verification='manual')."""
    return get_topology_engine().upsert_link(
        source_id=body.source_id,
        target_id=body.target_id,
        source_port=body.source_port,
        target_port=body.target_port,
        link_type=body.link_type,
        status=body.status,
        bandwidth=body.bandwidth,
        verification_status=body.verification_status or "manual",
        provenance="user_managed",
        notes=body.notes,
    )


@router.delete("/links")
def delete_link(link_id: str = Query(..., min_length=1), _actor: str = Depends(require_topology_admin)):
    """Menghapus link/kabel tertentu antara dua perangkat."""
    ok = get_topology_engine().delete_link(link_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Link tidak ditemukan.")
    return {"success": True, "link_id": link_id}


# ---------------------------------------------------------------------------
# Bounded Discovery, Demo Seeding & Guarded Reset
# ---------------------------------------------------------------------------


@router.post("/discover")
def trigger_discovery(body: DiscoverIn, _actor: str = Depends(require_topology_admin)):
    """
    Menjalankan proses auto-discovery berbasis bukti (MNDP/LLDP/CDP/ARP/Route/Bridge/DHCP)
    secara read-only dan terbatas pada seed router resmi di Inventory.
    """
    engine = get_topology_engine()
    try:
        res = engine.sync_from_seed_router(
            device_name=body.device_name,
            host=body.host,
            mode=body.mode,
        )
        if res.get("already_running"):
            return JSONResponse(
                status_code=409,
                content={
                    **res,
                    "detail": sanitize_untrusted_text(res.get("error", "Discovery sedang berjalan."), 200),
                },
            )
        if not res.get("success"):
            clean_err = sanitize_untrusted_text(
                res.get("error", "Gagal melakukan discovery topologi."),
                250,
            )
            return {
                "success": False,
                "job_id": res.get("job_id"),
                "detail": clean_err,
                "error": clean_err,
            }
        return res
    except Exception as exc:
        safe_msg = sanitize_untrusted_text(str(exc), 200)
        raise HTTPException(status_code=500, detail=f"Gagal menjalankan discovery: {safe_msg}") from exc


@router.delete("/clear")
def clear_topology(
    confirm: bool = Query(default=False, description="Wajib bernilai true untuk mengonfirmasi penghapusan seluruh graf."),
    _actor: str = Depends(require_topology_admin),
):
    """Mengosongkan seluruh graf topologi (membutuhkan konfirmasi eksplisit confirm=true)."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Penghapusan seluruh topologi membutuhkan konfirmasi eksplisit (?confirm=true).",
        )
    return get_topology_engine().clear_topology()


@router.post("/seed-demo")
def seed_demo_topology(_actor: str = Depends(require_topology_admin)):
    """Mengisi topologi sampel realistis perusahaan lengkap dengan klasifikasi V2 (Internal, Edge, ISP, Confirmed/Observed/Inferred)."""
    engine = get_topology_engine()

    demo_nodes = [
        {
            "node_id": "node_isp_upstream",
            "name": "ISP-Upstream-PE",
            "identity": "Telkom-MetroE-PE1",
            "ip": "203.0.113.1",
            "mac": "DC:2C:6E:99:00:01",
            "device_type": "wan",
            "status": "online",
            "pos_x": 450,
            "pos_y": 35,
            "latency_ms": 4.2,
            "ownership_status": "third_party",
            "topology_scope": "isp_upstream",
            "trust_zone": "isp",
            "device_role": "isp_gateway",
            "metadata": {"model": "ISP Metro-E PE", "is_isp_boundary": True, "role": "isp_gateway"},
        },
        {
            "node_id": "node_core_router",
            "name": "Core-CCR2004",
            "identity": "Core-CCR2004-Gateway",
            "ip": "10.0.0.1",
            "mac": "48:8F:5A:01:00:01",
            "device_type": "router",
            "status": "online",
            "pos_x": 450,
            "pos_y": 150,
            "latency_ms": 1.2,
            "ownership_status": "owned",
            "topology_scope": "enterprise_edge",
            "trust_zone": "edge",
            "device_role": "backbone",
            "metadata": {"model": "CCR2004-1G-12S+2XS", "uptime": "42d 18h", "cpu_load": 14, "version": "RouterOS v7.16", "role": "backbone", "wan_interface": "ether1"},
        },
        {
            "node_id": "node_sw_dist_1",
            "name": "SW-Dist-Lt1",
            "identity": "SW-CRS326-Lt1",
            "ip": "10.0.0.2",
            "mac": "48:8F:5A:02:00:02",
            "device_type": "switch",
            "status": "online",
            "pos_x": 230,
            "pos_y": 295,
            "latency_ms": 2.1,
            "ownership_status": "owned",
            "topology_scope": "enterprise_internal",
            "trust_zone": "internal",
            "device_role": "distribution",
            "metadata": {"model": "CRS326-24G-2S+", "uptime": "42d 18h", "cpu_load": 8, "version": "RouterOS v7.16"},
        },
        {
            "node_id": "node_sw_dist_2",
            "name": "SW-Dist-Lt2",
            "identity": "SW-CRS328-Lt2",
            "ip": "10.0.0.3",
            "mac": "48:8F:5A:03:00:03",
            "device_type": "switch",
            "status": "online",
            "pos_x": 670,
            "pos_y": 295,
            "latency_ms": 2.4,
            "ownership_status": "owned",
            "topology_scope": "enterprise_internal",
            "trust_zone": "internal",
            "device_role": "distribution",
            "metadata": {"model": "CRS328-24P-4S+", "uptime": "15d 04h", "cpu_load": 12, "version": "RouterOS v7.16"},
        },
        {
            "node_id": "node_ap_lobby",
            "name": "AP-Lobby-Lt1",
            "identity": "cAP-ax-Lobby",
            "ip": "10.0.10.11",
            "mac": "48:8F:5A:04:00:04",
            "device_type": "access_point",
            "status": "online",
            "pos_x": 120,
            "pos_y": 455,
            "latency_ms": 4.5,
            "ownership_status": "owned",
            "topology_scope": "enterprise_internal",
            "trust_zone": "internal",
            "device_role": "access",
            "metadata": {"model": "cAP ax", "clients": 28, "ssid": "CORP-WIFI"},
        },
        {
            "node_id": "node_ap_staff",
            "name": "AP-Staff-Lt2",
            "identity": "cAP-ax-Staff",
            "ip": "10.0.20.21",
            "mac": "48:8F:5A:06:00:06",
            "device_type": "access_point",
            "status": "warning",
            "pos_x": 540,
            "pos_y": 455,
            "latency_ms": 45.2,
            "ownership_status": "unknown",
            "topology_scope": "unclassified",
            "trust_zone": "unknown",
            "device_role": "access",
            "metadata": {"model": "cAP ax", "clients": 42, "warning": "Observed via single-sided MNDP; pending ownership confirmation"},
        },
        {
            "node_id": "node_server_nas",
            "name": "Server-Storage",
            "identity": "TrueNAS-Enterprise",
            "ip": "10.0.50.5",
            "mac": "00:15:5D:AA:BB:CC",
            "device_type": "server",
            "status": "online",
            "pos_x": 780,
            "pos_y": 455,
            "latency_ms": 1.5,
            "ownership_status": "owned",
            "topology_scope": "enterprise_internal",
            "trust_zone": "internal",
            "device_role": "server",
            "metadata": {"os": "Linux / ZFS", "service": "NFS/SMB Storage"},
        },
    ]

    for n in demo_nodes:
        engine.upsert_node(**n)

    demo_links = [
        {"source_id": "node_core_router", "target_id": "node_isp_upstream", "source_port": "ether1", "target_port": "", "link_type": "routed", "verification_status": "inferred", "bandwidth": "ISP Uplink", "status": "up"},
        {"source_id": "node_core_router", "target_id": "node_sw_dist_1", "source_port": "sfp-sfpplus1", "target_port": "sfp-sfpplus1", "link_type": "physical", "verification_status": "confirmed", "bandwidth": "10 Gbps", "status": "up"},
        {"source_id": "node_core_router", "target_id": "node_sw_dist_2", "source_port": "sfp-sfpplus2", "target_port": "sfp-sfpplus1", "link_type": "physical", "verification_status": "confirmed", "bandwidth": "10 Gbps", "status": "up"},
        {"source_id": "node_sw_dist_1", "target_id": "node_ap_lobby", "source_port": "ether1", "target_port": "ether1", "link_type": "layer2_adjacency", "verification_status": "observed", "bandwidth": "1 Gbps", "status": "up"},
        {"source_id": "node_sw_dist_2", "target_id": "node_ap_staff", "source_port": "ether2", "target_port": "", "link_type": "layer2_adjacency", "verification_status": "observed", "bandwidth": "1 Gbps", "status": "up"},
        {"source_id": "node_sw_dist_2", "target_id": "node_server_nas", "source_port": "ether24", "target_port": "eno1", "link_type": "physical", "verification_status": "manual", "bandwidth": "1 Gbps", "status": "up"},
    ]

    for l in demo_links:
        engine.upsert_link(**l)

    return {"success": True, "message": "Demo topology V2 berhasil di-generate.", "nodes": len(demo_nodes), "links": len(demo_links)}
