"""
AIRA_ECOSYSTEM/tests/test_network_intelligence_playbooks.py —
Tests for Diagnostic Playbooks Engine and 7 Initial Playbooks.
"""

import pytest
from unittest.mock import patch

from core.network_intelligence.models import (
    DiagnosticPlaybook,
    PlaybookRunRecord,
    PlaybookStatus,
)
from core.network_intelligence.playbooks import PlaybookEngine


def test_seven_initial_playbooks_structure():
    engine = PlaybookEngine()
    playbooks = engine.list_playbooks()
    assert len(playbooks) >= 7

    expected_ids = {
        "PB-LAN-INTERNET",
        "PB-DEFAULT-ROUTE",
        "PB-NAT-MISMATCH",
        "PB-FW-FORWARD",
        "PB-OSPF-ADJ",
        "PB-BGP-PREFIX",
        "PB-VLAN-TRUNK",
    }
    actual_ids = {pb.playbook_id for pb in playbooks}
    assert expected_ids.issubset(actual_ids)

    # Check read_only enforcement and step commands
    for pb in playbooks:
        assert pb.read_only is True
        assert len(pb.steps) > 0
        for step in pb.steps:
            cmd = step.action.get("command", "")
            # Ensure strictly read-only print commands and no mutating command verbs
            assert "print" in cmd.lower()
            tokens = cmd.lower().split()
            assert not any(tok in ("add", "set", "remove", "enable", "disable", "reset") for tok in tokens)


def test_playbook_run_lifecycle_and_stepping():
    engine = PlaybookEngine()

    run = engine.start_playbook_run(
        playbook_id="PB-LAN-INTERNET",
        incident_id="inc_test_123",
        device_identity="R1",
    )
    assert run.status == PlaybookStatus.RUNNING.value
    assert run.current_step_id == "STEP_1_CHECK_LAN_IP"
    assert len(run.completed_steps) == 0

    # Advance step 1 with mock evidence (client subnet found)
    mock_bundle = {
        "evidence_items": [
            MagicMock(
                observation_type="ip_addresses",
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "192.168.1.1/24"}]},
            )
        ]
    }

    with patch.object(engine.collector, "collect_evidence_bundle", return_value=mock_bundle):
        advanced = engine.advance_playbook(run.run_id, action="step")
        assert "STEP_1_CHECK_LAN_IP" in advanced.completed_steps
        assert advanced.current_step_id == "STEP_2_CHECK_DEFAULT_ROUTE"
        assert len(advanced.step_logs) >= 2


def test_playbook_cancellation():
    engine = PlaybookEngine()
    run = engine.start_playbook_run(
        playbook_id="PB-DEFAULT-ROUTE",
        incident_id="inc_test_456",
        device_identity="R1",
    )

    cancelled = engine.advance_playbook(run.run_id, action="cancel")
    assert cancelled.status == PlaybookStatus.CANCELLED.value
    assert any("dibatalkan" in log.get("message", "").lower() for log in cancelled.step_logs)


from unittest.mock import MagicMock
