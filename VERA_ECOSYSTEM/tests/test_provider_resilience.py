"""
tests/test_provider_resilience.py — Comprehensive test suite for Provider Health Manager,
Circuit Breaker, Fast Failure, and Multi-Provider Fallback.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from core.provider_health import (
    CircuitState,
    FailureCategory,
    HealthStatus,
    ProviderHealthManager,
    get_provider_health_manager,
)
from agents.rei.provider_client import (
    ProviderClient,
    _classify_request_exception,
    _normalize_timeout,
    _request_error,
)
import requests


class TestProviderHealthManager(unittest.TestCase):

    def setUp(self):
        self.mgr = ProviderHealthManager(failure_threshold=2, cooldown_seconds=0.1)

    def test_initial_state_healthy(self):
        self.assertTrue(self.mgr.is_provider_available("nvidia"))
        rec = self.mgr._get_or_create("nvidia")
        self.assertEqual(rec.status, HealthStatus.HEALTHY)
        self.assertEqual(rec.circuit_state, CircuitState.CLOSED)

    def test_circuit_trips_after_threshold_failures(self):
        # 1st failure -> DEGRADED, circuit still CLOSED
        self.mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Read timed out")
        rec = self.mgr._get_or_create("nvidia")
        self.assertEqual(rec.status, HealthStatus.DEGRADED)
        self.assertEqual(rec.circuit_state, CircuitState.CLOSED)
        self.assertTrue(self.mgr.is_provider_available("nvidia"))

        # 2nd failure -> Circuit trips to OPEN, status UNAVAILABLE
        self.mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Read timed out")
        self.assertEqual(rec.status, HealthStatus.UNAVAILABLE)
        self.assertEqual(rec.circuit_state, CircuitState.OPEN)
        self.assertFalse(self.mgr.is_provider_available("nvidia"))

    def test_circuit_cooldown_and_recovery(self):
        # Trip circuit
        self.mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
        self.mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")
        self.assertFalse(self.mgr.is_provider_available("nvidia"))

        # Wait for cooldown
        time.sleep(0.15)

        # First request after cooldown enters HALF_OPEN
        self.assertTrue(self.mgr.is_provider_available("nvidia"))
        rec = self.mgr._get_or_create("nvidia")
        self.assertEqual(rec.circuit_state, CircuitState.HALF_OPEN)
        self.assertEqual(rec.status, HealthStatus.RECOVERING)

        # Successful probe resets to CLOSED
        self.mgr.record_success("nvidia", latency=0.25)
        self.assertEqual(rec.circuit_state, CircuitState.CLOSED)
        self.assertEqual(rec.status, HealthStatus.HEALTHY)
        self.assertEqual(rec.consecutive_failures, 0)
        self.assertEqual(len(rec.latency_samples), 1)

    def test_failed_probe_reopens_circuit(self):
        self.mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
        self.mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")
        time.sleep(0.15)
        self.assertTrue(self.mgr.is_provider_available("nvidia"))  # Enters HALF_OPEN

        # Failed probe trips back to OPEN immediately
        self.mgr.record_failure("nvidia", FailureCategory.CONNECTION, "Connection refused")
        rec = self.mgr._get_or_create("nvidia")
        self.assertEqual(rec.circuit_state, CircuitState.OPEN)
        self.assertEqual(rec.status, HealthStatus.UNAVAILABLE)

    def test_exception_classification(self):
        exc_timeout = requests.exceptions.Timeout("Read timed out")
        err_type, cat = _classify_request_exception(exc_timeout)
        self.assertEqual(err_type, "timeout")
        self.assertEqual(cat, FailureCategory.TIMEOUT)

        exc_conn = requests.exceptions.ConnectionError("Connection reset")
        err_type, cat = _classify_request_exception(exc_conn)
        self.assertEqual(err_type, "connection")
        self.assertEqual(cat, FailureCategory.CONNECTION)

    def test_bounded_timeouts(self):
        timeouts = self.mgr.get_timeouts(is_classifier=True)
        self.assertEqual(timeouts, (4.0, 4.0))

        timeouts_aux = self.mgr.get_timeouts(is_auxiliary=True)
        self.assertEqual(timeouts_aux, (4.0, 8.0))

        timeouts_normal = self.mgr.get_timeouts()
        self.assertEqual(timeouts_normal, (4.0, 25.0))


class TestFastFailureIntegration(unittest.TestCase):

    def setUp(self):
        self.health_mgr = get_provider_health_manager()
        self.health_mgr.reset()

    def tearDown(self):
        self.health_mgr.reset()

    def test_fast_fail_when_circuit_open(self):
        # Manually trip circuit for test provider
        self.health_mgr.record_failure("test_prov", FailureCategory.TIMEOUT, "Timeout 1")
        self.health_mgr.record_failure("test_prov", FailureCategory.TIMEOUT, "Timeout 2")

        res = ProviderClient.chat("test_prov", "dummy_model", [{"role": "user", "content": "hi"}])
        self.assertIn("error", res)
        self.assertEqual(res.get("error_type"), "circuit_open")
        self.assertIn("Circuit breaker OPEN", res["error"])


if __name__ == "__main__":
    unittest.main()
