"""
core/artifacts/tests/test_interactive_html.py — Test suite for Interactive HTML Artifacts & Tools.
"""
import sys
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import tempfile

from core.artifacts.models import ArtifactType, ArtifactStatus
from core.artifacts.specs import VisualizationSpec, VisualizationNode, VisualizationEdge
from core.artifacts.validator import validate_visualization_spec, validate_for_type
from core.artifacts.engine import ArtifactEngine
from core.artifacts.store import ArtifactStore
from agents.rei.artifact_tools import create_interactive_artifact, create_artifact


def test_validator_rejects_empty():
    spec = VisualizationSpec(title="", nodes=[])
    res = validate_visualization_spec(spec)
    assert not res.is_valid
    messages = res.messages()
    assert any("title" in m for m in messages)
    assert any("nodes" in m for m in messages)


def test_validator_detects_duplicate_nodes():
    spec = VisualizationSpec(
        title="Valid Title",
        nodes=[
            VisualizationNode(id="node-1", label="Router 1"),
            VisualizationNode(id="node-1", label="Router 2"),
        ]
    )
    res = validate_visualization_spec(spec)
    assert not res.is_valid
    assert any("duplikat" in m for m in res.messages())


def test_validator_valid_spec():
    spec = VisualizationSpec(
        title="Valid Topology",
        description="Core network diagram",
        nodes=[
            VisualizationNode(id="r1", label="Router 1", type="router"),
            VisualizationNode(id="sw1", label="Switch 1", type="switch"),
        ],
        edges=[
            VisualizationEdge(id="e1", source="r1", target="sw1", label="1 Gbps")
        ]
    )
    res = validate_for_type(spec, "html")
    assert res.is_valid


def test_engine_creates_html_artifact():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "artifacts.db"
        store = ArtifactStore(db_path=db_path)
        engine = ArtifactEngine(store=store, resolve_path=lambda rel: tmp_path / rel)

        spec = VisualizationSpec(
            title="Data Center Spine-Leaf",
            description="Spine-leaf architecture for high-throughput compute",
            nodes=[
                VisualizationNode(id="spine-1", label="Spine 01", type="router", ip="10.0.0.1", status="online"),
                VisualizationNode(id="spine-2", label="Spine 02", type="router", ip="10.0.0.2", status="online"),
                VisualizationNode(id="leaf-1", label="Leaf 01", type="switch", ip="10.0.1.1", status="online"),
                VisualizationNode(id="leaf-2", label="Leaf 02", type="switch", ip="10.0.1.2", status="warning"),
            ],
            edges=[
                VisualizationEdge(source="spine-1", target="leaf-1", label="40G"),
                VisualizationEdge(source="spine-1", target="leaf-2", label="40G"),
                VisualizationEdge(source="spine-2", target="leaf-1", label="40G"),
                VisualizationEdge(source="spine-2", target="leaf-2", label="40G"),
            ]
        )

        result = engine.create_visualization(spec)
        assert result.success
        assert result.artifact is not None
        assert result.artifact.artifact_type == ArtifactType.HTML.value
        assert result.artifact.status == ArtifactStatus.READY.value
        assert result.artifact.size > 0

        # Verify file content
        file_path = tmp_path / result.artifact.storage_reference
        assert file_path.exists()
        content = file_path.read_text(encoding="utf-8")

        # Required features verified in generated HTML
        assert "Data Center Spine-Leaf" in content
        assert "spine-1" in content
        assert "leaf-2" in content
        assert "btn-export-svg" in content
        assert "btn-export-png" in content
        assert "detail-panel" in content
        assert "node-search" in content
        assert "btn-zoom-in" in content
        assert "btn-zoom-out" in content
        assert "btn-zoom-reset" in content
        assert "#030712" in content  # Dark theme background


def test_rei_tool_create_interactive_artifact():
    result = create_interactive_artifact(
        title="Enterprise WAN Topology",
        description="Multi-site MPLS and SD-WAN interconnect",
        nodes=[
            {"id": "hq-gw", "label": "HQ Edge Gateway", "type": "router", "ip": "172.16.1.1", "status": "online"},
            {"id": "br-gw", "label": "Branch Edge Gateway", "type": "router", "ip": "172.16.2.1", "status": "online"}
        ],
        edges=[
            {"id": "wan-link", "source": "hq-gw", "target": "br-gw", "label": "SD-WAN Tunnel", "speed": "100 Mbps"}
        ]
    )

    assert result["success"] is True
    assert result["tool"] == "create_interactive_artifact"
    assert result["artifact_id"].startswith("artifact_")
    assert result["view_url"].startswith("/api/artifacts/")
    assert result["download_url"].startswith("/api/artifacts/")
    assert result["size"] > 0
    assert "Enterprise WAN Topology" in result["note"]


if __name__ == "__main__":
    test_validator_rejects_empty()
    test_validator_detects_duplicate_nodes()
    test_validator_valid_spec()
    test_engine_creates_html_artifact()
    test_rei_tool_create_interactive_artifact()
    print("ALL INTERACTIVE HTML TESTS PASSED SUCCESSFULLY!")
