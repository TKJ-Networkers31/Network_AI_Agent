"""
core/provider_health.py — Centralized Provider Health Manager & Circuit Breaker for VERA.

Maintains real-time telemetry, failure classification, latency tracking, and
resilient circuit breakers (CLOSED, OPEN, HALF_OPEN) across all LLM providers.
Prevents cascading timeouts and fast-fails requests to degraded providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vera.provider_health")


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    RECOVERING = "RECOVERING"
    DISABLED = "DISABLED"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests pass through
    OPEN = "OPEN"            # Tripped: requests immediately fast-failed or routed to fallback
    HALF_OPEN = "HALF_OPEN"  # Testing recovery with controlled probe


class FailureCategory(str, Enum):
    CONNECTION = "connection"
    DNS = "dns"
    TLS = "tls"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"      # 5xx
    AUTH_ERROR = "auth_error"          # 401, 403 (non-retryable)
    BAD_REQUEST = "bad_request"        # 400 (non-retryable)
    NOT_FOUND = "not_found"            # 404 (non-retryable)
    STREAM_INTERRUPTED = "stream_interrupted"
    CANCELLED = "cancelled"
    OTHER = "other"


NON_RETRYABLE_FAILURES = {
    FailureCategory.AUTH_ERROR,
    FailureCategory.BAD_REQUEST,
    FailureCategory.NOT_FOUND,
    FailureCategory.CANCELLED,
}


@dataclass
class ModelHealthRecord:
    model_id: str
    provider: str
    status: HealthStatus = HealthStatus.HEALTHY
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    last_error: str = ""
    last_failure_category: Optional[FailureCategory] = None
    last_failure_ts: Optional[float] = None
    last_success_ts: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "status": self.status.value,
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "last_error": self.last_error,
            "last_failure_category": self.last_failure_category.value if self.last_failure_category else None,
            "last_failure_ts": self.last_failure_ts,
            "last_success_ts": self.last_success_ts,
        }


@dataclass
class ProviderHealthRecord:
    provider: str
    endpoint_url: str = ""
    status: HealthStatus = HealthStatus.HEALTHY
    circuit_state: CircuitState = CircuitState.CLOSED
    last_success_ts: Optional[float] = None
    last_failure_ts: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_requests: int = 0
    total_failures: int = 0
    total_timeouts: int = 0
    total_rate_limits: int = 0
    latency_samples: List[float] = field(default_factory=list)  # Last 20 samples in seconds
    last_error_message: str = ""
    last_failure_category: Optional[FailureCategory] = None
    circuit_opened_at: Optional[float] = None
    probe_in_flight: bool = False
    probe_started_at: Optional[float] = None

    def average_latency(self) -> float:
        if not self.latency_samples:
            return 0.0
        return round(sum(self.latency_samples) / len(self.latency_samples), 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "endpoint_url": self.endpoint_url,
            "status": self.status.value,
            "circuit_state": self.circuit_state.value,
            "last_success_ts": self.last_success_ts,
            "last_failure_ts": self.last_failure_ts,
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_timeouts": self.total_timeouts,
            "total_rate_limits": self.total_rate_limits,
            "avg_latency_s": self.average_latency(),
            "last_error": self.last_error_message,
            "last_failure_category": self.last_failure_category.value if self.last_failure_category else None,
            "circuit_opened_at": self.circuit_opened_at,
        }


class ProviderHealthManager:
    """
    Centralized, thread-safe health evaluator and circuit breaker for LLM providers.
    """

    def __init__(
        self,
        failure_threshold: int = 2,       # Open circuit after 2 consecutive timeouts or 3 total errors
        cooldown_seconds: float = 30.0,    # Duration before attempting HALF_OPEN probe
        connect_timeout: float = 4.0,     # Max TCP/TLS connect timeout in seconds
        read_timeout: float = 25.0,       # Max model generation read timeout
        classifier_timeout: float = 4.0,   # Max prompt classifier timeout
    ) -> None:
        self._lock = threading.Lock()
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.classifier_timeout = classifier_timeout
        self._records: Dict[str, ProviderHealthRecord] = {}
        self._model_records: Dict[str, ModelHealthRecord] = {}

    def _get_or_create(self, provider: str, endpoint: str = "") -> ProviderHealthRecord:
        key = provider
        if key not in self._records:
            self._records[key] = ProviderHealthRecord(provider=provider, endpoint_url=endpoint)
        elif endpoint and not self._records[key].endpoint_url:
            self._records[key].endpoint_url = endpoint
        return self._records[key]

    def _get_or_create_model(self, provider: str, model_id: str) -> ModelHealthRecord:
        key = f"{provider}:{model_id}"
        if key not in self._model_records:
            self._model_records[key] = ModelHealthRecord(model_id=model_id, provider=provider)
        return self._model_records[key]

    def is_provider_available(self, provider: str) -> bool:
        """
        Determines whether a request may be routed to this provider.
        Checks circuit breaker state and cooldown window.
        """
        return self.is_endpoint_available(provider)

    def is_endpoint_available(self, provider: str, endpoint: str = "") -> bool:
        """
        Determines whether the upstream endpoint for this provider is available.
        Read-only query: does NOT consume the probe slot.
        """
        with self._lock:
            rec = self._get_or_create(provider, endpoint)
            now = time.time()

            if rec.circuit_state == CircuitState.CLOSED:
                return True

            if rec.circuit_state == CircuitState.OPEN:
                # Check if cooldown has elapsed
                if rec.circuit_opened_at and (now - rec.circuit_opened_at) >= self.cooldown_seconds:
                    logger.info("CIRCUIT BREAKER | Provider '%s' cooldown elapsed (%ss). Entering HALF_OPEN.", provider, self.cooldown_seconds)
                    rec.circuit_state = CircuitState.HALF_OPEN
                    rec.status = HealthStatus.RECOVERING
                    rec.probe_in_flight = False
                    rec.probe_started_at = None
                    return True
                return False

            if rec.circuit_state == CircuitState.HALF_OPEN:
                # If a probe has been in flight for longer than 15s without completing, allow probe retry
                if rec.probe_in_flight and rec.probe_started_at and (now - rec.probe_started_at) > 15.0:
                    logger.warning("CIRCUIT BREAKER | Provider '%s' in-flight probe expired in HALF_OPEN. Allowing retry.", provider)
                    rec.probe_in_flight = False
                    rec.probe_started_at = None
                return not rec.probe_in_flight

            return False

    def acquire_probe_slot(self, provider: str, endpoint: str = "") -> bool:
        """
        Attempts to acquire the single permitted probe slot when in HALF_OPEN or transitioning from OPEN.
        Returns True if request may proceed to network.
        Returns False if circuit is OPEN (in cooldown) or another probe is currently active.
        """
        with self._lock:
            rec = self._get_or_create(provider, endpoint)
            now = time.time()

            if rec.circuit_state == CircuitState.CLOSED:
                return True

            if rec.circuit_state == CircuitState.OPEN:
                if rec.circuit_opened_at and (now - rec.circuit_opened_at) >= self.cooldown_seconds:
                    logger.info("CIRCUIT BREAKER | Provider '%s' cooldown elapsed. Entering HALF_OPEN and acquiring probe slot.", provider)
                    rec.circuit_state = CircuitState.HALF_OPEN
                    rec.status = HealthStatus.RECOVERING
                    rec.probe_in_flight = True
                    rec.probe_started_at = now
                    return True
                return False

            if rec.circuit_state == CircuitState.HALF_OPEN:
                if rec.probe_in_flight and rec.probe_started_at and (now - rec.probe_started_at) > 15.0:
                    rec.probe_in_flight = False
                    rec.probe_started_at = None

                if not rec.probe_in_flight:
                    rec.probe_in_flight = True
                    rec.probe_started_at = now
                    logger.info("CIRCUIT BREAKER | Provider '%s' probe slot acquired in HALF_OPEN.", provider)
                    return True
                return False

            return False

    def release_probe_slot(self, provider: str) -> None:
        """Releases the probe slot if request was aborted prior to network transmission."""
        with self._lock:
            if provider in self._records:
                rec = self._records[provider]
                if rec.circuit_state == CircuitState.HALF_OPEN:
                    rec.probe_in_flight = False
                    rec.probe_started_at = None

    def is_model_available(self, provider: str, model_id: str, endpoint: str = "") -> bool:
        """Checks both provider endpoint health and model-specific status."""
        if not self.is_endpoint_available(provider, endpoint):
            return False
        with self._lock:
            m_rec = self._model_records.get(f"{provider}:{model_id}")
            if m_rec and m_rec.status == HealthStatus.UNAVAILABLE:
                # Model-specific failure (e.g. permanent 404)
                return False
        return True

    def record_success(
        self,
        provider: str,
        latency: float,
        model_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        """Records a successful response and updates circuit health."""
        with self._lock:
            rec = self._get_or_create(provider, endpoint or "")
            now = time.time()
            rec.last_success_ts = now
            rec.consecutive_failures = 0
            rec.consecutive_successes += 1
            rec.total_requests += 1
            rec.probe_in_flight = False
            rec.probe_started_at = None

            rec.latency_samples.append(latency)
            if len(rec.latency_samples) > 20:
                rec.latency_samples.pop(0)

            if rec.circuit_state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("CIRCUIT BREAKER | Provider '%s' probe SUCCEEDED. Resetting to CLOSED (HEALTHY).", provider)
                rec.circuit_state = CircuitState.CLOSED
                rec.status = HealthStatus.HEALTHY
                rec.circuit_opened_at = None
            else:
                rec.status = HealthStatus.HEALTHY

            if model_id:
                m_rec = self._get_or_create_model(provider, model_id)
                m_rec.last_success_ts = now
                m_rec.consecutive_failures = 0
                m_rec.status = HealthStatus.HEALTHY
                m_rec.total_requests += 1

    def record_failure(
        self,
        provider: str,
        category: FailureCategory,
        error_message: str,
        model_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        """Records a failure and triggers circuit opening if threshold is reached."""
        with self._lock:
            now = time.time()

            # Record model-level telemetry
            if model_id:
                m_rec = self._get_or_create_model(provider, model_id)
                m_rec.last_failure_ts = now
                m_rec.last_error = error_message[:300]
                m_rec.last_failure_category = category
                m_rec.total_requests += 1
                m_rec.total_failures += 1
                if category == FailureCategory.NOT_FOUND:
                    m_rec.status = HealthStatus.UNAVAILABLE
                    m_rec.consecutive_failures += 1

            # Endpoint-level circuit breaker:
            # Model-specific errors (NOT_FOUND, BAD_REQUEST, CANCELLED) and rate limits DO NOT trip the provider circuit breaker!
            is_endpoint_error = category in (
                FailureCategory.TIMEOUT,
                FailureCategory.CONNECTION,
                FailureCategory.DNS,
                FailureCategory.TLS,
                FailureCategory.SERVER_ERROR,
            )

            rec = self._get_or_create(provider, endpoint or "")
            rec.last_failure_ts = now
            rec.last_error_message = error_message[:300]
            rec.last_failure_category = category
            rec.total_requests += 1
            rec.total_failures += 1
            rec.probe_in_flight = False
            rec.probe_started_at = None

            if category == FailureCategory.TIMEOUT:
                rec.total_timeouts += 1
            elif category == FailureCategory.RATE_LIMIT:
                rec.total_rate_limits += 1

            if is_endpoint_error:
                rec.consecutive_failures += 1
                rec.consecutive_successes = 0

                # Evaluate Circuit Breaker trip conditions
                trip_condition = (
                    rec.consecutive_failures >= self.failure_threshold
                    or rec.circuit_state == CircuitState.HALF_OPEN
                )

                if trip_condition and rec.circuit_state != CircuitState.OPEN:
                    rec.circuit_state = CircuitState.OPEN
                    rec.status = HealthStatus.UNAVAILABLE
                    rec.circuit_opened_at = now
                    logger.warning(
                        "CIRCUIT BREAKER OPENED | Provider '%s' tripped after %d consecutive failures (last: %s). Cooldown: %ss",
                        provider, rec.consecutive_failures, category.value, self.cooldown_seconds,
                    )
                elif rec.consecutive_failures > 0 and rec.circuit_state == CircuitState.CLOSED:
                    rec.status = HealthStatus.DEGRADED

    def get_timeouts(self, is_classifier: bool = False, is_auxiliary: bool = False) -> tuple[float, float]:
        """Returns (connect_timeout, read_timeout) in seconds based on operation type."""
        if is_classifier:
            return (self.connect_timeout, self.classifier_timeout)
        if is_auxiliary:
            return (self.connect_timeout, 8.0)
        return (self.connect_timeout, self.read_timeout)

    def get_record(self, provider: str) -> Optional[ProviderHealthRecord]:
        with self._lock:
            return self._records.get(provider)

    def get_all_records(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: v.to_dict() for k, v in self._records.items()}

    def get_model_record(self, provider: str, model_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            key = f"{provider}:{model_id}"
            rec = self._model_records.get(key)
            return rec.to_dict() if rec else None

    def get_all_model_records(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: v.to_dict() for k, v in self._model_records.items()}

    def reset_circuit(self, provider: str) -> bool:
        """Manually or administratively resets a tripped circuit breaker to CLOSED/HEALTHY."""
        with self._lock:
            if provider in self._records:
                rec = self._records[provider]
                rec.circuit_state = CircuitState.CLOSED
                rec.status = HealthStatus.HEALTHY
                rec.consecutive_failures = 0
                rec.circuit_opened_at = None
                rec.probe_in_flight = False
                logger.info("CIRCUIT BREAKER RESET | Provider '%s' circuit manually restored to CLOSED/HEALTHY.", provider)
                return True
            return False

    def reset(self, provider: Optional[str] = None) -> None:
        with self._lock:
            if provider:
                self._records.pop(provider, None)
            else:
                self._records.clear()


_GLOBAL_HEALTH_MANAGER: Optional[ProviderHealthManager] = None


def get_provider_health_manager() -> ProviderHealthManager:
    global _GLOBAL_HEALTH_MANAGER
    if _GLOBAL_HEALTH_MANAGER is None:
        _GLOBAL_HEALTH_MANAGER = ProviderHealthManager()
    return _GLOBAL_HEALTH_MANAGER
