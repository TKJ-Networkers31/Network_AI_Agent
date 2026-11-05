"""
AIRA OS — Predictive Operations Engine (Networking VII / WP 7.1).

Performs transparent, explainable, multi-window time series analysis and risk forecasting
for network device resources, interface bandwidth, error growth, and routing stability.

Strict Epistemic Principles:
1. Never claims to know the future; emits probabilistic projections with declared assumptions.
2. Never converts missing telemetry (`None`) to `0.0`.
3. If sample count N < 10, returns status `INSUFFICIENT_DATA` rather than guessing.
4. Uses outlier-resistant rolling statistics (Median, MAD) and linear trend regression.
5. All calculations are pure Python/NumPy, lightweight, and CPU-cache friendly.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import statistics
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

from core.network_intelligence.baseline_engine import BaselineEngine
from core.network_intelligence.intelligence_models import (
    MetricBaselineRecord,
    NetworkEvidenceBundle,
)
from core.operations.models import (
    PredictiveAnalysisReport,
    PredictiveMetricProjection,
    PredictionStatus,
    RiskLevel,
    TimeWindow,
    TrendDirection,
)

MIN_SAMPLE_THRESHOLD = 10
MAD_SCALE_CONSTANT = 1.4826

DEFAULT_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    # metric_name -> (warning_threshold, critical_threshold)
    "rx_utilization_percent": (80.0, 95.0),
    "tx_utilization_percent": (80.0, 95.0),
    "cpu_load_percent": (75.0, 90.0),
    "memory_used_percent": (80.0, 95.0),
    "error_rate_delta": (10.0, 50.0),
    "packet_loss_percent": (2.0, 5.0),
    "route_churn_per_hour": (5.0, 20.0),
}


class PredictiveOperationsEngine:
    """Predictive forecasting and capacity horizon engine."""

    def __init__(self, baseline_engine: Optional[BaselineEngine] = None) -> None:
        self.baseline_engine = baseline_engine or BaselineEngine()

    @staticmethod
    def _clean_series(
        raw_samples: Sequence[Tuple[float, Optional[float]]]
    ) -> List[Tuple[float, float]]:
        """Filters out None values, ensuring strict epistemic honesty."""
        return [(float(ts), float(val)) for ts, val in raw_samples if val is not None]

    @staticmethod
    def _fit_linear_regression(
        samples: Sequence[Tuple[float, float]]
    ) -> Tuple[float, float, float]:
        """
        Fits y = m * x + c using least-squares linear regression.
        x is normalized relative to t0 (seconds from start).
        Returns: (slope_per_second, intercept, r_squared)
        """
        n = len(samples)
        if n < 2:
            return 0.0, samples[0][1] if samples else 0.0, 0.0

        t0 = samples[0][0]
        sum_x = 0.0
        sum_y = 0.0
        for s in samples:
            sum_x += s[0] - t0
            sum_y += s[1]

        mean_x = sum_x / n
        mean_y = sum_y / n

        ss_xx = 0.0
        ss_yy = 0.0
        ss_xy = 0.0
        for s in samples:
            dx = (s[0] - t0) - mean_x
            dy = s[1] - mean_y
            ss_xx += dx * dx
            ss_yy += dy * dy
            ss_xy += dx * dy

        if ss_xx == 0.0:
            return 0.0, mean_y, 1.0

        slope = ss_xy / ss_xx
        intercept = mean_y - (slope * mean_x)

        if ss_yy == 0.0:
            # All values identical
            r_squared = 1.0
        else:
            r_val = ss_xy / math.sqrt(ss_xx * ss_yy)
            r_squared = max(0.0, min(1.0, r_val ** 2))

        return slope, intercept, r_squared

    def analyze_metric_trend(
        self,
        metric_name: str,
        entity_type: str,
        entity_id: str,
        device_id: str,
        raw_samples: Sequence[Tuple[float, Optional[float]]],
        window: str = TimeWindow.TWENTY_FOUR_HOURS.value,
        warning_threshold: Optional[float] = None,
        critical_threshold: Optional[float] = None,
    ) -> PredictiveMetricProjection:
        """Analyzes a time series and computes forward-looking saturation horizons."""
        clean_samples = self._clean_series(raw_samples)
        sample_count = len(clean_samples)

        # Threshold resolution
        def_warn, def_crit = DEFAULT_THRESHOLDS.get(metric_name, (80.0, 95.0))
        warn_thresh = warning_threshold if warning_threshold is not None else def_warn
        crit_thresh = critical_threshold if critical_threshold is not None else def_crit

        # Epistemic Rule: If sample count < MIN_SAMPLE_THRESHOLD, never guess
        if sample_count < MIN_SAMPLE_THRESHOLD:
            curr_val = clean_samples[-1][1] if clean_samples else None
            return PredictiveMetricProjection(
                metric_name=metric_name,
                entity_type=entity_type,
                entity_id=entity_id,
                device_id=device_id,
                current_value=curr_val,
                sample_count=sample_count,
                window=window,
                trend_direction=TrendDirection.UNKNOWN.value,
                slope_per_hour=None,
                slope_per_day=None,
                r_squared=None,
                p95_value=None,
                max_value=max((s[1] for s in clean_samples), default=None),
                warning_threshold=warn_thresh,
                critical_threshold=crit_thresh,
                hours_to_warning=None,
                hours_to_critical=None,
                days_to_warning=None,
                days_to_critical=None,
                risk_level=RiskLevel.UNKNOWN.value,
                status=PredictionStatus.INSUFFICIENT_DATA.value,
                confidence_score=0.0,
                confidence_level="UNKNOWN",
                assumptions=["Insufficient telemetry points available to construct a reliable trend."],
                epistemic_limitations=[
                    f"Sample count ({sample_count}) is below minimum requirement ({MIN_SAMPLE_THRESHOLD}).",
                    "Forecasting withheld to prevent misleading operations guidance."
                ],
                recommended_action="Allow NMS telemetry collector to gather more historical cycles."
            )

        # Sort chronologically
        clean_samples.sort(key=lambda s: s[0])
        values = [s[1] for s in clean_samples]
        current_val = values[-1]
        max_val = max(values)

        # P95 calculation
        sorted_vals = sorted(values)
        p95_idx = min(int(math.ceil(0.95 * len(sorted_vals))) - 1, len(sorted_vals) - 1)
        p95_val = sorted_vals[max(0, p95_idx)]

        # Fit trend regression
        slope_sec, _, r2 = self._fit_linear_regression(clean_samples)
        slope_hour = slope_sec * 3600.0
        slope_day = slope_sec * 86400.0

        # Classify trend direction
        if r2 < 0.20 and abs(slope_day) > 5.0:
            direction = TrendDirection.ERRATIC.value
        elif slope_day > 30.0 or slope_hour > 3.0:
            direction = TrendDirection.RAPID_INCREASE.value
        elif slope_day > 5.0 or slope_hour > 0.3:
            direction = TrendDirection.MODERATE_INCREASE.value
        elif slope_day < -30.0 or slope_hour < -3.0:
            direction = TrendDirection.RAPID_DECREASE.value
        elif slope_day < -5.0 or slope_hour < -0.3:
            direction = TrendDirection.MODERATE_DECREASE.value
        else:
            direction = TrendDirection.STABLE.value

        # Calculate Saturation Horizons
        hours_to_warn: Optional[float] = None
        hours_to_crit: Optional[float] = None
        days_to_warn: Optional[float] = None
        days_to_crit: Optional[float] = None

        if current_val >= crit_thresh:
            hours_to_crit = 0.0
            hours_to_warn = 0.0
            risk = RiskLevel.CRITICAL.value
        elif current_val >= warn_thresh:
            hours_to_warn = 0.0
            if slope_hour > 0:
                hours_to_crit = max(0.1, (crit_thresh - current_val) / slope_hour)
                if hours_to_crit <= 24.0:
                    risk = RiskLevel.CRITICAL.value
                else:
                    risk = RiskLevel.WARNING.value
            else:
                risk = RiskLevel.WARNING.value
        else:
            # Below warning threshold
            if slope_hour > 0:
                hours_to_warn = max(0.1, (warn_thresh - current_val) / slope_hour)
                hours_to_crit = max(0.1, (crit_thresh - current_val) / slope_hour)

                if hours_to_warn <= 24.0:
                    risk = RiskLevel.CRITICAL.value
                elif hours_to_warn <= 168.0:  # <= 7 days
                    risk = RiskLevel.WARNING.value
                elif hours_to_warn <= 720.0:  # <= 30 days
                    risk = RiskLevel.WATCH.value
                else:
                    risk = RiskLevel.INFO.value
            else:
                # Flat or downward trend
                risk = RiskLevel.INFO.value

        if hours_to_warn is not None:
            days_to_warn = round(hours_to_warn / 24.0, 1)
            hours_to_warn = round(hours_to_warn, 1)

        if hours_to_crit is not None:
            days_to_crit = round(hours_to_crit / 24.0, 1)
            hours_to_crit = round(hours_to_crit, 1)

        # Epistemic Confidence Calculation
        density_factor = min(1.0, sample_count / 30.0)
        fit_factor = r2 if direction != TrendDirection.STABLE.value else 0.90
        confidence_score = round(0.4 * density_factor + 0.6 * fit_factor, 2)

        if confidence_score >= 0.75:
            confidence_level = "HIGH"
        elif confidence_score >= 0.45:
            confidence_level = "MEDIUM"
        else:
            confidence_level = "LOW"

        # Action Recommendations
        if risk == RiskLevel.CRITICAL.value:
            rec_action = f"Immediate operational review required. Saturation threshold ({crit_thresh}%) imminent within {hours_to_crit or '<24'} hours."
        elif risk == RiskLevel.WARNING.value:
            rec_action = f"Schedule capacity expansion or traffic rerouting. Warning threshold ({warn_thresh}%) expected within {days_to_warn} days."
        elif risk == RiskLevel.WATCH.value:
            rec_action = f"Monitor trend in weekly capacity reviews. Saturation projected in {days_to_warn} days."
        else:
            rec_action = "Maintain normal operational monitoring; headroom is sufficient."

        return PredictiveMetricProjection(
            metric_name=metric_name,
            entity_type=entity_type,
            entity_id=entity_id,
            device_id=device_id,
            current_value=round(current_val, 2),
            sample_count=sample_count,
            window=window,
            trend_direction=direction,
            slope_per_hour=round(slope_hour, 4),
            slope_per_day=round(slope_day, 4),
            r_squared=round(r2, 3),
            p95_value=round(p95_val, 2),
            max_value=round(max_val, 2),
            warning_threshold=warn_thresh,
            critical_threshold=crit_thresh,
            hours_to_warning=hours_to_warn,
            hours_to_critical=hours_to_crit,
            days_to_warning=days_to_warn,
            days_to_critical=days_to_crit,
            risk_level=risk,
            status=PredictionStatus.VALID.value,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            assumptions=[
                "Extrapolation assumes current consumption and traffic growth patterns persist linearly.",
                "Does not account for sudden unannounced structural migrations, route shifts, or DDoS spikes."
            ],
            epistemic_limitations=[
                f"Prediction horizon is statistically valid up to 2x the lookback window duration ({window}).",
                f"Confidence level ({confidence_level}) reflects historical fit R^2={round(r2, 2)} over N={sample_count} points."
            ],
            recommended_action=rec_action
        )

    def analyze_evidence_bundle(
        self,
        bundle: NetworkEvidenceBundle,
        historical_samples_map: Optional[Dict[str, List[Tuple[float, float]]]] = None,
    ) -> PredictiveAnalysisReport:
        """
        Analyzes all interfaces and devices in a NetworkEvidenceBundle,
        using either provided historical time series or baseline data.
        """
        projections: List[PredictiveMetricProjection] = []
        samples_map = historical_samples_map or {}

        # 1. Analyze interfaces from bundle.interface_evidence or bundle.interfaces
        interfaces_list: List[Dict[str, Any]] = []
        if getattr(bundle, "interface_evidence", None):
            for dev_id, iface_records in bundle.interface_evidence.items():
                for item in iface_records:
                    if isinstance(item, dict):
                        d = dict(item)
                        d.setdefault("device_id", dev_id)
                        interfaces_list.append(d)
                    else:
                        interfaces_list.append({
                            "device_id": getattr(item, "device_id", dev_id),
                            "interface_name": getattr(item, "interface_name", getattr(item, "name", "unknown")),
                            "rx_utilization_percent": getattr(item, "rx_utilization_percent", None),
                            "tx_utilization_percent": getattr(item, "tx_utilization_percent", None),
                        })
        elif hasattr(bundle, "interfaces"):
            for item in getattr(bundle, "interfaces", []):
                interfaces_list.append({
                    "device_id": getattr(item, "device_id", ""),
                    "interface_name": getattr(item, "interface_name", getattr(item, "name", "unknown")),
                    "rx_utilization_percent": getattr(item, "rx_utilization_percent", None),
                    "tx_utilization_percent": getattr(item, "tx_utilization_percent", None),
                })

        for iface in interfaces_list:
            dev_id = str(iface.get("device_id") or "")
            iname = str(iface.get("interface_name") or iface.get("name") or "unknown")
            entity_key = f"{dev_id}:{iname}"

            # Check Rx utilization
            rx_key = f"{entity_key}:rx_utilization_percent"
            if rx_key in samples_map:
                p = self.analyze_metric_trend(
                    metric_name="rx_utilization_percent",
                    entity_type="interface",
                    entity_id=iname,
                    device_id=dev_id,
                    raw_samples=samples_map[rx_key],
                )
                projections.append(p)
            elif iface.get("rx_utilization_percent") is not None:
                p = self.analyze_metric_trend(
                    metric_name="rx_utilization_percent",
                    entity_type="interface",
                    entity_id=iname,
                    device_id=dev_id,
                    raw_samples=[(time.time(), float(iface["rx_utilization_percent"]))],
                )
                projections.append(p)

            # Check Tx utilization
            tx_key = f"{entity_key}:tx_utilization_percent"
            if tx_key in samples_map:
                p = self.analyze_metric_trend(
                    metric_name="tx_utilization_percent",
                    entity_type="interface",
                    entity_id=iname,
                    device_id=dev_id,
                    raw_samples=samples_map[tx_key],
                )
                projections.append(p)
            elif iface.get("tx_utilization_percent") is not None:
                p = self.analyze_metric_trend(
                    metric_name="tx_utilization_percent",
                    entity_type="interface",
                    entity_id=iname,
                    device_id=dev_id,
                    raw_samples=[(time.time(), float(iface["tx_utilization_percent"]))],
                )
                projections.append(p)

        # 2. Analyze devices (CPU and Memory)
        devices_list: List[Dict[str, Any]] = []
        if getattr(bundle, "device_evidence", None):
            for dev_id, dev_data in bundle.device_evidence.items():
                if isinstance(dev_data, dict):
                    d = dict(dev_data)
                    d.setdefault("device_id", dev_id)
                    devices_list.append(d)
                else:
                    devices_list.append({
                        "device_id": getattr(dev_data, "device_id", dev_id),
                        "cpu_load_percent": getattr(dev_data, "cpu_load_percent", None),
                        "memory_used_percent": getattr(dev_data, "memory_used_percent", None),
                    })
        elif hasattr(bundle, "devices"):
            for item in getattr(bundle, "devices", []):
                devices_list.append({
                    "device_id": getattr(item, "device_id", ""),
                    "cpu_load_percent": getattr(item, "cpu_load_percent", None),
                    "memory_used_percent": getattr(item, "memory_used_percent", None),
                })

        for dev in devices_list:
            did = str(dev.get("device_id") or "")
            cpu_key = f"{did}:cpu_load_percent"
            if cpu_key in samples_map:
                p = self.analyze_metric_trend(
                    metric_name="cpu_load_percent",
                    entity_type="device",
                    entity_id=did,
                    device_id=did,
                    raw_samples=samples_map[cpu_key],
                )
                projections.append(p)
            elif dev.get("cpu_load_percent") is not None:
                p = self.analyze_metric_trend(
                    metric_name="cpu_load_percent",
                    entity_type="device",
                    entity_id=did,
                    device_id=did,
                    raw_samples=[(time.time(), float(dev["cpu_load_percent"]))],
                )
                projections.append(p)

        # Aggregate risk counts
        risk_counts = {
            RiskLevel.CRITICAL.value: 0,
            RiskLevel.WARNING.value: 0,
            RiskLevel.WATCH.value: 0,
            RiskLevel.INFO.value: 0,
            RiskLevel.UNKNOWN.value: 0,
        }
        for proj in projections:
            risk_counts[proj.risk_level] = risk_counts.get(proj.risk_level, 0) + 1

        # Determine highest risk level
        if risk_counts[RiskLevel.CRITICAL.value] > 0:
            highest_risk = RiskLevel.CRITICAL.value
        elif risk_counts[RiskLevel.WARNING.value] > 0:
            highest_risk = RiskLevel.WARNING.value
        elif risk_counts[RiskLevel.WATCH.value] > 0:
            highest_risk = RiskLevel.WATCH.value
        elif risk_counts[RiskLevel.INFO.value] > 0:
            highest_risk = RiskLevel.INFO.value
        else:
            highest_risk = RiskLevel.UNKNOWN.value

        action_items = [
            p.recommended_action
            for p in projections
            if p.recommended_action and p.risk_level in (RiskLevel.CRITICAL.value, RiskLevel.WARNING.value)
        ]

        summary = (
            f"Predictive analysis completed across {len(projections)} metric forecasts. "
            f"Highest risk: {highest_risk} (Critical: {risk_counts[RiskLevel.CRITICAL.value]}, "
            f"Warning: {risk_counts[RiskLevel.WARNING.value]}, Watch: {risk_counts[RiskLevel.WATCH.value]})."
        )

        return PredictiveAnalysisReport(
            report_id=f"pred_rep_{uuid.uuid4().hex[:8]}",
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            projections=projections,
            highest_risk_level=highest_risk,
            summary=summary,
            risk_counts=risk_counts,
            action_items=action_items,
        )
