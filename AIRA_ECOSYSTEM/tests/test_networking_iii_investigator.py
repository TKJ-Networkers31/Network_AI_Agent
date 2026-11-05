"""
tests/test_networking_iii_investigator.py — Unit tests for Phase Networking III Topology-Aware RCA.
"""

import pytest
from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.models import IncidentType


def test_multi_device_investigation_structure():
    inv = NetworkInvestigator()

    # Synthetic multi-device investigation
    rec = inv.run_multi_device_investigation(
        primary_device="Core-1",
        related_devices=["ISP-1"],
        symptom_description="Klien tidak dapat menjangkau internet melalui Core-1",
        incident_type=IncidentType.DEFAULT_ROUTE_FAILS,
    )

    assert rec is not None
    assert rec.device_identity == "Core-1"
    assert "ISP-1" in rec.related_devices
    assert rec.investigation_status == "DIAGNOSIS_READY"
    assert len(rec.observed_facts) >= 2
    assert len(rec.inferred_hypotheses) > 0
    hyp = rec.inferred_hypotheses[0]
    hyp_id = hyp.get("hypothesis_id") if isinstance(hyp, dict) else hyp.hypothesis_id
    assert hyp_id is not None
    assert rec.correlation_id is not None

    d = rec.to_dict()
    assert d["related_devices"] == ["ISP-1"]
    assert "Multi-device evidence collected" in d["observed_facts"][0]
