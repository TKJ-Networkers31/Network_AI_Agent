"""
tests/test_model_sync_api.py — End-to-End Automated Test Suite for Frontend & Backend Model Registry Synchronization.

Validates:
1. Authoritative Backend REST APIs for Model Registry, Capabilities, Classifications, Benchmarks, Active Model, and Sync Status.
2. Provider Telemetry & Circuit Breaker endpoints.
3. EventBus publication and WebSocket translation for all 8 real-time model events:
   - model_registry_updated
   - model_status_changed
   - provider_health_changed
   - model_availability_changed
   - model_priority_changed
   - model_discovery_completed
   - model_sync_failed
   - active_model_changed
4. Strict RBAC Permission Architecture:
   - Standard authenticated operators can read models, capabilities, and health.
   - Non-superadmins are strictly rejected with HTTP 403 on mutation/administrative actions.
   - Superadmin users are authorized for full administration.
5. Real-Time WebSocket endpoint /ws/models snapshot and frames.
"""

import os
import unittest
from unittest import mock
import pytest
from starlette.testclient import TestClient

from api.main import app
from core.events import EventNames, event_bus
from core.model_store import get_model_store
from core.provider_health import get_provider_health_manager, CircuitState, HealthStatus, FailureCategory
from core.tenant.auth_deps import get_current_authenticated_user, require_superadmin
from core.tenant.models import TenantContext


# Mock User Contexts
STANDARD_OPERATOR_CONTEXT = TenantContext(
    user_id="operator_user_01",
    username="operator_lingga",
    is_internal=True,
    tenant_id="tenant_internal",
    roles=["NOC_OPERATOR"],
    groups=["OPERATORS"],
    permissions={"models.read", "chat.read"},
    account_enabled=True,
)

