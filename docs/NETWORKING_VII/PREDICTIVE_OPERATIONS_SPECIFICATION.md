# AIRA OS — NETWORKING VII
# PREDICTIVE OPERATIONS ENGINE SPECIFICATION (WP 7.1)

**Module:** `AIRA_ECOSYSTEM/core/operations/predictive_engine.py`  
**Data Models:** `AIRA_ECOSYSTEM/core/operations/models.py`  
**Phase:** Phase B — Predictive Operations Engine  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Operational Need

Network management has historically been reactive: alarms fire after interfaces drop packets, after CPUs hit 100%, or after transit circuits saturate.

The **Predictive Operations Engine** provides forward-looking operational intelligence by analyzing metric acceleration over multi-window timeframes (`1h`, `6h`, `24h`, `7d`, `30d`), computing robust linear trend regressions, estimating time-to-saturation horizons ($T_{80}$ and $T_{95}$), and categorizing operational risk into `INFO`, `WATCH`, `WARNING`, and `CRITICAL`.

---

## 2. Epistemic Principles & Rules

1. **No Hallucination / No Prescience:** Projections are mathematical extrapolations of observed trends. They represent *what will occur if present trajectories continue without intervention*. Every projection explicitly includes assumptions and limitations.
2. **Missing Telemetry Rule:** If a metric value is `None` (due to polling timeout, device reboot, or unmonitored interval), it remains `None`. Converting `None` to `0.0` is strictly forbidden because it would artificially pull down regression slopes and mask saturation risks.
3. **Sample Sufficiency Floor:** If the number of valid samples $N < 10$, the engine withholds forecasting, returning status `INSUFFICIENT_DATA`, `RiskLevel.UNKNOWN`, and `confidence_score = 0.0`.
4. **Outlier Filtering & MAD:** Metric series are checked against Median Absolute Deviation (MAD) baselines to prevent isolated telemetry spikes from skewing long-term slopes.

---

## 3. Mathematical Formulations

### 3.1. Normalized Linear Regression
Given $N$ samples $(t_i, y_i)$, timestamps are normalized relative to $t_0$:
$$x_i = t_i - t_0$$
The slope per second $m$ is computed via least squares:
$$m = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}{\sum (x_i - \bar{x})^2}$$
Converted to operational units:
$$\text{slope\_per\_hour} = m \times 3600$$
$$\text{slope\_per\_day} = m \times 86400$$

### 3.2. Goodness-of-Fit ($R^2$)
$$R^2 = \frac{\left[\sum (x_i - \bar{x})(y_i - \bar{y})\right]^2}{\sum (x_i - \bar{x})^2 \sum (y_i - \bar{y})^2}$$
Bounded in $[0.0, 1.0]$. If $y_i$ is constant, $R^2 = 1.0$ and slope $= 0.0$.

### 3.3. Saturation Horizons ($T_{\text{threshold}}$)
For warning threshold $W$ (e.g. 80%) and critical threshold $C$ (e.g. 95%):
If current value $y_{\text{curr}} < W$ and $\text{slope\_per\_hour} > 0$:
$$T_{\text{warn}} = \frac{W - y_{\text{curr}}}{\text{slope\_per\_hour}} \quad [\text{hours}]$$
$$T_{\text{crit}} = \frac{C - y_{\text{curr}}}{\text{slope\_per\_hour}} \quad [\text{hours}]$$
If $\text{slope\_per\_hour} \le 0$, horizons are `None` (headroom is stable or expanding).

---

## 4. Risk Classification Matrix

| Current State / Horizon | Risk Level | Operational Meaning | Recommended Action |
| :--- | :--- | :--- | :--- |
| Current $\ge C$ (e.g. $\ge 95\%$) OR $T_{\text{crit}} \le 24$ hours | `CRITICAL` | Severe saturation imminent or active | Immediate operational intervention or traffic reroute. |
| Current $\ge W$ (e.g. $\ge 80\%$) OR $T_{\text{warn}} \le 7$ days (168h) | `WARNING` | Rapid consumption, breach expected within a week | Schedule capacity expansion or adjust QoS policies. |
| $T_{\text{warn}} \le 30$ days (720h) | `WATCH` | Moderate upward trend | Review in weekly capacity planning sessions. |
| $T_{\text{warn}} > 30$ days OR slope $\le 0$ | `INFO` | Adequate capacity headroom | Normal routine monitoring. |
| Sample count $N < 10$ or high noise | `UNKNOWN` | Insufficient telemetry | Collect additional polling cycles. |
