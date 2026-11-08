"""
Tests for Networking VII Phase D (WP 7.3) — Service Dependency Intelligence.
"""

from __future__ import annotations

from pathlib import Path
import time
import pytest

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.operations.models import (
    BusinessServiceRecord,
    ServiceCriticality,
    ServiceEndpointRecord,
    ServiceHealthStatus,
)
from core.operations.service_intelligence import ServiceIntelligenceEngine


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_topology.db"


@pytest.fixture
def service_engine(temp_db_path: Path) -> ServiceIntelligenceEngine:
    return ServiceIntelligenceEngine(db_path=temp_db_path)


def test_service_crud_lifecycle(service_engine: ServiceIntelligenceEngine) -> None:
    """Verifies complete CRUD operations for business services and endpoints."""
    svc = BusinessServiceRecord(
        service_id="svc_core_banking",
        name="Core Banking Gateway",
        description="Handles payment processing and ATM transactions",
        criticality=ServiceCriticality.TIER_1_MISSION_CRITICAL.value,
        owner_team="FinOps",
        endpoints=[
            ServiceEndpointRecord(
                endpoint_id="ep_cb_01",
                service_id="svc_core_banking",
                endpoint_type="IP_PORT",
                endpoint_value="10.10.10.1:8443",
                target_device_id="Core-1",
                target_interface="ether1",
                is_primary=True,
            )
        ],
    )

    created = service_engine.create_service(svc)
    assert created.service_id == "svc_core_banking"

    fetched = service_engine.get_service("svc_core_banking")
    assert fetched is not None
    assert fetched.name == "Core Banking Gateway"
    assert fetched.criticality == ServiceCriticality.TIER_1_MISSION_CRITICAL.value
    assert len(fetched.endpoints) == 1
    assert fetched.endpoints[0].target_device_id == "Core-1"

    all_svcs = service_engine.list_services()
    assert len(all_svcs) >= 1

    deleted = service_engine.delete_service("svc_core_banking")
    assert deleted is True
    assert service_engine.get_service("svc_core_banking") is None


def test_knowledge_graph_ingestion(service_engine: ServiceIntelligenceEngine) -> None:
    """Verifies that services and endpoints are properly projected into NetworkKnowledgeGraph."""
    svc = BusinessServiceRecord(
        service_id="svc_erp",
        name="Enterprise ERP",
        description="ERP Database and web frontends",
        criticality=ServiceCriticality.TIER_2_BUSINESS_OPERATIONAL.value,
        owner_team="IT Infrastructure",
        endpoints=[
            ServiceEndpointRecord(
                endpoint_id="ep_erp_pri",
                service_id="svc_erp",
                endpoint_type="IP_PORT",
                endpoint_value="10.20.0.50:443",
                target_device_id="R-1",
                target_interface="ether2",
                is_primary=True,
            ),
            ServiceEndpointRecord(
                endpoint_id="ep_erp_sec",
                service_id="svc_erp",
                endpoint_type="IP_PORT",
                endpoint_value="10.20.0.51:443",
                target_device_id="CHR",
                target_interface="ether2",
                is_primary=False,
            ),
        ],
    )
    service_engine.create_service(svc)

    graph = NetworkKnowledgeGraph()
    count = service_engine.ingest_into_knowledge_graph(graph)

    # 1 service node + 2 endpoint nodes + 2 DEPENDS_ON edges + 2 HOSTED_ON edges = 7 entities
    assert count == 7
    assert "service:svc_erp" in graph.nodes
    assert "endpoint:ep_erp_pri" in graph.nodes
    assert "endpoint:ep_erp_sec" in graph.nodes
    assert "edge_svc_erp_ep_erp_pri" in graph.edges
    assert "edge_host_ep_erp_pri" in graph.edges


def test_service_health_ha_and_spof(service_engine: ServiceIntelligenceEngine) -> None:
    """Verifies redundancy classification (HA vs SPOF) and health degradation against evidence."""
    # 1. HA Service spanning Core-1 and CHR
    ha_svc = BusinessServiceRecord(
        service_id="svc_dns",
        name="Internal Recursive DNS",
        description="Highly available internal DNS",
        criticality=ServiceCriticality.TIER_1_MISSION_CRITICAL.value,
        owner_team="NetOps",
        endpoints=[
            ServiceEndpointRecord(
                endpoint_id="ep_dns_1",
                service_id="svc_dns",
                endpoint_type="IP_PORT",
                endpoint_value="10.0.0.53:53",
                target_device_id="Core-1",
            ),
            ServiceEndpointRecord(
                endpoint_id="ep_dns_2",
                service_id="svc_dns",
                endpoint_type="IP_PORT",
                endpoint_value="10.0.0.54:53",
                target_device_id="CHR",
            ),
        ],
    )
    service_engine.create_service(ha_svc)

    # Test clean state
    health_report = service_engine.evaluate_service_health("svc_dns")
    assert health_report["redundancy"] == "HA_ACTIVE"
    assert health_report["status"] == ServiceHealthStatus.HEALTHY.value
    assert health_report["health_score"] == 100.0

    # Test state with Core-1 down in evidence bundle
    bundle = NetworkEvidenceBundle(
        bundle_id="bnd_test_health",
        correlation_id="corr_test_health",
        assembled_at=time.time(),
        scope="cluster",
        device_evidence={
            "Core-1": {"status": "down"},
            "CHR": {"status": "up"},
        },
    )

    degraded_report = service_engine.evaluate_service_health("svc_dns", bundle=bundle)
    assert degraded_report["status"] == ServiceHealthStatus.DEGRADED.value
    assert degraded_report["health_score"] == 50.0
    assert len(degraded_report["impaired_reasons"]) >= 1


def test_get_services_impacted_by_device(service_engine: ServiceIntelligenceEngine) -> None:
    """Verifies immediate reverse lookup of services depending on a given device."""
    svc = BusinessServiceRecord(
        service_id="svc_voip",
        name="VoIP PBX SIP Trunk",
        description="Corporate telephony",
        criticality=ServiceCriticality.TIER_2_BUSINESS_OPERATIONAL.value,
        owner_team="VoiceOps",
        endpoints=[
            ServiceEndpointRecord(
                endpoint_id="ep_voip_01",
                service_id="svc_voip",
                endpoint_type="IP_PORT",
                endpoint_value="192.168.10.10:5060",
                target_device_id="Edge-Router-1",
            )
        ],
    )
    service_engine.create_service(svc)

    impacted = service_engine.get_services_impacted_by_device("Edge-Router-1")
    assert len(impacted) == 1
    assert impacted[0].service_id == "svc_voip"

    not_impacted = service_engine.get_services_impacted_by_device("Unrelated-Device")
    assert len(not_impacted) == 0
