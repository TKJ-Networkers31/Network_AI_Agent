"""
core/network_intelligence/change_detector.py — Event-Driven Network Change & Anomaly Detection Engine (Phase G).

Implements:
- Device & Interface State Comparison (NMS, Inventory, Topology).
- Event Deduplication & Debouncing (preventing AI invocation on every poll).
- Event Correlation & Priority Classification.
- Active Investigation Attachment (updating existing investigations instead of duplicate generation).
- Bounded Event Expiration & Idempotency.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.events import event_bus
from core.network_intelligence.store import get_network_intelligence_store

logger = logging.getLogger("aira.network_intelligence.change_detector")

DEFAULT_DEBOUNCE_SEC = 15.0
LATENCY_DELTA_THRESHOLD_MS = 30.0
PACKET_LOSS_DELTA_THRESHOLD_PCT = 5.0
CPU_DELTA_THRESHOLD_PCT = 25.0


class NetworkChangeDetector:
    """Thread-safe change detection and event correlation engine."""

    def __init__(self, debounce_sec: float = DEFAULT_DEBOUNCE_SEC):
        self.debounce_sec = debounce_sec
        self._lock = threading.RLock()
        self._device_state_cache: Dict[str, Dict[str, Any]] = {}
        self._last_event_time: Dict[str, float] = {}
        self.store = get_network_intelligence_store()

    def evaluate_metric_sample(
        self,
        device_id: str,
        metrics: Dict[str, Any],
        source: str = "NMS",
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates a fresh metrics sample against cached device baseline.
        Returns a structured event ONLY if a meaningful change is detected.
        Suppresses identical periodic poll data.
        """
        now = time.time()
        with self._lock:
            prev = self._device_state_cache.get(device_id)
            last_ts = self._last_event_time.get(device_id, 0.0)

            # 1. Baseline initialization
            if prev is None:
                self._device_state_cache[device_id] = {
                    "status": metrics.get("status", "UP"),
                    "latency_ms": float(metrics.get("latency_ms", 0.0) or 0.0),
                    "packet_loss_pct": float(metrics.get("packet_loss_pct", 0.0) or 0.0),
                    "cpu_util_pct": float(metrics.get("cpu_util_pct", 0.0) or 0.0),
                    "active_interfaces": list(metrics.get("active_interfaces", [])),
                    "timestamp": now,
                }
                return None

            # 2. Debouncing check
            if (now - last_ts) < self.debounce_sec:
                return None

            # 3. Delta calculations
            curr_status = metrics.get("status", prev["status"])
            curr_latency = float(metrics.get("latency_ms", prev["latency_ms"]) or 0.0)
            curr_loss = float(metrics.get("packet_loss_pct", prev["packet_loss_pct"]) or 0.0)
            curr_cpu = float(metrics.get("cpu_util_pct", prev["cpu_util_pct"]) or 0.0)
            curr_ifaces = list(metrics.get("active_interfaces", prev.get("active_interfaces", [])))

            delta_reasons: List[str] = []
            severity = "LOW"

            # Check status transition
            if curr_status != prev["status"]:
                delta_reasons.append(f"Status transitioned from {prev['status']} to {curr_status}")
                if curr_status in ("DOWN", "UNREACHABLE"):
                    severity = "CRITICAL"
                elif curr_status == "DEGRADED":
                    severity = "HIGH"
                else:
                    severity = "MEDIUM"

            # Check latency spike
            latency_diff = abs(curr_latency - prev["latency_ms"])
            if latency_diff >= LATENCY_DELTA_THRESHOLD_MS:
                delta_reasons.append(f"Latency delta {latency_diff:.1f}ms exceeds threshold (now {curr_latency:.1f}ms)")
                if curr_latency > 100.0 and severity not in ("CRITICAL",):
                    severity = "HIGH"

            # Check packet loss
            loss_diff = abs(curr_loss - prev["packet_loss_pct"])
            if loss_diff >= PACKET_LOSS_DELTA_THRESHOLD_PCT:
                delta_reasons.append(f"Packet loss delta {loss_diff:.1f}% exceeds threshold (now {curr_loss:.1f}%)")
                if curr_loss > 10.0 and severity not in ("CRITICAL",):
                    severity = "HIGH"

            # Check CPU utilization
            cpu_diff = abs(curr_cpu - prev["cpu_util_pct"])
            if cpu_diff >= CPU_DELTA_THRESHOLD_PCT and curr_cpu > 80.0:
                delta_reasons.append(f"CPU utilization spiked to {curr_cpu:.1f}%")
                if severity == "LOW":
                    severity = "MEDIUM"

            # Check interface flapping / changes
            if set(curr_ifaces) != set(prev.get("active_interfaces", [])):
                added = set(curr_ifaces) - set(prev.get("active_interfaces", []))
                removed = set(prev.get("active_interfaces", [])) - set(curr_ifaces)
                if added:
                    delta_reasons.append(f"Interfaces up: {', '.join(added)}")
                if removed:
                    delta_reasons.append(f"Interfaces down: {', '.join(removed)}")
                    if severity == "LOW":
                        severity = "HIGH"

            # 4. If no meaningful changes detected, skip event publication
            if not delta_reasons:
                # Update timestamp only
                prev["timestamp"] = now
                return None

            # 5. Meaningful change verified -> construct NetworkEvent
            event_id = f"ev_{uuid.uuid4().hex[:12]}"
            event_payload = {
                "event_id": event_id,
                "event_type": "NETWORK_CONDITION_CHANGED",
                "device_id": device_id,
                "source": source,
                "severity": severity,
                "reasons": delta_reasons,
                "before_state": {
                    "status": prev["status"],
                    "latency_ms": prev["latency_ms"],
                    "packet_loss_pct": prev["packet_loss_pct"],
                    "cpu_util_pct": prev["cpu_util_pct"],
                },
                "after_state": {
                    "status": curr_status,
                    "latency_ms": curr_latency,
                    "packet_loss_pct": curr_loss,
                    "cpu_util_pct": curr_cpu,
                },
                "detected_at": now,
            }

            # Update cache
            self._device_state_cache[device_id] = {
                "status": curr_status,
                "latency_ms": curr_latency,
                "packet_loss_pct": curr_loss,
                "cpu_util_pct": curr_cpu,
                "active_interfaces": curr_ifaces,
                "timestamp": now,
            }
            self._last_event_time[device_id] = now

            # 6. Correlate with active investigations to avoid duplicate storm
            self._correlate_or_trigger_investigation(device_id, event_payload)

            # 7. Publish to system EventBus
            try:
                event_bus.publish(
                    "network.condition_changed",
                    agent="CHANGE_DETECTOR",
                    data=event_payload,
                )
            except Exception as exc:
                logger.warning("Failed to publish network change event: %s", exc)

            return event_payload

    def _correlate_or_trigger_investigation(self, device_id: str, event_payload: Dict[str, Any]) -> None:
        """
        Attaches event evidence to an existing active investigation, or initializes a new one.
        Ensures idempotency and prevents flood of duplicate investigations.
        """
        try:
            recent_incidents = self.store.list_incidents(device_identity=device_id, limit=5)
            active_incident = next((i for i in recent_incidents if i.investigation_status != "COMPLETED"), None)

            if active_incident:
                # Update existing incident with new observation
                logger.info(
                    "Attaching condition change to existing investigation %s for device %s",
                    active_incident.incident_id,
                    device_id,
                )
                self.store.update_incident_evidence(
                    incident_id=active_incident.incident_id,
                    facts_to_add=event_payload["reasons"],
                )
            else:
                # Trigger a new focused investigation if severity is HIGH or CRITICAL
                if event_payload["severity"] in ("HIGH", "CRITICAL"):
                    from core.network_intelligence.investigator import NetworkInvestigator
                    investigator = NetworkInvestigator()
                    symptom = "; ".join(event_payload["reasons"])
                    inc_type = investigator.classify_symptom(symptom)
                    investigator.investigate_incident(
                        device_identity=device_id,
                        incident_type=inc_type,
                        symptoms=event_payload["reasons"],
                        user_description=f"Auto-triggered by change detector: {symptom}",
                        severity=event_payload["severity"],
                    )
        except Exception as exc:
            logger.warning("Error in auto-investigation correlation: %s", exc)


_change_detector: Optional[NetworkChangeDetector] = None

def get_change_detector() -> NetworkChangeDetector:
    global _change_detector
    if _change_detector is None:
        _change_detector = NetworkChangeDetector()
    return _change_detector
