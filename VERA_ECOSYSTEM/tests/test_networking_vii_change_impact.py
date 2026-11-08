"""
Tests for Networking VII Phase C (WP 7.2) — Network Change Impact Intelligence.
"""

from __future__ import annotations

import time
import pytest

from core.network_intelligence.intelligence_models import (
    GraphEntityType,
    GraphRelationshipType,
    KnowledgeEdge,
    KnowledgeNode,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.operations.change_impact_engine import ChangeImpactEngine
from core.operations.models import ChangeScenarioRequest


@pytest.fixture
def sample_topology_graph() -> NetworkKnowledgeGraph:
    """Builds a 3-node linear topology: Core-1 <-> Dist-1 <-> Access-1."""
    graph = NetworkKnowledgeGraph()
    now = time.time()

    # Add devices
    graph.add_node(KnowledgeNode(
        node_id="device:Core-1",
        entity_type=GraphEntityType.DEVICE.value,
        device_id="Core-1",
        label="Core Router",
        observed_at=now,
    ))
    graph.add_node(KnowledgeNode(
        node_id="device:Dist-1",
        entity_type=GraphEntityType.DEVICE.value,
        device_id="Dist-1",
        label="Distribution Switch",
        observed_at=now,
    ))
    graph.add_node(KnowledgeNode(
        node_id="device:Access-1",
        entity_type=GraphEntityType.DEVICE.value,
        device_id="Access-1",
        label="Access Switch",
        observed_at=now,
    ))

    # Add interfaces
    graph.add_node(KnowledgeNode(
        node_id="interface:Core-1:sfp-sfpplus1",
        entity_type=GraphEntityType.INTERFACE.value,
        device_id="Core-1",
        label="sfp-sfpplus1",
        observed_at=now,
    ))
    graph.add_node(KnowledgeNode(
        node_id="interface:Dist-1:sfp1",
        entity_type=GraphEntityType.INTERFACE.value,
        device_id="Dist-1",
        label="sfp1",
        observed_at=now,
    ))

    # Add edges
    graph.add_edge(KnowledgeEdge(
        edge_id="edge_core_dist",
        source_id="device:Core-1",
        target_id="device:Dist-1",
        relationship_type=GraphRelationshipType.LAYER3_REACHABILITY.value,
        observed_at=now,
    ))
    graph.add_edge(KnowledgeEdge(
        edge_id="edge_dist_access",
        source_id="device:Dist-1",
        target_id="device:Access-1",
        relationship_type=GraphRelationshipType.LAYER2_ADJACENCY.value,
        observed_at=now,
    ))
    graph.add_edge(KnowledgeEdge(
        edge_id="edge_core_iface",
        source_id="interface:Core-1:sfp-sfpplus1",
        target_id="device:Dist-1",
        relationship_type=GraphRelationshipType.PHYSICAL_ADJACENCY.value,
        observed_at=now,
    ))

    return graph


@pytest.fixture
def empty_bundle() -> NetworkEvidenceBundle:
    return NetworkEvidenceBundle(
        bundle_id="bnd_change_test",
        correlation_id="corr_change_test",
        assembled_at=time.time(),
        scope="cluster",
    )


def test_simulation_preserves_original_graph(
    sample_topology_graph: NetworkKnowledgeGraph,
    empty_bundle: NetworkEvidenceBundle,
) -> None:
    """Verifies 100% in-memory isolation: the original graph is untouched after simulation."""
    engine = ChangeImpactEngine()
    orig_node_count = len(sample_topology_graph.nodes)
    orig_edge_count = len(sample_topology_graph.edges)

    req = ChangeScenarioRequest(
        scenario_id="scen_001",
        title="Shutdown Core Interface",
        change_type="INTERFACE_DOWN",
        target_device="Core-1",
        target_entity="sfp-sfpplus1",
    )

    report = engine.simulate_change(req, empty_bundle, sample_topology_graph)

    assert report.is_simulation is True
    # Verify original graph is identical
    assert len(sample_topology_graph.nodes) == orig_node_count
    assert len(sample_topology_graph.edges) == orig_edge_count
    assert "edge_core_iface" in sample_topology_graph.edges


def test_interface_down_blast_radius(
    sample_topology_graph: NetworkKnowledgeGraph,
    empty_bundle: NetworkEvidenceBundle,
) -> None:
    """Simulating interface down severs connection and identifies directly impacted devices."""
    engine = ChangeImpactEngine()

    req = ChangeScenarioRequest(
        scenario_id="scen_002",
        title="Disable Core-Dist Trunk",
        change_type="INTERFACE_DOWN",
        target_device="Core-1",
        target_entity="sfp-sfpplus1",
    )

    report = engine.simulate_change(req, empty_bundle, sample_topology_graph)

    assert report.change_type == "INTERFACE_DOWN"
    assert "Dist-1" in report.directly_impacted_devices
    assert len(report.rollback_plan) >= 1
    assert any("sfp-sfpplus1" in cmd for cmd in report.rollback_plan)
    assert len(report.preflight_checklist) >= 3


def test_device_reboot_isolation(
    sample_topology_graph: NetworkKnowledgeGraph,
    empty_bundle: NetworkEvidenceBundle,
) -> None:
    """Rebooting Dist-1 breaks downstream Access-1 without alternate path (Severity: CRITICAL)."""
    engine = ChangeImpactEngine()

    req = ChangeScenarioRequest(
        scenario_id="scen_003",
        title="Dist-1 Firmware Upgrade Reboot",
        change_type="DEVICE_REBOOT",
        target_device="Dist-1",
        target_entity="Dist-1",
    )

    report = engine.simulate_change(req, empty_bundle, sample_topology_graph)

    assert report.change_type == "DEVICE_REBOOT"
    assert report.severity in ("CRITICAL", "HIGH")
    assert any("Access-1" in loss for loss in report.redundancy_losses) or len(report.severed_transit_paths) >= 1
