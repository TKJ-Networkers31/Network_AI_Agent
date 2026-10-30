"""
Unit and integration tests for Background Voice Service and Voice REST API.
Verifies lifecycle states, device discovery, duplicate start prevention,
mic pause/resume arbitration, transcript masking, and REST endpoints.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from agents.yuki.voice_io import (
    VoiceState,
    VoiceIO,
    STATE_STOPPED,
    STATE_STARTING,
    STATE_RUNNING,
    STATE_LISTENING,
    STATE_PROCESSING,
    STATE_ERROR,
    STATE_PAUSED,
    _mask_transcript,
)
from agents.yuki.service import BackgroundVoiceService
from api.main import app


@pytest.fixture
def test_client():
    return TestClient(app)


class TestVoiceStateEnum:
    def test_voice_states_definition(self):
        assert VoiceState.STOPPED.value == "STOPPED"
        assert VoiceState.STARTING.value == "STARTING"
        assert VoiceState.RUNNING.value == "RUNNING"
        assert VoiceState.LISTENING.value == "LISTENING"
        assert VoiceState.PROCESSING.value == "PROCESSING"
        assert VoiceState.ERROR.value == "ERROR"
        assert VoiceState.PAUSED.value == "PAUSED"


class TestVoiceIOLifecycle:
    def test_initial_state_is_stopped(self):
        io = VoiceIO()
        assert io.state == STATE_STOPPED
        status = io.stats
        assert status["state"] == "STOPPED"
        assert status["is_listening"] is False
        assert status["active_backend"] is not None

    def test_pause_and_resume_mic(self):
        io = VoiceIO()
        # Set active & running to simulate active listener
        io._active.set()
        io._state = STATE_LISTENING
        
        # Pause
        res = io.pause_mic(reason="chat_speech_active")
        assert res["success"] is True
        assert res["state"] == STATE_PAUSED
        assert io.state == STATE_PAUSED
        assert io.stats["paused_reason"] == "chat_speech_active"

        # Resume
        res_resume = io.resume_mic()
        assert res_resume["success"] is True
        assert io.state == STATE_LISTENING
        assert io._pause_reason is None

    def test_duplicate_start_protection(self):
        io = VoiceIO()
        io._active.set()
        mock_t = MagicMock()
        mock_t.is_alive.return_value = True
        io._thread = mock_t

        # Calling start while running should return already_running=True without creating new thread
        with patch("threading.Thread") as mock_thread:
            res = io.start()
            assert res["success"] is True
            assert res.get("already_running") is True
            mock_thread.assert_not_called()

    def test_transcript_masking(self):
        # Sensitive credentials in transcript should be masked
        masked = _mask_transcript("RouterOS admin password123 secret key")
        assert "password123" not in masked
        assert "***" in masked


class TestBackgroundVoiceService:
    def test_service_lifecycle_mocked(self):
        service = BackgroundVoiceService()
        status = service.get_status()
        assert "state" in status
        assert "active_backend" in status
        assert "devices" in status

    def test_service_start_stop(self):
        service = BackgroundVoiceService()
        with patch.object(service._voice_io, "start", return_value={"success": True, "state": "STARTING"}):
            res = service.start()
            assert res["success"] is True

        with patch.object(service._voice_io, "stop", return_value={"success": True, "state": "STOPPED"}):
            res = service.stop()
            assert res["success"] is True


class TestVoiceAPIRouter:
    def test_get_status_endpoint(self, test_client):
        res = test_client.get("/api/voice/service/status")
        assert res.status_code == 200
        data = res.json()
        assert "state" in data
        assert "is_listening" in data
        assert "devices" in data

    def test_pause_and_resume_endpoints(self, test_client):
        # Pause endpoint
        res = test_client.post("/api/voice/service/pause", json={"reason": "test_pause"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["reason"] == "test_pause"

        # Resume endpoint
        res = test_client.post("/api/voice/service/resume")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

    def test_start_and_stop_endpoints(self, test_client):
        # Stop endpoint
        res = test_client.post("/api/voice/service/stop")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["state"] == "STOPPED"
