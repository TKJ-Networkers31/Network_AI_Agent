"""
AIRA OS — Historical Route Analytics & Immutable Route Snapshot Engine (Networking IV / WP 4.6.4).

Capabilities:
- Additive SQLite schema (`route_snapshots`, `route_changes`) inside `topology.db` governed by
  `core.topology_db` (`topology_transaction` + `execute_with_retry` + WAL + 30s busy_timeout).
- Cryptographic SHA-256 snapshot integrity strictly orthogonal to collection completeness.
- SQLite `BEFORE UPDATE` and `BEFORE DELETE` immutability triggers on `route_snapshots`.
- Dedicated `RouteChangeType` domain (never mixed into `TopologyChangeType`).
- False-positive protection: incomplete, unreachable, expired, or parser-failed collections
  never emit `ROUTE_REMOVED`; they emit `ROUTE_STATE_UNKNOWN` with explicit suppression metadata.
- Historical route analytics: churn, stability score, flapping detection, default/gateway/ECMP/VRF
  transitions, and temporal correlation (explicitly distinguished from causation) with
  `topology_changes` and NMS events.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from core.routing.route_collector import (
    PARSER_VERSION,
    RouteCollectionResult,
    RouteCollectionStatus,
    RouteCompleteness,
)
from core.routing.unified_route_parser import NormalizedRoute
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    execute_with_retry,
    topology_transaction,
)

logger = logging.getLogger("aira.routing.history")

MAX_QUERY_LIMIT = 500
DEFAULT_CORRELATION_WINDOW_SEC = 120.0

RETENTION_POLICY: Dict[str, Any] = {
    "policy_name": "IMMUTABLE_APPEND_ONLY_V1",
    "immutable_snapshots": True,
    "destructive_cleanup_enabled": False,
    "max_query_limit": MAX_QUERY_LIMIT,
    "single_worker_write_coordinator": True,
}


class RouteChangeType(str, Enum):
    ROUTE_ADDED = "ROUTE_ADDED"
    ROUTE_REMOVED = "ROUTE_REMOVED"
    ROUTE_MODIFIED = "ROUTE_MODIFIED"
    ROUTE_ACTIVATED = "ROUTE_ACTIVATED"
    ROUTE_DEACTIVATED = "ROUTE_DEACTIVATED"
    ROUTE_DISABLED = "ROUTE_DISABLED"
    ROUTE_ENABLED = "ROUTE_ENABLED"
    NEXT_HOP_CHANGED = "NEXT_HOP_CHANGED"
    GATEWAY_CHANGED = "GATEWAY_CHANGED"
    METRIC_CHANGED = "METRIC_CHANGED"
    DISTANCE_CHANGED = "DISTANCE_CHANGED"
    ROUTING_TABLE_CHANGED = "ROUTING_TABLE_CHANGED"
    ECMP_CHANGED = "ECMP_CHANGED"
    ROUTE_REAPPEARED = "ROUTE_REAPPEARED"
    ROUTE_STATE_UNKNOWN = "ROUTE_STATE_UNKNOWN"


def canonicalize_route_for_snapshot(route: NormalizedRoute | Dict[str, Any]) -> Dict[str, Any]:
    """
    Produces a deterministic, timestamp-independent canonical dictionary for a single route
    so identical routing tables yield identical SHA-256 digests across collections.
    """
    if isinstance(route, NormalizedRoute):
        gws = sorted(str(g).strip() for g in (route.gateways or ([route.gateway] if route.gateway else [])) if str(g).strip())
        rtype_val = str(route.route_type.value if hasattr(route.route_type, "value") else (route.route_type or "unicast")).lower()
        return {
            "routing_table": str(route.routing_table or "main"),
            "dst_prefix": str(route.dst_prefix or ""),
            "prefix_len": int(route.prefix_len or 0),
            "gateway": str(route.gateway or ""),
            "gateways": gws,
            "immediate_gw": str(route.immediate_gw or ""),
            "interface_name": str(route.interface_name or ""),
            "pref_src": str(route.pref_src or ""),
            "protocol": str(route.protocol or "unknown"),
            "route_type": rtype_val,
            "distance": int(route.distance or 0),
            "scope": route.scope,
            "target_scope": route.target_scope,
            "metric": route.metric,
            "active": bool(route.active),
            "disabled": bool(route.disabled),
            "connect": bool(route.connect),
            "static": bool(route.static),
            "dynamic": bool(route.dynamic),
            "ecmp": bool(getattr(route, "is_ecmp", False) or len(gws) > 1),
            "unreachable": bool(route.unreachable or rtype_val == "unreachable"),
            "blackhole": bool(rtype_val == "blackhole"),
            "prohibit": bool(rtype_val == "prohibit"),
            "reject": bool(rtype_val == "reject"),
        }

    gws_raw = route.get("gateways") or ([route.get("gateway")] if route.get("gateway") else [])
    gws = sorted(str(g).strip() for g in gws_raw if str(g).strip())
    return {
        "routing_table": str(route.get("routing_table") or "main"),
        "dst_prefix": str(route.get("dst_prefix") or ""),
        "prefix_len": int(route.get("prefix_len") or 0),
        "gateway": str(route.get("gateway") or ""),
        "gateways": gws,
        "immediate_gw": str(route.get("immediate_gw") or ""),
        "interface_name": str(route.get("interface_name") or ""),
        "pref_src": str(route.get("pref_src") or ""),
        "protocol": str(route.get("protocol") or "unknown"),
        "route_type": str(route.get("route_type") or "unicast"),
        "distance": int(route.get("distance") or 0),
        "scope": route.get("scope"),
        "target_scope": route.get("target_scope"),
        "metric": route.get("metric"),
        "active": bool(route.get("active", False)),
        "disabled": bool(route.get("disabled", False)),
        "connect": bool(route.get("connect", False)),
        "static": bool(route.get("static", False)),
        "dynamic": bool(route.get("dynamic", False)),
        "ecmp": bool(route.get("ecmp", False) or len(gws) > 1),
        "unreachable": bool(route.get("unreachable", False)),
        "blackhole": bool(route.get("blackhole", False)),
        "prohibit": bool(route.get("prohibit", False)),
        "reject": bool(route.get("reject", False)),
    }


def _route_sort_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        item.get("routing_table", "main"),
        item.get("dst_prefix", ""),
        int(item.get("distance", 0)),
        item.get("gateway", ""),
        item.get("interface_name", ""),
        item.get("protocol", ""),
        0 if item.get("active") else 1,
        1 if item.get("disabled") else 0,
    )


def serialize_routes_deterministically(routes: Sequence[NormalizedRoute | Dict[str, Any]]) -> str:
    canonical_list = [canonicalize_route_for_snapshot(r) for r in routes]
    canonical_list.sort(key=_route_sort_key)
    return json.dumps(canonical_list, sort_keys=True, separators=(",", ":"))


@dataclass
class RouteSnapshotRecord:
    snapshot_id: str
    batch_id: str
    device_id: str
    device_identity: str
    collected_at: float
    ros_version: str
    routing_tables: List[str]
    routes_json: str
    route_count: int
    active_route_count: int
    completeness: str
    sha256_hash: str
    parser_version: str = PARSER_VERSION
    trigger_type: str = "collection"
    topology_snapshot_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_checksum(self) -> str:
        """
        Computes deterministic SHA-256 digest over canonical snapshot envelope.
        Orthogonal to completeness: partial or failed snapshots still have verifiable integrity.
        """
        envelope = {
            "device_id": self.device_id,
            "ros_version": self.ros_version,
            "parser_version": self.parser_version,
            "completeness": self.completeness,
            "routing_tables": sorted(self.routing_tables),
            "routes": json.loads(self.routes_json) if self.routes_json else [],
        }
        canonical_bytes = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()

    def verify_integrity(self) -> bool:
        return self.calculate_checksum() == self.sha256_hash

    @property
    def is_complete(self) -> bool:
        return self.completeness == RouteCompleteness.COMPLETE.value

    def get_routes(self) -> List[Dict[str, Any]]:
        if not self.routes_json:
            return []
        try:
            return json.loads(self.routes_json)
        except Exception:
            return []

    def to_dict(self, *, include_routes: bool = False) -> Dict[str, Any]:
        verified = self.verify_integrity()
        payload: Dict[str, Any] = {
            "snapshot_id": self.snapshot_id,
            "batch_id": self.batch_id,
            "device_id": self.device_id,
            "device_identity": self.device_identity,
            "topology_snapshot_id": self.topology_snapshot_id,
            "collected_at": self.collected_at,
            "ros_version": self.ros_version,
            "routing_tables": list(self.routing_tables),
            "route_count": self.route_count,
            "active_route_count": self.active_route_count,
            "completeness": self.completeness,
            "is_complete": self.is_complete,
            "sha256_hash": self.sha256_hash,
            "integrity_verified": verified,
            "integrity_status": "verified" if verified else "compromised",
            "parser_version": self.parser_version,
            "trigger_type": self.trigger_type,
            "metadata": dict(self.metadata),
        }
        if include_routes:
            payload["routes"] = self.get_routes()
        return payload


@dataclass
class RouteChangeRecord:
    change_id: Optional[int]
    from_snapshot_id: Optional[str]
    to_snapshot_id: str
    device_id: str
    detected_at: float
    change_type: str
    routing_table: str
    dst_prefix: str
    gateway_before: str = ""
    gateway_after: str = ""
    before_route: Optional[Dict[str, Any]] = None
    after_route: Optional[Dict[str, Any]] = None
    completeness_context: str = RouteCompleteness.COMPLETE.value
    confidence: float = 1.0
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "from_snapshot_id": self.from_snapshot_id,
            "to_snapshot_id": self.to_snapshot_id,
            "device_id": self.device_id,
            "detected_at": self.detected_at,
            "change_type": self.change_type,
            "semantic_domain": "ROUTE_HISTORY",
            "routing_table": self.routing_table,
            "dst_prefix": self.dst_prefix,
            "gateway_before": self.gateway_before,
            "gateway_after": self.gateway_after,
            "before_route": self.before_route,
            "after_route": self.after_route,
            "completeness_context": self.completeness_context,
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
            "metadata": dict(self.metadata),
        }


@dataclass
class RouteSnapshotDiffResult:
    base_snapshot_id: str
    target_snapshot_id: str
    device_id: str
    cross_device_warning: Optional[str]
    base_completeness: str
    target_completeness: str
    base_integrity_verified: bool
    target_integrity_verified: bool
    removal_suppression_active: bool
    suppression_reason: Optional[str]
    changes: List[RouteChangeRecord] = field(default_factory=list)
    unchanged_count: int = 0
    summary_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_snapshot_id": self.base_snapshot_id,
            "target_snapshot_id": self.target_snapshot_id,
            "device_id": self.device_id,
            "cross_device_warning": self.cross_device_warning,
            "base_completeness": self.base_completeness,
            "target_completeness": self.target_completeness,
            "base_integrity_verified": self.base_integrity_verified,
            "target_integrity_verified": self.target_integrity_verified,
            "removal_suppression_active": self.removal_suppression_active,
            "suppression_reason": self.suppression_reason,
            "unchanged_count": self.unchanged_count,
            "total_changes": len(self.changes),
            "summary_counts": dict(self.summary_counts),
            "changes": [c.to_dict() for c in self.changes],
        }


# ---------------------------------------------------------------------------
# Semantic Route Snapshot Diff Engine (Section 8.3 & 8.4)
# ---------------------------------------------------------------------------

def _classify_incomplete_reason(snap: RouteSnapshotRecord) -> str:
    meta = snap.metadata or {}
    status = str(meta.get("collection_status") or "").upper()
    errors = " ".join(str(e) for e in (meta.get("errors") or [])).lower()

    if snap.completeness == RouteCompleteness.UNREACHABLE.value or status in ("UNREACHABLE", "TIMEOUT"):
        return "DEVICE_UNREACHABLE"
    if "parser" in errors or meta.get("parser_failed"):
        return "PARSER_FAILURE"
    if meta.get("evidence_expired"):
        return "EVIDENCE_EXPIRED"
    if snap.completeness == RouteCompleteness.PARTIAL.value or status == "PARTIAL":
        return "COLLECTION_INCOMPLETE"
    if snap.completeness in (RouteCompleteness.FAILED.value, RouteCompleteness.CANCELLED.value):
        return f"COLLECTION_{snap.completeness}"
    return "ROUTE_TEMPORARILY_MISSING_OR_UNVERIFIED"


def _group_routes_by_table_prefix(routes: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in routes:
        key = (str(r.get("routing_table") or "main"), str(r.get("dst_prefix") or ""))
        grouped.setdefault(key, []).append(r)
    for k in grouped:
        grouped[k].sort(key=_route_sort_key)
    return grouped


def compare_route_snapshots_semantic(
    base: RouteSnapshotRecord,
    target: RouteSnapshotRecord,
    *,
    previously_removed_prefixes: Optional[Set[Tuple[str, str]]] = None,
) -> RouteSnapshotDiffResult:
    """
    Computes semantic route deltas between `base` and `target` snapshots with
    strict false-positive suppression when either snapshot is incomplete, unreachable,
    expired, or compromised.
    """
    base_verified = base.verify_integrity()
    target_verified = target.verify_integrity()

    cross_warning = None
    if base.device_id != target.device_id:
        cross_warning = (
            f"Comparing snapshots from different devices ('{base.device_id}' vs '{target.device_id}'); "
            "results represent cross-device table divergence rather than temporal transitions."
        )

    # False-positive protection (Section 8.4):
    # Never emit confirmed ROUTE_REMOVED if target collection is incomplete, failed, unreachable,
    # expired, or compromised!
    target_has_expired = bool((target.metadata or {}).get("evidence_expired"))
    target_parser_failed = bool((target.metadata or {}).get("parser_failed"))
    suppression_active = (
        not target.is_complete
        or not target_verified
        or not base_verified
        or target_has_expired
        or target_parser_failed
    )
    suppression_reason = _classify_incomplete_reason(target) if suppression_active else None
    if not target_verified or not base_verified:
        suppression_reason = "SNAPSHOT_INTEGRITY_COMPROMISED"

    base_routes = base.get_routes()
    target_routes = target.get_routes()
    base_groups = _group_routes_by_table_prefix(base_routes)
    target_groups = _group_routes_by_table_prefix(target_routes)

    changes: List[RouteChangeRecord] = []
    unchanged_count = 0

    # Detect VRF / routing_table moves first (prefix removed from table A and added to table B)
    removed_keys = [k for k in base_groups if k not in target_groups]
    added_keys = [k for k in target_groups if k not in base_groups]

    moved_removed: Set[Tuple[str, str]] = set()
    moved_added: Set[Tuple[str, str]] = set()

    if not suppression_active:
        for rk in removed_keys:
            r_tbl, r_pfx = rk
            for ak in added_keys:
                a_tbl, a_pfx = ak
                if ak in moved_added:
                    continue
                if r_pfx == a_pfx and r_tbl != a_tbl:
                    b_primary = base_groups[rk][0]
                    t_primary = target_groups[ak][0]
                    moved_removed.add(rk)
                    moved_added.add(ak)
                    changes.append(
                        RouteChangeRecord(
                            change_id=None,
                            from_snapshot_id=base.snapshot_id,
                            to_snapshot_id=target.snapshot_id,
                            device_id=target.device_id,
                            detected_at=target.collected_at,
                            change_type=RouteChangeType.ROUTING_TABLE_CHANGED.value,
                            routing_table=a_tbl,
                            dst_prefix=a_pfx,
                            gateway_before=str(b_primary.get("gateway") or ""),
                            gateway_after=str(t_primary.get("gateway") or ""),
                            before_route=b_primary,
                            after_route=t_primary,
                            completeness_context=target.completeness,
                            confidence=0.92,
                            summary=f"Prefix {a_pfx} moved from routing table '{r_tbl}' to '{a_tbl}'.",
                            metadata={"from_table": r_tbl, "to_table": a_tbl},
                        )
                    )
                    break

    # Process remaining removed prefixes
    for rk in removed_keys:
        if rk in moved_removed:
            continue
        r_tbl, r_pfx = rk
        for b_route in base_groups[rk]:
            if suppression_active:
                changes.append(
                    RouteChangeRecord(
                        change_id=None,
                        from_snapshot_id=base.snapshot_id,
                        to_snapshot_id=target.snapshot_id,
                        device_id=target.device_id,
                        detected_at=target.collected_at,
                        change_type=RouteChangeType.ROUTE_STATE_UNKNOWN.value,
                        routing_table=r_tbl,
                        dst_prefix=r_pfx,
                        gateway_before=str(b_route.get("gateway") or ""),
                        gateway_after="",
                        before_route=b_route,
                        after_route=None,
                        completeness_context=target.completeness,
                        confidence=0.30,
                        summary=(
                            f"Route {r_pfx} (table '{r_tbl}') not observed in incomplete/unverified "
                            f"snapshot ({suppression_reason}); confirmed removal suppressed."
                        ),
                        metadata={
                            "suppressed_confirmed_removal": True,
                            "reason": suppression_reason,
                        },
                    )
                )
            else:
                changes.append(
                    RouteChangeRecord(
                        change_id=None,
                        from_snapshot_id=base.snapshot_id,
                        to_snapshot_id=target.snapshot_id,
                        device_id=target.device_id,
                        detected_at=target.collected_at,
                        change_type=RouteChangeType.ROUTE_REMOVED.value,
                        routing_table=r_tbl,
                        dst_prefix=r_pfx,
                        gateway_before=str(b_route.get("gateway") or ""),
                        gateway_after="",
                        before_route=b_route,
                        after_route=None,
                        completeness_context=target.completeness,
                        confidence=0.98,
                        summary=f"Confirmed removal of {r_pfx} via {b_route.get('gateway')} from table '{r_tbl}'.",
                    )
                )

    # Process added / reappeared prefixes
    prev_rem = previously_removed_prefixes or set()
    for ak in added_keys:
        if ak in moved_added:
            continue
        a_tbl, a_pfx = ak
        is_reappeared = (a_tbl, a_pfx) in prev_rem
        ctype = (
            RouteChangeType.ROUTE_REAPPEARED.value
            if is_reappeared
            else RouteChangeType.ROUTE_ADDED.value
        )
        for t_route in target_groups[ak]:
            changes.append(
                RouteChangeRecord(
                    change_id=None,
                    from_snapshot_id=base.snapshot_id,
                    to_snapshot_id=target.snapshot_id,
                    device_id=target.device_id,
                    detected_at=target.collected_at,
                    change_type=ctype,
                    routing_table=a_tbl,
                    dst_prefix=a_pfx,
                    gateway_before="",
                    gateway_after=str(t_route.get("gateway") or ""),
                    before_route=None,
                    after_route=t_route,
                    completeness_context=target.completeness,
                    confidence=0.95 if target.is_complete else 0.75,
                    summary=(
                        f"Previously removed route {a_pfx} reappeared via {t_route.get('gateway')} in '{a_tbl}'."
                        if is_reappeared
                        else f"Route {a_pfx} added via {t_route.get('gateway')} in table '{a_tbl}'."
                    ),
                )
            )

    # Process prefixes present in both Base and Target
    common_keys = [k for k in base_groups if k in target_groups]
    for ck in common_keys:
        c_tbl, c_pfx = ck
        b_list = base_groups[ck]
        t_list = target_groups[ck]

        if b_list == t_list:
            unchanged_count += len(t_list)
            continue

        # Collect active ECMP gateway sets across the prefix group
        b_ecmp_gws = sorted({
            g for r in b_list if r.get("active") and not r.get("disabled")
            for g in (r.get("gateways") or ([r.get("gateway")] if r.get("gateway") else [])) if g
        })
        t_ecmp_gws = sorted({
            g for r in t_list if r.get("active") and not r.get("disabled")
            for g in (r.get("gateways") or ([r.get("gateway")] if r.get("gateway") else [])) if g
        })

        if (len(b_ecmp_gws) > 1 or len(t_ecmp_gws) > 1) and b_ecmp_gws != t_ecmp_gws:
            changes.append(
                RouteChangeRecord(
                    change_id=None,
                    from_snapshot_id=base.snapshot_id,
                    to_snapshot_id=target.snapshot_id,
                    device_id=target.device_id,
                    detected_at=target.collected_at,
                    change_type=RouteChangeType.ECMP_CHANGED.value,
                    routing_table=c_tbl,
                    dst_prefix=c_pfx,
                    gateway_before=",".join(b_ecmp_gws),
                    gateway_after=",".join(t_ecmp_gws),
                    before_route=b_list[0],
                    after_route=t_list[0],
                    completeness_context=target.completeness,
                    confidence=0.95 if target.is_complete else 0.70,
                    summary=(
                        f"ECMP next-hop set for {c_pfx} changed from [{', '.join(b_ecmp_gws)}] "
                        f"to [{', '.join(t_ecmp_gws)}]."
                    ),
                )
            )
            continue

        # Compare primary candidate attributes
        b_prim = b_list[0]
        t_prim = t_list[0]
        gw_b = str(b_prim.get("gateway") or "")
        gw_t = str(t_prim.get("gateway") or "")

        if bool(b_prim.get("disabled")) != bool(t_prim.get("disabled")):
            ctype = (
                RouteChangeType.ROUTE_DISABLED.value
                if t_prim.get("disabled")
                else RouteChangeType.ROUTE_ENABLED.value
            )
            summary = f"Route {c_pfx} ({gw_t}) {'disabled' if t_prim.get('disabled') else 'enabled'}."
        elif bool(b_prim.get("active")) != bool(t_prim.get("active")):
            ctype = (
                RouteChangeType.ROUTE_ACTIVATED.value
                if t_prim.get("active")
                else RouteChangeType.ROUTE_DEACTIVATED.value
            )
            summary = f"Route {c_pfx} ({gw_t}) {'activated' if t_prim.get('active') else 'deactivated'}."
        elif gw_b != gw_t:
            ctype = RouteChangeType.GATEWAY_CHANGED.value
            summary = f"Gateway for {c_pfx} changed from '{gw_b}' to '{gw_t}'."
        elif str(b_prim.get("immediate_gw") or "") != str(t_prim.get("immediate_gw") or ""):
            ctype = RouteChangeType.NEXT_HOP_CHANGED.value
            summary = (
                f"Resolved immediate next-hop for {c_pfx} changed from "
                f"'{b_prim.get('immediate_gw')}' to '{t_prim.get('immediate_gw')}'."
            )
        elif int(b_prim.get("distance") or 0) != int(t_prim.get("distance") or 0):
            ctype = RouteChangeType.DISTANCE_CHANGED.value
            summary = (
                f"Administrative distance for {c_pfx} changed from "
                f"{b_prim.get('distance')} to {t_prim.get('distance')}."
            )
        elif b_prim.get("metric") != t_prim.get("metric"):
            ctype = RouteChangeType.METRIC_CHANGED.value
            summary = f"Metric for {c_pfx} changed from {b_prim.get('metric')} to {t_prim.get('metric')}."
        else:
            ctype = RouteChangeType.ROUTE_MODIFIED.value
            summary = f"Route attributes modified for {c_pfx} in table '{c_tbl}'."

        changes.append(
            RouteChangeRecord(
                change_id=None,
                from_snapshot_id=base.snapshot_id,
                to_snapshot_id=target.snapshot_id,
                device_id=target.device_id,
                detected_at=target.collected_at,
                change_type=ctype,
                routing_table=c_tbl,
                dst_prefix=c_pfx,
                gateway_before=gw_b,
                gateway_after=gw_t,
                before_route=b_prim,
                after_route=t_prim,
                completeness_context=target.completeness,
                confidence=0.95 if target.is_complete else 0.72,
                summary=summary,
            )
        )

    counts: Dict[str, int] = {}
    for chg in changes:
        counts[chg.change_type] = counts.get(chg.change_type, 0) + 1

    return RouteSnapshotDiffResult(
        base_snapshot_id=base.snapshot_id,
        target_snapshot_id=target.snapshot_id,
        device_id=target.device_id,
        cross_device_warning=cross_warning,
        base_completeness=base.completeness,
        target_completeness=target.completeness,
        base_integrity_verified=base_verified,
        target_integrity_verified=target_verified,
        removal_suppression_active=suppression_active,
        suppression_reason=suppression_reason,
        changes=changes,
        unchanged_count=unchanged_count,
        summary_counts=counts,
    )


# ---------------------------------------------------------------------------
# Additive SQLite Store & Historical Analytics Engine (Sections 8.1–8.6)
# ---------------------------------------------------------------------------

class RouteHistoryStore:
    """
    Thread-safe, WAL-governed persistence service for immutable route snapshots
    and semantic route change records inside `topology.db` (or test SQLite path).
    """

    def __init__(self, db_path: Path | str = DEFAULT_TOPOLOGY_DB_PATH) -> None:
        self.db_path = Path(db_path).resolve()
        self._init_lock = threading.Lock()
        self._initialized = False
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            def _migrate() -> None:
                with topology_transaction(self.db_path, write=True) as conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS route_snapshots (
                            snapshot_id TEXT PRIMARY KEY,
                            batch_id TEXT NOT NULL,
                            device_id TEXT NOT NULL,
                            device_identity TEXT DEFAULT '',
                            topology_snapshot_id TEXT,
                            collected_at REAL NOT NULL,
                            ros_version TEXT DEFAULT '',
                            routing_tables_json TEXT NOT NULL DEFAULT '["main"]',
                            routes_json TEXT NOT NULL DEFAULT '[]',
                            route_count INTEGER NOT NULL DEFAULT 0,
                            active_route_count INTEGER NOT NULL DEFAULT 0,
                            completeness TEXT NOT NULL DEFAULT 'COMPLETE',
                            sha256_hash TEXT NOT NULL,
                            parser_version TEXT NOT NULL DEFAULT '1.0.0',
                            trigger_type TEXT NOT NULL DEFAULT 'collection',
                            metadata_json TEXT NOT NULL DEFAULT '{}'
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE TRIGGER IF NOT EXISTS trg_route_snapshots_no_update
                        BEFORE UPDATE ON route_snapshots
                        BEGIN
                            SELECT RAISE(ABORT, 'route_snapshots records are immutable');
                        END
                        """
                    )
                    conn.execute(
                        """
                        CREATE TRIGGER IF NOT EXISTS trg_route_snapshots_no_delete
                        BEFORE DELETE ON route_snapshots
                        BEGIN
                            SELECT RAISE(ABORT, 'route_snapshots records are immutable');
                        END
                        """
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS route_changes (
                            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            from_snapshot_id TEXT,
                            to_snapshot_id TEXT NOT NULL,
                            device_id TEXT NOT NULL,
                            detected_at REAL NOT NULL,
                            change_type TEXT NOT NULL,
                            routing_table TEXT NOT NULL DEFAULT 'main',
                            dst_prefix TEXT NOT NULL DEFAULT '',
                            gateway_before TEXT DEFAULT '',
                            gateway_after TEXT DEFAULT '',
                            before_json TEXT,
                            after_json TEXT,
                            completeness_context TEXT NOT NULL DEFAULT 'COMPLETE',
                            confidence REAL NOT NULL DEFAULT 1.0,
                            summary TEXT DEFAULT '',
                            metadata_json TEXT NOT NULL DEFAULT '{}'
                        )
                        """
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_route_snapshots_device_time ON route_snapshots(device_id, collected_at DESC)"
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_route_snapshots_batch ON route_snapshots(batch_id)"
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_route_snapshots_topo_snap ON route_snapshots(topology_snapshot_id)"
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_route_changes_device_time ON route_changes(device_id, detected_at DESC)"
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_route_changes_to_snap ON route_changes(to_snapshot_id)"
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_route_changes_type ON route_changes(change_type)"
                    )

            execute_with_retry(_migrate, operation_name="route_history_schema_init")
            self._initialized = True

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> RouteSnapshotRecord:
        try:
            tables = json.loads(row["routing_tables_json"]) if row["routing_tables_json"] else ["main"]
        except Exception:
            tables = ["main"]
        try:
            meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        except Exception:
            meta = {}
        return RouteSnapshotRecord(
            snapshot_id=row["snapshot_id"],
            batch_id=row["batch_id"],
            device_id=row["device_id"],
            device_identity=row["device_identity"] or "",
            topology_snapshot_id=row["topology_snapshot_id"],
            collected_at=float(row["collected_at"]),
            ros_version=row["ros_version"] or "",
            routing_tables=tables,
            routes_json=row["routes_json"] or "[]",
            route_count=int(row["route_count"]),
            active_route_count=int(row["active_route_count"]),
            completeness=row["completeness"] or RouteCompleteness.COMPLETE.value,
            sha256_hash=row["sha256_hash"],
            parser_version=row["parser_version"] or PARSER_VERSION,
            trigger_type=row["trigger_type"] or "collection",
            metadata=meta,
        )

    @staticmethod
    def _row_to_change(row: sqlite3.Row) -> RouteChangeRecord:
        try:
            b_json = json.loads(row["before_json"]) if row["before_json"] else None
        except Exception:
            b_json = None
        try:
            a_json = json.loads(row["after_json"]) if row["after_json"] else None
        except Exception:
            a_json = None
        try:
            meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        except Exception:
            meta = {}
        return RouteChangeRecord(
            change_id=int(row["change_id"]),
            from_snapshot_id=row["from_snapshot_id"],
            to_snapshot_id=row["to_snapshot_id"],
            device_id=row["device_id"],
            detected_at=float(row["detected_at"]),
            change_type=row["change_type"],
            routing_table=row["routing_table"] or "main",
            dst_prefix=row["dst_prefix"] or "",
            gateway_before=row["gateway_before"] or "",
            gateway_after=row["gateway_after"] or "",
            before_route=b_json,
            after_route=a_json,
            completeness_context=row["completeness_context"] or RouteCompleteness.COMPLETE.value,
            confidence=float(row["confidence"]),
            summary=row["summary"] or "",
            metadata=meta,
        )

    def create_snapshot_from_collection(
        self,
        result: RouteCollectionResult,
        *,
        batch_id: Optional[str] = None,
        topology_snapshot_id: Optional[str] = None,
        trigger_type: str = "collection",
        description: str = "",
        deduplicate_by_evidence_id: bool = True,
        skip_if_unchanged: bool = False,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[RouteSnapshotRecord, List[RouteChangeRecord]]:
        """
        Persists an immutable RouteSnapshotRecord for `result` and records semantic
        `RouteChangeRecord` entries against the device's previous snapshot.
        Serialization and diff computation happen BEFORE acquiring the SQLite write lock
        to guarantee sub-millisecond write transaction duration!
        """
        self._ensure_schema()

        # Prepare deterministic JSON outside DB write lock
        routes_json = serialize_routes_deterministically(result.routes)
        tables = sorted(result.routing_tables or {r.routing_table or "main" for r in result.routes} or {"main"})
        parser_failed = bool(
            result.status == RouteCollectionStatus.FAILED.value
            and any("parse" in e.lower() or "malformed" in e.lower() for e in result.errors)
        )
        if (
            result.parser_report
            and (
                getattr(result.parser_report, "status", "") == "ERROR"
                or getattr(result.parser_report, "malformed_blocks", 0) > 0
            )
            and not result.routes
        ):
            parser_failed = True

        meta: Dict[str, Any] = {
            "evidence_id": result.evidence_id,
            "collection_status": result.status,
            "source_command": result.source_command,
            "duration_ms": round(result.duration_ms, 2),
            "errors": list(result.errors),
            "warnings": list(result.warnings),
            "parser_failed": parser_failed,
            "description": description,
        }
        if extra_metadata:
            meta.update(extra_metadata)

        b_id = batch_id or f"rbatch_{int(result.collected_at)}_{uuid.uuid4().hex[:6]}"
        snap_id = f"rsnap_{result.device_id}_{int(result.collected_at * 1000)}_{uuid.uuid4().hex[:6]}"

        candidate = RouteSnapshotRecord(
            snapshot_id=snap_id,
            batch_id=b_id,
            device_id=result.device_id,
            device_identity=result.device_identity,
            topology_snapshot_id=topology_snapshot_id,
            collected_at=result.collected_at,
            ros_version=result.router_os_version,
            routing_tables=tables,
            routes_json=routes_json,
            route_count=result.route_count,
            active_route_count=result.active_route_count,
            completeness=result.completeness,
            sha256_hash="",
            parser_version=result.parser_version or PARSER_VERSION,
            trigger_type=trigger_type,
            metadata=meta,
        )
        candidate.sha256_hash = candidate.calculate_checksum()

        def _persist() -> Tuple[RouteSnapshotRecord, List[RouteChangeRecord], bool]:
            with topology_transaction(self.db_path, write=True) as conn:
                # 1. Check immediate previous snapshot for duplicate evidence_id / unchanged hash
                prev_any_row = conn.execute(
                    """
                    SELECT * FROM route_snapshots
                    WHERE device_id = ?
                    ORDER BY collected_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (result.device_id,),
                ).fetchone()

                prev_any_snap = self._row_to_snapshot(prev_any_row) if prev_any_row else None
                if prev_any_snap is not None:
                    prev_ev_id = (prev_any_snap.metadata or {}).get("evidence_id")
                    if deduplicate_by_evidence_id and result.evidence_id and prev_ev_id == result.evidence_id:
                        return prev_any_snap, [], True
                    if (
                        skip_if_unchanged
                        and prev_any_snap.sha256_hash == candidate.sha256_hash
                        and prev_any_snap.completeness == candidate.completeness
                    ):
                        return prev_any_snap, [], True

                # Compare deltas against the last COMPLETE authoritative baseline snapshot
                # (prevents an intermediate UNREACHABLE/FAILED empty snapshot from causing
                # 100% false ROUTE_ADDED churn when the device recovers!).
                prev_complete_row = conn.execute(
                    """
                    SELECT * FROM route_snapshots
                    WHERE device_id = ? AND completeness = ?
                    ORDER BY collected_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (result.device_id, RouteCompleteness.COMPLETE.value),
                ).fetchone()
                prev_snap = (
                    self._row_to_snapshot(prev_complete_row)
                    if prev_complete_row is not None
                    else prev_any_snap
                )

                # 2. Query previously removed prefixes for ROUTE_REAPPEARED classification
                removed_rows = conn.execute(
                    """
                    SELECT DISTINCT routing_table, dst_prefix
                    FROM route_changes
                    WHERE device_id = ? AND change_type = ?
                    """,
                    (result.device_id, RouteChangeType.ROUTE_REMOVED.value),
                ).fetchall()
                prev_removed = {(r["routing_table"], r["dst_prefix"]) for r in removed_rows}

                # 3. Insert immutable snapshot
                conn.execute(
                    """
                    INSERT INTO route_snapshots (
                        snapshot_id, batch_id, device_id, device_identity,
                        topology_snapshot_id, collected_at, ros_version,
                        routing_tables_json, routes_json, route_count,
                        active_route_count, completeness, sha256_hash,
                        parser_version, trigger_type, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.snapshot_id,
                        candidate.batch_id,
                        candidate.device_id,
                        candidate.device_identity,
                        candidate.topology_snapshot_id,
                        candidate.collected_at,
                        candidate.ros_version,
                        json.dumps(candidate.routing_tables),
                        candidate.routes_json,
                        candidate.route_count,
                        candidate.active_route_count,
                        candidate.completeness,
                        candidate.sha256_hash,
                        candidate.parser_version,
                        candidate.trigger_type,
                        json.dumps(candidate.metadata, sort_keys=True),
                    ),
                )

                # 4. Compute and persist delta changes if previous snapshot exists
                persisted_changes: List[RouteChangeRecord] = []
                if prev_snap is not None:
                    diff = compare_route_snapshots_semantic(
                        prev_snap,
                        candidate,
                        previously_removed_prefixes=prev_removed,
                    )
                    for chg in diff.changes:
                        cur = conn.execute(
                            """
                            INSERT INTO route_changes (
                                from_snapshot_id, to_snapshot_id, device_id,
                                detected_at, change_type, routing_table, dst_prefix,
                                gateway_before, gateway_after, before_json, after_json,
                                completeness_context, confidence, summary, metadata_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                chg.from_snapshot_id,
                                chg.to_snapshot_id,
                                chg.device_id,
                                chg.detected_at,
                                chg.change_type,
                                chg.routing_table,
                                chg.dst_prefix,
                                chg.gateway_before,
                                chg.gateway_after,
                                json.dumps(chg.before_route, sort_keys=True) if chg.before_route else None,
                                json.dumps(chg.after_route, sort_keys=True) if chg.after_route else None,
                                chg.completeness_context,
                                chg.confidence,
                                chg.summary,
                                json.dumps(chg.metadata, sort_keys=True),
                            ),
                        )
                        chg.change_id = cur.lastrowid
                        persisted_changes.append(chg)

                return candidate, persisted_changes, False

        snap_rec, changes_out, _was_dedup = execute_with_retry(
            _persist, operation_name="create_route_snapshot"
        )
        # Note: Event publication (if subscribed in future) strictly happens OUTSIDE the write lock here.
        return snap_rec, changes_out

    def create_multi_device_snapshots(
        self,
        collections: Dict[str, RouteCollectionResult],
        *,
        topology_snapshot_id: Optional[str] = None,
        trigger_type: str = "multi_collection",
        description: str = "",
        deduplicate_by_evidence_id: bool = True,
    ) -> Dict[str, Any]:
        batch_id = f"rbatch_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        created_snapshots: List[RouteSnapshotRecord] = []
        created_changes: List[RouteChangeRecord] = []

        for dev_id in sorted(collections.keys()):
            snap, chgs = self.create_snapshot_from_collection(
                collections[dev_id],
                batch_id=batch_id,
                topology_snapshot_id=topology_snapshot_id,
                trigger_type=trigger_type,
                description=description,
                deduplicate_by_evidence_id=deduplicate_by_evidence_id,
            )
            created_snapshots.append(snap)
            created_changes.extend(chgs)

        return {
            "batch_id": batch_id,
            "snapshots_count": len(created_snapshots),
            "changes_count": len(created_changes),
            "snapshots": [s.to_dict(include_routes=False) for s in created_snapshots],
            "changes": [c.to_dict() for c in created_changes],
        }

    def get_snapshot(self, snapshot_id: str) -> Optional[RouteSnapshotRecord]:
        self._ensure_schema()
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                "SELECT * FROM route_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            return self._row_to_snapshot(row) if row else None

    def list_snapshots(
        self,
        *,
        device_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        trigger_type: Optional[str] = None,
        completeness: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[RouteSnapshotRecord], int]:
        self._ensure_schema()
        safe_limit = max(1, min(int(limit), MAX_QUERY_LIMIT))
        safe_offset = max(0, int(offset))

        clauses: List[str] = []
        params: List[Any] = []
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if trigger_type:
            clauses.append("trigger_type = ?")
            params.append(trigger_type)
        if completeness:
            clauses.append("completeness = ?")
            params.append(completeness.upper())

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with topology_transaction(self.db_path, write=False) as conn:
            total = int(
                conn.execute(f"SELECT COUNT(*) FROM route_snapshots {where_sql}", params).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT * FROM route_snapshots
                {where_sql}
                ORDER BY collected_at DESC, rowid DESC
                LIMIT ? OFFSET ?
                """,
                [*params, safe_limit, safe_offset],
            ).fetchall()
            return [self._row_to_snapshot(r) for r in rows], total

    def verify_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        snap = self.get_snapshot(snapshot_id)
        if snap is None:
            return None
        computed = snap.calculate_checksum()
        verified = computed == snap.sha256_hash
        return {
            "snapshot_id": snap.snapshot_id,
            "device_id": snap.device_id,
            "verified": verified,
            "integrity_status": "verified" if verified else "compromised",
            "sha256_hash": snap.sha256_hash,
            "computed_hash": computed,
            "completeness": snap.completeness,
            "is_complete": snap.is_complete,
            "orthogonality_note": (
                "SHA-256 integrity verifies record immutability only; "
                "collection completeness is reported independently."
            ),
        }

    def compare_snapshots(self, base_id: str, target_id: str) -> RouteSnapshotDiffResult:
        base = self.get_snapshot(base_id)
        if base is None:
            raise KeyError(f"Base route snapshot '{base_id}' not found.")
        target = self.get_snapshot(target_id)
        if target is None:
            raise KeyError(f"Target route snapshot '{target_id}' not found.")

        with topology_transaction(self.db_path, write=False) as conn:
            rem_rows = conn.execute(
                """
                SELECT DISTINCT routing_table, dst_prefix
                FROM route_changes
                WHERE device_id = ? AND detected_at <= ? AND change_type = ?
                """,
                (target.device_id, base.collected_at, RouteChangeType.ROUTE_REMOVED.value),
            ).fetchall()
            prev_rem = {(r["routing_table"], r["dst_prefix"]) for r in rem_rows}

        return compare_route_snapshots_semantic(
            base, target, previously_removed_prefixes=prev_rem
        )

    def list_changes(
        self,
        *,
        device_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        change_type: Optional[str] = None,
        dst_prefix: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[RouteChangeRecord], int]:
        self._ensure_schema()
        safe_limit = max(1, min(int(limit), MAX_QUERY_LIMIT))
        safe_offset = max(0, int(offset))

        clauses: List[str] = []
        params: List[Any] = []
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if snapshot_id:
            clauses.append("(to_snapshot_id = ? OR from_snapshot_id = ?)")
            params.extend([snapshot_id, snapshot_id])
        if change_type:
            clauses.append("change_type = ?")
            params.append(change_type.upper())
        if dst_prefix:
            clauses.append("dst_prefix = ?")
            params.append(dst_prefix)
        if start_time is not None:
            clauses.append("detected_at >= ?")
            params.append(float(start_time))
        if end_time is not None:
            clauses.append("detected_at <= ?")
            params.append(float(end_time))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with topology_transaction(self.db_path, write=False) as conn:
            total = int(
                conn.execute(f"SELECT COUNT(*) FROM route_changes {where_sql}", params).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT * FROM route_changes
                {where_sql}
                ORDER BY detected_at DESC, change_id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, safe_limit, safe_offset],
            ).fetchall()
            return [self._row_to_change(r) for r in rows], total

    def get_change(self, change_id: int) -> Optional[RouteChangeRecord]:
        self._ensure_schema()
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                "SELECT * FROM route_changes WHERE change_id = ?",
                (int(change_id),),
            ).fetchone()
            return self._row_to_change(row) if row else None

    def get_historical_analytics(
        self,
        *,
        device_id: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        correlation_window_sec: float = DEFAULT_CORRELATION_WINDOW_SEC,
        limit: int = MAX_QUERY_LIMIT,
    ) -> Dict[str, Any]:
        """
        Computes historical route analytics (Section 8.5):
        - Additions/removals over time
        - Default route, gateway, activation, ECMP, and VRF table changes
        - Route churn & stability score
        - Repeated route flapping (>= 3 transitions on same device/table/prefix)
        - Temporal correlation with `topology_changes` and `nms_events`
          (strictly labeled as temporal correlation, NOT proven causation).
        """
        changes, total_changes = self.list_changes(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=min(limit, MAX_QUERY_LIMIT),
            offset=0,
        )
        snaps, total_snaps = self.list_snapshots(
            device_id=device_id,
            limit=min(limit, MAX_QUERY_LIMIT),
            offset=0,
        )

        by_type: Dict[str, int] = {}
        default_route_changes: List[Dict[str, Any]] = []
        gateway_changes: List[Dict[str, Any]] = []
        activation_changes: List[Dict[str, Any]] = []
        ecmp_changes: List[Dict[str, Any]] = []
        table_changes: List[Dict[str, Any]] = []
        prefix_transitions: Dict[Tuple[str, str, str], List[RouteChangeRecord]] = {}

        for chg in changes:
            by_type[chg.change_type] = by_type.get(chg.change_type, 0) + 1
            cd = chg.to_dict()

            if chg.dst_prefix == "0.0.0.0/0":
                default_route_changes.append(cd)
            if chg.change_type in (
                RouteChangeType.GATEWAY_CHANGED.value,
                RouteChangeType.NEXT_HOP_CHANGED.value,
            ):
                gateway_changes.append(cd)
            if chg.change_type in (
                RouteChangeType.ROUTE_ACTIVATED.value,
                RouteChangeType.ROUTE_DEACTIVATED.value,
                RouteChangeType.ROUTE_ENABLED.value,
                RouteChangeType.ROUTE_DISABLED.value,
            ):
                activation_changes.append(cd)
            if chg.change_type == RouteChangeType.ECMP_CHANGED.value:
                ecmp_changes.append(cd)
            if chg.change_type == RouteChangeType.ROUTING_TABLE_CHANGED.value:
                table_changes.append(cd)

            # Exclude unverified ROUTE_STATE_UNKNOWN from flapping counts!
            if chg.change_type != RouteChangeType.ROUTE_STATE_UNKNOWN.value:
                prefix_transitions.setdefault(
                    (chg.device_id, chg.routing_table, chg.dst_prefix), []
                ).append(chg)

        flapping_prefixes: List[Dict[str, Any]] = []
        for (d_id, tbl, pfx), seq in prefix_transitions.items():
            if len(seq) >= 3:
                flapping_prefixes.append({
                    "device_id": d_id,
                    "routing_table": tbl,
                    "dst_prefix": pfx,
                    "transition_count": len(seq),
                    "change_types": [s.change_type for s in seq],
                    "first_seen": min(s.detected_at for s in seq),
                    "last_seen": max(s.detected_at for s in seq),
                })

        confirmed_mutations = sum(
            cnt for ct, cnt in by_type.items() if ct != RouteChangeType.ROUTE_STATE_UNKNOWN.value
        )
        churn_per_snapshot = (
            round(confirmed_mutations / max(1, len(snaps)), 3) if snaps else 0.0
        )
        # Stability score in [0.0, 1.0]: penalizes churn and flapping
        raw_penalty = min(1.0, (churn_per_snapshot * 0.15) + (len(flapping_prefixes) * 0.20))
        stability_score = round(max(0.0, 1.0 - raw_penalty), 3)

        # Temporal correlation (NOT causation!) with topology_changes & NMS events
        correlated_events = self._correlate_with_topology_and_nms(
            changes, window_sec=correlation_window_sec
        )

        return {
            "device_id": device_id,
            "total_snapshots": total_snaps,
            "total_changes_in_window": total_changes,
            "change_counts_by_type": by_type,
            "additions_count": by_type.get(RouteChangeType.ROUTE_ADDED.value, 0)
            + by_type.get(RouteChangeType.ROUTE_REAPPEARED.value, 0),
            "removals_count": by_type.get(RouteChangeType.ROUTE_REMOVED.value, 0),
            "suppressed_unknown_count": by_type.get(RouteChangeType.ROUTE_STATE_UNKNOWN.value, 0),
            "default_route_changes": default_route_changes[:50],
            "gateway_changes": gateway_changes[:50],
            "activation_changes": activation_changes[:50],
            "ecmp_changes": ecmp_changes[:50],
            "routing_table_changes": table_changes[:50],
            "flapping_prefixes": flapping_prefixes,
            "route_churn_per_snapshot": churn_per_snapshot,
            "route_stability_score": stability_score,
            "correlated_topology_and_nms_events": correlated_events,
            "retention_policy": dict(RETENTION_POLICY),
            "epistemic_notice": (
                "Temporal correlations with topology and NMS events indicate co-occurrence within "
                f"±{correlation_window_sec:.0f}s and do NOT prove causal direction without dependency verification."
            ),
        }

    def _correlate_with_topology_and_nms(
        self,
        route_changes: Sequence[RouteChangeRecord],
        *,
        window_sec: float = DEFAULT_CORRELATION_WINDOW_SEC,
    ) -> List[Dict[str, Any]]:
        if not route_changes:
            return []

        min_ts = min(c.detected_at for c in route_changes) - window_sec
        max_ts = max(c.detected_at for c in route_changes) + window_sec
        correlations: List[Dict[str, Any]] = []

        with topology_transaction(self.db_path, write=False) as conn:
            tables = {
                r["name"]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }

            topo_rows = []
            if "topology_changes" in tables:
                topo_rows = conn.execute(
                    """
                    SELECT id, change_type, entity_id, change_reason, detected_at
                    FROM topology_changes
                    WHERE detected_at >= ? AND detected_at <= ?
                    ORDER BY detected_at DESC
                    LIMIT 100
                    """,
                    (min_ts, max_ts),
                ).fetchall()

            nms_rows = []
            if "nms_alerts" in tables:
                try:
                    nms_rows = conn.execute(
                        """
                        SELECT id, device_id, alert_type, severity, message, created_at
                        FROM nms_alerts
                        WHERE created_at >= ? AND created_at <= ?
                        ORDER BY created_at DESC
                        LIMIT 100
                        """,
                        (min_ts, max_ts),
                    ).fetchall()
                except Exception:
                    nms_rows = []

        for rchg in route_changes[:50]:
            for tr in topo_rows:
                delta = abs(float(tr["detected_at"]) - rchg.detected_at)
                if delta <= window_sec:
                    correlations.append({
                        "route_change_id": rchg.change_id,
                        "device_id": rchg.device_id,
                        "dst_prefix": rchg.dst_prefix,
                        "route_change_type": rchg.change_type,
                        "external_domain": "TOPOLOGY_CHANGE",
                        "external_event_id": tr["id"],
                        "external_type": tr["change_type"],
                        "external_entity_id": tr["entity_id"],
                        "external_reason": tr["change_reason"],
                        "time_delta_sec": round(delta, 3),
                        "relationship": "TEMPORAL_CORRELATION_NOT_PROVEN_CAUSATION",
                    })
            for nr in nms_rows:
                delta = abs(float(nr["created_at"]) - rchg.detected_at)
                if delta <= window_sec:
                    correlations.append({
                        "route_change_id": rchg.change_id,
                        "device_id": rchg.device_id,
                        "dst_prefix": rchg.dst_prefix,
                        "route_change_type": rchg.change_type,
                        "external_domain": "NMS_ALERT",
                        "external_event_id": nr["id"],
                        "external_type": nr["alert_type"],
                        "external_entity_id": nr["device_id"],
                        "external_reason": nr["message"],
                        "time_delta_sec": round(delta, 3),
                        "relationship": "TEMPORAL_CORRELATION_NOT_PROVEN_CAUSATION",
                    })

        return correlations[:100]


_GLOBAL_ROUTE_HISTORY_STORE: Optional[RouteHistoryStore] = None
_STORE_LOCK = threading.Lock()


def get_route_history_store(db_path: Optional[Path | str] = None) -> RouteHistoryStore:
    global _GLOBAL_ROUTE_HISTORY_STORE
    if db_path is not None:
        return RouteHistoryStore(db_path=db_path)
    with _STORE_LOCK:
        if _GLOBAL_ROUTE_HISTORY_STORE is None:
            _GLOBAL_ROUTE_HISTORY_STORE = RouteHistoryStore(DEFAULT_TOPOLOGY_DB_PATH)
        return _GLOBAL_ROUTE_HISTORY_STORE
