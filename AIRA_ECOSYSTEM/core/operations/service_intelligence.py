"""
AIRA OS — Service Dependency Intelligence Engine (Networking VII / WP 7.3).

Maps business services and application endpoints down to L3/L2 network infrastructure
(devices, interfaces, transit paths, and VLANs). Evaluates service health, redundancy tiers,
and downstream business impact.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.network_intelligence.intelligence_models import (
    GraphEntityType,
    GraphRelationshipType,
    KnowledgeEdge,
    KnowledgeNode,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.operations.db import ensure_operational_schema
from core.operations.models import (
    BusinessServiceRecord,
    ServiceCriticality,
    ServiceEndpointRecord,
    ServiceHealthStatus,
)
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.operations.service_intelligence")


class ServiceIntelligenceEngine:
    """Manages business service catalog, endpoints, and topology-level dependency mapping."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_operational_schema(self.db_path)

    # -----------------------------------------------------------------------
    # CRUD Operations for Business Services
    # -----------------------------------------------------------------------

    def create_service(self, service: BusinessServiceRecord) -> BusinessServiceRecord:
        """Persists a new business service into the catalog."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_services (
                    service_id, name, description, criticality, owner_team,
                    health_score, status, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service.service_id,
                    service.name,
                    service.description,
                    service.criticality,
                    service.owner_team,
                    service.health_score,
                    service.status,
                    json.dumps(service.metadata_json or {}),
                    service.created_at or now_iso,
                    service.updated_at or now_iso,
                ),
            )

            # Insert initial endpoints if provided
            for ep in service.endpoints:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO operational_service_endpoints (
                        endpoint_id, service_id, endpoint_type, endpoint_value,
                        target_device_id, target_interface, is_primary, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ep.endpoint_id,
                        service.service_id,
                        ep.endpoint_type,
                        ep.endpoint_value,
                        ep.target_device_id,
                        ep.target_interface,
                        1 if ep.is_primary else 0,
                        ep.created_at or now_iso,
                    ),
                )
        return service

    def get_service(self, service_id: str) -> Optional[BusinessServiceRecord]:
        """Retrieves a business service by ID with all its registered endpoints."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT service_id, name, description, criticality, owner_team,
                       health_score, status, metadata_json, created_at, updated_at
                FROM operational_services WHERE service_id = ?
                """,
                (service_id,),
            ).fetchone()

            if not row:
                return None

            ep_rows = conn.execute(
                """
                SELECT endpoint_id, service_id, endpoint_type, endpoint_value,
                       target_device_id, target_interface, is_primary, created_at
                FROM operational_service_endpoints WHERE service_id = ?
                """,
                (service_id,),
            ).fetchall()

        endpoints = [
            ServiceEndpointRecord(
                endpoint_id=ep[0],
                service_id=ep[1],
                endpoint_type=ep[2],
                endpoint_value=ep[3],
                target_device_id=ep[4],
                target_interface=ep[5],
                is_primary=bool(ep[6]),
                created_at=ep[7],
            )
            for ep in ep_rows
        ]

        return BusinessServiceRecord(
            service_id=row[0],
            name=row[1],
            description=row[2],
            criticality=row[3],
            owner_team=row[4],
            health_score=float(row[5]),
            status=row[6],
            metadata_json=json.loads(row[7] or "{}"),
            created_at=row[8],
            updated_at=row[9],
            endpoints=endpoints,
        )

    def list_services(self) -> List[BusinessServiceRecord]:
        """Lists all registered business services."""
        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(
                """
                SELECT service_id FROM operational_services ORDER BY name ASC
                """
            ).fetchall()

        services: List[BusinessServiceRecord] = []
        for r in rows:
            svc = self.get_service(r[0])
            if svc:
                services.append(svc)
        return services

    def delete_service(self, service_id: str) -> bool:
        """Deletes a business service and cascades to its endpoints."""
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute(
                "DELETE FROM operational_services WHERE service_id = ?",
                (service_id,),
            )
            return cur.rowcount > 0

    def add_endpoint(self, endpoint: ServiceEndpointRecord) -> ServiceEndpointRecord:
        """Registers a new network endpoint binding for a service."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_service_endpoints (
                    endpoint_id, service_id, endpoint_type, endpoint_value,
                    target_device_id, target_interface, is_primary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    endpoint.endpoint_id,
                    endpoint.service_id,
                    endpoint.endpoint_type,
                    endpoint.endpoint_value,
                    endpoint.target_device_id,
                    endpoint.target_interface,
                    1 if endpoint.is_primary else 0,
                    endpoint.created_at or now_iso,
                ),
            )
        return endpoint

    # -----------------------------------------------------------------------
    # Graph Ingestion
    # -----------------------------------------------------------------------

    def ingest_into_knowledge_graph(self, graph: NetworkKnowledgeGraph) -> int:
        """
        Projects all business services and endpoints into the NetworkKnowledgeGraph.
        Returns the total number of service nodes and relationship edges created.
        """
        services = self.list_services()
        now = time.time()
        count = 0

        for svc in services:
            svc_node_id = f"service:{svc.service_id}"
            graph.add_node(
                KnowledgeNode(
                    node_id=svc_node_id,
                    entity_type=GraphEntityType.SERVICE_ENDPOINT.value,
                    label=svc.name,
                    attributes={
                        "service_id": svc.service_id,
                        "description": svc.description,
                        "criticality": svc.criticality,
                        "owner_team": svc.owner_team,
                        "health_score": svc.health_score,
                        "status": svc.status,
                    },
                    observed_at=now,
                )
            )
            count += 1

            for ep in svc.endpoints:
                ep_node_id = f"endpoint:{ep.endpoint_id}"
                graph.add_node(
                    KnowledgeNode(
                        node_id=ep_node_id,
                        entity_type=GraphEntityType.SERVICE_ENDPOINT.value,
                        label=ep.endpoint_value,
                        device_id=ep.target_device_id,
                        attributes={
                            "endpoint_id": ep.endpoint_id,
                            "service_id": ep.service_id,
                            "endpoint_type": ep.endpoint_type,
                            "target_interface": ep.target_interface,
                            "is_primary": ep.is_primary,
                        },
                        observed_at=now,
                    )
                )
                count += 1

                # Edge: Service -> Endpoint (DEPENDS_ON)
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=f"edge_{svc.service_id}_{ep.endpoint_id}",
                        source_id=svc_node_id,
                        target_id=ep_node_id,
                        relationship_type=GraphRelationshipType.DEPENDS_ON.value,
                        observed_at=now,
                    )
                )
                count += 1

                # Edge: Endpoint -> Target Device / Interface (HOSTED_ON)
                if ep.target_device_id:
                    target_node = f"device:{ep.target_device_id}"
                    if ep.target_interface:
                        target_node = f"interface:{ep.target_device_id}:{ep.target_interface}"

                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=f"edge_host_{ep.endpoint_id}",
                            source_id=ep_node_id,
                            target_id=target_node,
                            relationship_type=GraphRelationshipType.HOSTED_ON.value,
                            observed_at=now,
                        )
                    )
                    count += 1

        return count

    # -----------------------------------------------------------------------
    # Service Health & Blast-Radius Evaluation
    # -----------------------------------------------------------------------

    def evaluate_service_health(
        self,
        service_id: str,
        bundle: Optional[NetworkEvidenceBundle] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates health score and high-availability redundancy for a service.
        """
        svc = self.get_service(service_id)
        if not svc:
            return {"error": f"Service '{service_id}' not found."}

        endpoints = svc.endpoints
        if not endpoints:
            return {
                "service_id": service_id,
                "name": svc.name,
                "health_score": 100.0,
                "status": ServiceHealthStatus.HEALTHY.value,
                "redundancy": "NO_ENDPOINTS_CONFIGURED",
                "active_endpoints": 0,
                "total_endpoints": 0,
            }

        # Check redundancy: do endpoints span multiple devices?
        distinct_devices = {ep.target_device_id for ep in endpoints if ep.target_device_id}
        redundancy_type = "HA_ACTIVE" if len(distinct_devices) > 1 else "SINGLE_POINT_OF_FAILURE"

        # Check operational status against evidence bundle
        active_eps = 0
        impaired_reasons: List[str] = []

        for ep in endpoints:
            ep_ok = True
            if bundle and ep.target_device_id:
                dev_data = (bundle.device_evidence or {}).get(ep.target_device_id)
                if dev_data and dev_data.get("status") == "down":
                    ep_ok = False
                    impaired_reasons.append(f"Target device '{ep.target_device_id}' is down.")

                if ep.target_interface and bundle.interface_evidence:
                    ifaces = bundle.interface_evidence.get(ep.target_device_id) or []
                    for if_item in ifaces:
                        if if_item.get("interface_name") == ep.target_interface or if_item.get("name") == ep.target_interface:
                            if if_item.get("oper_status") != "up":
                                ep_ok = False
                                impaired_reasons.append(f"Target interface '{ep.target_interface}' is {if_item.get('oper_status')}.")
                            break

            if ep_ok:
                active_eps += 1

        # Determine health score and status
        total_eps = len(endpoints)
        health_score = round((active_eps / total_eps) * 100.0, 1)

        if active_eps == total_eps:
            status = ServiceHealthStatus.HEALTHY.value
        elif active_eps > 0:
            status = ServiceHealthStatus.DEGRADED.value
        else:
            status = ServiceHealthStatus.DOWN.value

        # Update service record in database
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE operational_services
                SET health_score = ?, status = ?, updated_at = ?
                WHERE service_id = ?
                """,
                (health_score, status, datetime.now(timezone.utc).isoformat(), service_id),
            )

        return {
            "service_id": service_id,
            "name": svc.name,
            "criticality": svc.criticality,
            "health_score": health_score,
            "status": status,
            "redundancy": redundancy_type,
            "active_endpoints": active_eps,
            "total_endpoints": total_eps,
            "impaired_reasons": impaired_reasons,
        }

    def get_services_impacted_by_device(self, device_id: str) -> List[BusinessServiceRecord]:
        """Returns all business services that have endpoints hosted on a specific device."""
        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT service_id FROM operational_service_endpoints
                WHERE target_device_id = ?
                """,
                (device_id,),
            ).fetchall()

        services: List[BusinessServiceRecord] = []
        for r in rows:
            svc = self.get_service(r[0])
            if svc:
                services.append(svc)
        return services
