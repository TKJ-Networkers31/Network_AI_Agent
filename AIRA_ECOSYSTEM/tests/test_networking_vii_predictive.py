"""
Tests for Networking VII Phase B (WP 7.1) — Predictive Operations Engine.
"""

from __future__ import annotations

import time
import pytest

from core.network_intelligence.intelligence_models import (
    NetworkEvidenceBundle,
)
from core.operations.models import (
    PredictionStatus,
    RiskLevel,
    TimeWindow,
    TrendDirection,
)
from core.operations.predictive_engine import (
    MIN_SAMPLE_THRESHOLD,
    PredictiveOperationsEngine,
)


@pytest.fixture
def engine() -> PredictiveOperationsEngine:
    return PredictiveOperationsEngine()


def test_insufficient_samples_emits_unknown(engine: PredictiveOperationsEngine) -> None:
    """Verifies that N < 10 samples returns INSUFFICIENT_DATA without hallucinating trends."""
    now = time.time()
    # Provide only 5 samples
    samples = [(now - (5 - i) * 60, 45.0 + i) for i in range(5)]

    projection = engine.analyze_metric_trend(
        metric_name="rx_utilization_percent",
        entity_type="interface",
        entity_id="ether1",
        device_id="R-1",
        raw_samples=samples,
    )

    assert projection.status == PredictionStatus.INSUFFICIENT_DATA.value
    assert projection.risk_level == RiskLevel.UNKNOWN.value
    assert projection.confidence_score == 0.0
    assert projection.confidence_level == "UNKNOWN"
    assert projection.hours_to_warning is None
    assert projection.hours_to_critical is None
    assert projection.sample_count == 5
    assert len(projection.epistemic_limitations) >= 1


def test_missing_samples_preserved_not_zero(engine: PredictiveOperationsEngine) -> None:
    """Verifies that None values in time series are filtered out and not converted to 0.0."""
    now = time.time()
    raw = [
        (now - 1200, 70.0),
        (now - 1100, None),   # Missing sample
        (now - 1000, 71.0),
        (now - 900, None),    # Missing sample
        (now - 800, 72.0),
    ]

    cleaned = engine._clean_series(raw)
    assert len(cleaned) == 3
    assert all(val is not None for _, val in cleaned)
    # Ensure no 0.0 was injected
    assert all(val >= 70.0 for _, val in cleaned)


def test_steady_state_headroom(engine: PredictiveOperationsEngine) -> None:
    """A flat constant metric has stable trend and infinite headroom (Risk: INFO)."""
    now = time.time()
    # 20 samples with steady 35% CPU
    samples = [(now - (20 - i) * 60, 35.0) for i in range(20)]

    projection = engine.analyze_metric_trend(
        metric_name="cpu_load_percent",
        entity_type="device",
        entity_id="R-1",
        device_id="R-1",
        raw_samples=samples,
    )

    assert projection.status == PredictionStatus.VALID.value
    assert projection.risk_level == RiskLevel.INFO.value
    assert projection.trend_direction == TrendDirection.STABLE.value
    assert projection.hours_to_warning is None
    assert projection.hours_to_critical is None
    assert projection.r_squared == 1.0
    assert projection.confidence_score >= 0.75
    assert projection.confidence_level == "HIGH"


def test_steep_saturation_critical_risk(engine: PredictiveOperationsEngine) -> None:
    """A rapid upward trend projecting warning breach within 24 hours triggers CRITICAL."""
    now = time.time()
    # 15 samples climbing from 60% to 78% over 1 hour (climbing 18% / hour)
    # Warning threshold is 80%, critical is 95%
    # Expected hours to warning = (80 - 78) / 18 ~= 0.11 hours (< 24 hours) -> CRITICAL
    step_sec = 240  # 4 minutes per step = 15 steps in 60 mins
    samples = [(now - (14 - i) * step_sec, 60.0 + (i * 1.285)) for i in range(15)]

    projection = engine.analyze_metric_trend(
        metric_name="rx_utilization_percent",
        entity_type="interface",
        entity_id="sfp-sfpplus1",
        device_id="Core-1",
        raw_samples=samples,
    )

    assert projection.status == PredictionStatus.VALID.value
    assert projection.risk_level == RiskLevel.CRITICAL.value
    assert projection.trend_direction == TrendDirection.RAPID_INCREASE.value
    assert projection.hours_to_warning is not None
    assert projection.hours_to_warning <= 24.0
    assert projection.hours_to_critical is not None
    assert projection.days_to_warning is not None
    assert "Immediate operational review" in (projection.recommended_action or "")