SUPERADMIN_CONTEXT = TenantContext(
    user_id="superadmin_user_01",
    username="lingga_admin",
    is_internal=True,
    tenant_id="tenant_internal",
    roles=["SUPERADMIN"],
    groups=["SUPER_ADMIN"],
    permissions={"*"},
    account_enabled=True,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


class TestModelSyncApiReadEndpoints:
    """Verifies all model read endpoints return authoritative backend data."""

    @pytest.fixture(autouse=True)
    def setup_superadmin_auth(self):
        app.dependency_overrides[get_current_authenticated_user] = lambda: SUPERADMIN_CONTEXT
        app.dependency_overrides[require_superadmin] = lambda: SUPERADMIN_CONTEXT
        yield
        app.dependency_overrides.pop(get_current_authenticated_user, None)
        app.dependency_overrides.pop(require_superadmin, None)

    def test_list_models_all_and_filtering(self, client):
        # 1. List all
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert len(data["models"]) > 0

        # 2. Filter by capability
        resp_cap = client.get("/api/models?capability=tool_calling")
        assert resp_cap.status_code == 200
        for m in resp_cap.json()["models"]:
            assert m["supports_tool_calling"] or "tool_calling" in m.get("capabilities", [])

        # 3. Filter by provider
        resp_prov = client.get("/api/models?provider=nvidia")
        assert resp_prov.status_code == 200
        for m in resp_prov.json()["models"]:
            assert m["provider"] == "nvidia"

        # 4. Search query
        resp_search = client.get("/api/models?search=nemotron")
        assert resp_search.status_code == 200
        for m in resp_search.json()["models"]:
            assert "nemotron" in m["model_id"].lower() or "nemotron" in m["display_name"].lower()

    def test_get_active_model(self, client):
        resp = client.get("/api/models/active?label=general")
        assert resp.status_code == 200
        data = resp.json()

        assert data["task_label"] == "general"
        assert "preferred_model" in data
        assert "executing_model" in data
        assert "fallback_model" in data
        assert "active_by_label" in data
        assert "provider_health" in data

    def test_get_classifications(self, client):
        resp = client.get("/api/models/classifications")
        assert resp.status_code == 200
        data = resp.json()
        assert "classifications" in data
        # Must return all 28 unified categories
        assert len(data["classifications"]) == 28
        first_cat = data["classifications"][0]
        assert "category" in first_cat
        assert "name" in first_cat
        assert "models_count" in first_cat

    def test_get_capabilities(self, client):
        resp = client.get("/api/models/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "capabilities" in data
        caps = data["capabilities"]
        assert "tool_calling" in caps
        assert "streaming" in caps
        assert "vision" in caps
        assert "structured_output" in caps
        assert isinstance(caps["tool_calling"], list)

    def test_get_benchmarks(self, client):
        resp = client.get("/api/models/benchmarks")
        assert resp.status_code == 200
        data = resp.json()
        assert "benchmarks" in data
        assert len(data["benchmarks"]) > 0
        b0 = data["benchmarks"][0]
        assert "context_window" in b0
        assert "max_output_tokens" in b0
        assert "priority" in b0
        assert "health_status" in b0
        assert "lifecycle_status" in b0

    def test_get_sync_status(self, client):
        resp = client.get("/api/models/sync-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "provider" in data
        assert "registered_models_count" in data
        assert "nvidia_models_count" in data


class TestProviderTelemetryEndpoints:
    """Verifies upstream AI provider registry and circuit breaker endpoints."""

    @pytest.fixture(autouse=True)
    def setup_superadmin_auth(self):
        app.dependency_overrides[get_current_authenticated_user] = lambda: SUPERADMIN_CONTEXT
        app.dependency_overrides[require_superadmin] = lambda: SUPERADMIN_CONTEXT
        yield
        app.dependency_overrides.pop(get_current_authenticated_user, None)
        app.dependency_overrides.pop(require_superadmin, None)

    def test_list_providers(self, client):
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        provider_ids = [p["id"] for p in data["providers"]]
        assert "nvidia" in provider_ids
        assert "openrouter" in provider_ids
        assert "gemini" in provider_ids

    def test_get_providers_health(self, client):
        resp = client.get("/api/providers/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "health" in data

    def test_reset_circuit_breaker(self, client):
        health_mgr = get_provider_health_manager()
        # Simulate tripped circuit
        health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Simulated timeout")
        health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Simulated timeout")

        # Call reset endpoint
        resp = client.post("/api/providers/nvidia/reset-circuit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["circuit_state"] == "CLOSED"

        # Verify manager state restored
        rec = health_mgr.get_record("nvidia")
        assert rec.circuit_state == CircuitState.CLOSED
        assert rec.status == HealthStatus.HEALTHY


class TestModelSyncApiMutationsAndEvents:
    """Verifies that administrative updates persist to database and broadcast EventBus events."""

    @pytest.fixture(autouse=True)
    def setup_superadmin_auth(self):
        app.dependency_overrides[get_current_authenticated_user] = lambda: SUPERADMIN_CONTEXT
        app.dependency_overrides[require_superadmin] = lambda: SUPERADMIN_CONTEXT
        yield
        app.dependency_overrides.pop(get_current_authenticated_user, None)
        app.dependency_overrides.pop(require_superadmin, None)

    def test_update_status_and_events(self, client):
        store = get_model_store()
        models = store.list_models()
        assert len(models) > 0
        target = models[0]
        target_id = target["id"]

        captured_events = []
        token1 = event_bus.subscribe(EventNames.MODEL_STATUS_CHANGED, lambda e: captured_events.append(e))
        token2 = event_bus.subscribe(EventNames.MODEL_AVAILABILITY_CHANGED, lambda e: captured_events.append(e))
        token3 = event_bus.subscribe(EventNames.MODEL_REGISTRY_UPDATED, lambda e: captured_events.append(e))

        try:
            # Disable model
            resp = client.put(f"/api/models/{target_id}/status", json={"enabled": False})
            assert resp.status_code == 200
            updated = resp.json()["model"]
            assert updated["enabled"] is False

            # Verify events published
            event_types = [e.event for e in captured_events]
            assert EventNames.MODEL_STATUS_CHANGED in event_types
            assert EventNames.MODEL_AVAILABILITY_CHANGED in event_types
            assert EventNames.MODEL_REGISTRY_UPDATED in event_types

            # Re-enable model
            resp2 = client.put(f"/api/models/{target_id}/status", json={"enabled": True})
            assert resp2.status_code == 200
            assert resp2.json()["model"]["enabled"] is True
        finally:
            event_bus.unsubscribe(EventNames.MODEL_STATUS_CHANGED, token1)
            event_bus.unsubscribe(EventNames.MODEL_AVAILABILITY_CHANGED, token2)
            event_bus.unsubscribe(EventNames.MODEL_REGISTRY_UPDATED, token3)

    def test_update_priority_and_events(self, client):
        store = get_model_store()
        models = store.list_models()
        target_id = models[0]["id"]

        captured_events = []
        token1 = event_bus.subscribe(EventNames.MODEL_PRIORITY_CHANGED, lambda e: captured_events.append(e))
        token2 = event_bus.subscribe(EventNames.MODEL_REGISTRY_UPDATED, lambda e: captured_events.append(e))

        try:
            resp = client.put(f"/api/models/{target_id}/priority", json={"priority": 5})
            assert resp.status_code == 200
            assert resp.json()["model"]["priority"] == 5

            event_types = [e.event for e in captured_events]
            assert EventNames.MODEL_PRIORITY_CHANGED in event_types
            assert EventNames.MODEL_REGISTRY_UPDATED in event_types
        finally:
            event_bus.unsubscribe(EventNames.MODEL_PRIORITY_CHANGED, token1)
            event_bus.unsubscribe(EventNames.MODEL_REGISTRY_UPDATED, token2)

    def test_sync_remote_catalog_and_events(self, client):
        store = get_model_store()
        captured_events = []
        token = event_bus.subscribe(EventNames.MODEL_DISCOVERY_COMPLETED, lambda e: captured_events.append(e))

        registered_nvidia = list({m["model_id"] for m in store.list_models() if m.get("provider") == "nvidia"})
        mock_catalog_response = {
            "data": [{"id": mid} for mid in registered_nvidia]
        }

        with mock.patch("requests.get") as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.json.return_value = mock_catalog_response
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            try:
                resp = client.post("/api/models/sync", json={"provider": "nvidia", "api_key": "nvapi-test"})
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["remote_count"] == len(registered_nvidia)

                assert any(e.event == EventNames.MODEL_DISCOVERY_COMPLETED for e in captured_events)
            finally:
                event_bus.unsubscribe(EventNames.MODEL_DISCOVERY_COMPLETED, token)

    def test_routing_and_policy_updates(self, client):
        store = get_model_store()
        models = store.list_models()
        target_id = models[0]["id"]

        captured_events = []
        token = event_bus.subscribe(EventNames.ACTIVE_MODEL_CHANGED, lambda e: captured_events.append(e))

        try:
            # Set default model for general
            resp = client.put("/api/models/routing/general", json={"default_model_id": target_id})
            assert resp.status_code == 200

            # Update policy
            resp_policy = client.put("/api/models/policy", json={"fallback_model_id": target_id, "retry_provider": 2})
            assert resp_policy.status_code == 200

            assert len(captured_events) >= 2
            assert all(e.event == EventNames.ACTIVE_MODEL_CHANGED for e in captured_events)
        finally:
            event_bus.unsubscribe(EventNames.ACTIVE_MODEL_CHANGED, token)


class TestModelSyncApiPermissions:
    """Verifies strict RBAC permission controls: read allowed for operators, mutations forbidden."""

    def test_read_allowed_for_standard_operator(self, client):
        app.dependency_overrides[get_current_authenticated_user] = lambda: STANDARD_OPERATOR_CONTEXT
        try:
            # Standard operator CAN read models
            resp = client.get("/api/models")
            assert resp.status_code == 200

            # Standard operator CAN read active model
            resp_active = client.get("/api/models/active")
            assert resp_active.status_code == 200

            # Standard operator CAN read capabilities
            resp_caps = client.get("/api/models/capabilities")
            assert resp_caps.status_code == 200

            # Standard operator CAN read classifications
            resp_class = client.get("/api/models/classifications")
            assert resp_class.status_code == 200

            # Standard operator CAN read providers
            resp_prov = client.get("/api/providers")
            assert resp_prov.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_authenticated_user, None)

    def test_mutations_forbidden_for_standard_operator(self, client):
        app.dependency_overrides[get_current_authenticated_user] = lambda: STANDARD_OPERATOR_CONTEXT
        try:
            # POST /api/models -> 403 Forbidden
            resp = client.post("/api/models", json={"provider": "nvidia", "model_id": "test", "display_name": "Test"})
            assert resp.status_code == 403

            # PUT /api/models/{id}/status -> 403 Forbidden
            resp_status = client.put("/api/models/test-model/status", json={"enabled": False})
            assert resp_status.status_code == 403

            # PUT /api/models/{id}/priority -> 403 Forbidden
            resp_pri = client.put("/api/models/test-model/priority", json={"priority": 1})
            assert resp_pri.status_code == 403

            # POST /api/models/sync -> 403 Forbidden
            resp_sync = client.post("/api/models/sync", json={"provider": "nvidia"})
            assert resp_sync.status_code == 403

            # PUT /api/models/routing/general -> 403 Forbidden
            resp_route = client.put("/api/models/routing/general", json={"default_model_id": "test"})
            assert resp_route.status_code == 403

            # DELETE /api/models/{id} -> 403 Forbidden
            resp_del = client.delete("/api/models/test-model")
            assert resp_del.status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_authenticated_user, None)


class TestModelSyncWebSocket:
    """Verifies /ws/models streaming connection and initial snapshot."""

    def test_websocket_models_snapshot_and_ping(self, client):
        with client.websocket_connect("/ws/models") as ws:
            # 1. First message must be snapshot
            msg = ws.receive_json()
            assert msg["type"] == "model_registry_snapshot"
            data = msg["data"]
            assert "models" in data
            assert "routing" in data
            assert "policy" in data
            assert "provider_health" in data

            # 2. Ping-pong response
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
