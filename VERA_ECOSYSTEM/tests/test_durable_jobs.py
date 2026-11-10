"""
tests/test_durable_jobs.py — Tests for Durable Background Jobs, State Machine & Event Replay.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
import uuid

from core.job_store import JobStore, JobState
from api.main import app

client = TestClient(app)


@pytest.fixture
def temp_job_store(tmp_path: Path):
    db_file = tmp_path / "test_jobs.db"
    return JobStore(db_path=db_file)


def test_job_lifecycle(temp_job_store: JobStore):
    # 1. Create Job
    job = temp_job_store.create_job(
        job_type="network_diagnostic",
        title="BGP Path Analysis",
        session_id="sess_123",
        run_id="run_abc",
        user_id="user_admin",
        stage="init",
    )
    assert job.job_id.startswith("job_")
    assert job.state == JobState.RUNNING.value
    assert job.progress == 0.0

    # 2. Check Active Job for Session
    active = temp_job_store.get_active_job_for_session("sess_123")
    assert active is not None
    assert active.job_id == job.job_id

    # 3. Update Progress & Checkpoint
    updated = temp_job_store.update_job_progress(
        job_id=job.job_id,
        progress=50.0,
        stage="querying_routes",
        checkpoint_data={"routes_found": 42},
    )
    assert updated is not None
    assert updated.progress == 50.0
    assert updated.stage == "querying_routes"
    assert updated.checkpoint_data.get("routes_found") == 42

    # 4. Record Events
    ev1 = temp_job_store.record_event(
        job_id=job.job_id,
        event_type="tool_start",
        event_data={"tool": "bgp_routes", "asn": 65001},
        session_id="sess_123",
        run_id="run_abc",
    )
    ev2 = temp_job_store.record_event(
        job_id=job.job_id,
        event_type="tool_finish",
        event_data={"tool": "bgp_routes", "status": "ok"},
        session_id="sess_123",
        run_id="run_abc",
    )
    events = temp_job_store.get_events_for_job(job.job_id)
    assert len(events) == 2
    assert events[0].event_type == "tool_start"
    assert events[1].event_type == "tool_finish"

    # 5. Complete Job
    completed = temp_job_store.complete_job(
        job_id=job.job_id,
        result_data={"convergence_seconds": 1.2},
    )
    assert completed is not None
    assert completed.state == JobState.SUCCEEDED.value
    assert completed.progress == 100.0
    assert completed.result_data.get("convergence_seconds") == 1.2
    assert completed.completed_at is not None

    # 6. Verify No Longer Active
    active_now = temp_job_store.get_active_job_for_session("sess_123")
    assert active_now is None


def test_job_recovery_on_interruption(temp_job_store: JobStore):
    # Create two jobs: one running, one queued
    j1 = temp_job_store.create_job(
        job_type="topology_scan",
        title="Full Discovery",
        session_id="sess_scan",
    )
    assert j1.state == JobState.RUNNING.value

    # Simulate unexpected system reboot / process crash recovery
    interrupted_count = temp_job_store.recover_interrupted_jobs()
    assert interrupted_count == 1

    recovered_j1 = temp_job_store.get_job(j1.job_id)
    assert recovered_j1 is not None
    assert recovered_j1.state == JobState.INTERRUPTED.value
    assert recovered_j1.stage == "interrupted_system_restart"


def test_jobs_api_endpoints():
    unique_sess = f"test_sess_{uuid.uuid4().hex[:8]}"

    # Create Job via API
    resp = client.post(
        "/api/v1/jobs",
        json={
            "job_type": "vrrp_failover_check",
            "title": "Automated VRRP Verification",
            "session_id": unique_sess,
            "checkpoint_data": {"vrid": 10},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    job_id = data["job"]["job_id"]

    # Get Active Job
    active_resp = client.get(f"/api/v1/jobs/active?session_id={unique_sess}")
    assert active_resp.status_code == 200
    active_data = active_resp.json()
    assert active_data["status"] == "active"
    assert active_data["active_job"]["job_id"] == job_id

    # Get Job Details
    details_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert details_resp.status_code == 200
    assert details_resp.json()["job"]["title"] == "Automated VRRP Verification"

    # Cancel Job
    cancel_resp = client.post(f"/api/v1/jobs/{job_id}/cancel", json={"reason": "Test cancel"})
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["job"]["state"] == "CANCELLED"


def test_job_pause_and_resume(temp_job_store: JobStore):
    job = temp_job_store.create_job(
        job_type="firmware_upgrade",
        title="RouterOS v7.14 Upgrade",
        session_id="sess_upgrade",
        checkpoint_data={"step": 1, "downloaded": True},
    )
    assert job.state == JobState.RUNNING.value

    # 1. Pause Job with Checkpoint
    paused = temp_job_store.pause_job(
        job_id=job.job_id,
        checkpoint_data={"step": 2, "ready_for_reboot": True},
        reason="Awaiting maintenance window",
    )
    assert paused is not None
    assert paused.state == JobState.PAUSED.value
    assert paused.stage == "paused"
    assert paused.checkpoint_data.get("ready_for_reboot") is True
    assert paused.checkpoint_data.get("pause_reason") == "Awaiting maintenance window"
    assert paused.is_active() is True

    # 2. Resume Job with Additional Instructions
    resumed = temp_job_store.resume_job(
        job_id=job.job_id,
        additional_instructions="Proceed with reboot during window",
    )
    assert resumed is not None
    assert resumed.state == JobState.RUNNING.value
    assert resumed.stage == "running"
    assert resumed.checkpoint_data.get("additional_instructions") == "Proceed with reboot during window"
    assert resumed.checkpoint_data.get("resumed_at") is not None