def test_moderate_growth_warning_risk(engine: PredictiveOperationsEngine) -> None:
    """A moderate upward trend projecting warning in ~3 days triggers WARNING."""
    now = time.time()
    # 24 hourly samples climbing from 40% to 52% (0.5% per hour)
    # Warning threshold 80%: (80 - 52) / 0.5 = 56 hours (~2.3 days) -> WARNING
    samples = [(now - (23 - i) * 3600, 40.0 + (i * 0.5)) for i in range(24)]

    projection = engine.analyze_metric_trend(
        metric_name="tx_utilization_percent",
        entity_type="interface",
        entity_id="ether2",
        device_id="R-1",
        raw_samples=samples,
        window=TimeWindow.TWENTY_FOUR_HOURS.value,
    )

    assert projection.status == PredictionStatus.VALID.value
    assert projection.risk_level == RiskLevel.WARNING.value
    assert projection.trend_direction == TrendDirection.MODERATE_INCREASE.value
    assert projection.hours_to_warning is not None
    assert 24.0 < projection.hours_to_warning <= 168.0
    assert projection.days_to_warning is not None
    assert 1.0 <= projection.days_to_warning <= 7.0


def test_active_critical_breach(engine: PredictiveOperationsEngine) -> None:
    """An entity currently above critical threshold is immediately classified as CRITICAL."""
    now = time.time()
    # 12 samples already at 96%
    samples = [(now - (11 - i) * 60, 96.0) for i in range(12)]

    projection = engine.analyze_metric_trend(
        metric_name="memory_used_percent",
        entity_type="device",
        entity_id="CHR",
        device_id="CHR",
        raw_samples=samples,
    )

    assert projection.risk_level == RiskLevel.CRITICAL.value
    assert projection.hours_to_critical == 0.0
    assert projection.hours_to_warning == 0.0


def test_analyze_evidence_bundle_aggregation(engine: PredictiveOperationsEngine) -> None:
    """Verifies analyze_evidence_bundle aggregates multiple metrics across devices and interfaces."""
    now = time.time()

    bundle = NetworkEvidenceBundle(
        bundle_id="bnd_test_pred",
        correlation_id="corr_test_pred",
        assembled_at=now,
        scope="cluster",
        device_evidence={
            "R-1": {"device_id": "R-1", "identity": "R-1", "cpu_load_percent": 45.0},
            "CHR": {"device_id": "CHR", "identity": "CHR", "cpu_load_percent": 88.0},
        },
        interface_evidence={
            "R-1": [
                {
                    "device_id": "R-1",
                    "interface_name": "ether1",
                    "oper_status": "up",
                    "rx_utilization_percent": 35.0,
                    "tx_utilization_percent": 25.0,
                }
            ],
            "CHR": [
                {
                    "device_id": "CHR",
                    "interface_name": "ether1",
                    "oper_status": "up",
                    "rx_utilization_percent": 92.0,
                    "tx_utilization_percent": 85.0,
                }
            ],
        },
    )

    # Provide rich history for CHR ether1 Rx
    chr_rx_history = [(now - (15 - i) * 300, 75.0 + (i * 1.2)) for i in range(16)]
    samples_map = {
        "CHR:ether1:rx_utilization_percent": chr_rx_history,
    }

    report = engine.analyze_evidence_bundle(bundle, historical_samples_map=samples_map)

    assert report.report_id.startswith("pred_rep_")
    assert report.highest_risk_level in (RiskLevel.CRITICAL.value, RiskLevel.WARNING.value)
    assert len(report.projections) >= 3
    assert report.risk_counts[RiskLevel.CRITICAL.value] >= 1 or report.risk_counts[RiskLevel.WARNING.value] >= 1
    assert len(report.action_items) >= 1
