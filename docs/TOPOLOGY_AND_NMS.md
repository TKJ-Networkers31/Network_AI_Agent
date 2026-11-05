# AIRA OS — TOPOLOGY AND REAL-TIME NMS SPECIFICATION
## Device-Centric Graph Fabric & Accurate Counter Delta Bandwidth Telemetry

**Version:** 1.0.0  
**Status:** Canonical Topology & NMS Specification  

---

## 1. Device-Centric Topology Model

A central requirement of AIRA OS is that **one physical or virtual device is always represented as one node**, regardless of how many network interfaces or ports it possesses.

### 1.1 Structural Invariant
- **Device Entity (Node):**
  - Contains device identity, management IP, vendor, model, and availability status (`UP`, `DEGRADED`, `DOWN`).
  - Ports are NOT separate floating nodes.
- **Interface Entities:**
  - Child entities attached to the parent device node (e.g. `ether1`, `ether2`, `sfp-plus1`).
- **Connection Entity (Edge):**
  - Links represent independent physical or logical connections connecting a specific `(source_device_id, source_interface)` to `(target_device_id, target_interface)`.
  - Multiple distinct links between the same pair of devices (e.g. dual trunk links or LAG members) are rendered as separate parallel edges with their respective interface endpoints.

```
+-------------------------------------------------------------------------------+
|                               CORRECT MODEL                                   |
|                                                                               |
|       [ Router A ] ════════ ether1 ──────── ether1 ════════ [ Router B ]      |
|            ║                                                                  |
|          ether2                                                               |
|            │                                                                  |
|          ether1                                                               |
|            ║                                                                  |
|       [ Switch A ] ════════ ether24 ─────── eth0 ═══════════ [ Server A ]     |
+-------------------------------------------------------------------------------+
```

---

## 2. Real-Time NMS & Telemetry Architecture

AIRA OS provides continuous, asynchronous background telemetry without forcing the engineer to manually refresh the browser.

### 2.1 Accurate Counter Delta Bandwidth Calculation

$$\text{Bandwidth (bps)} = \frac{(\text{Current In/Out Octets} - \text{Previous In/Out Octets}) \times 8}{\text{Current Timestamp} - \text{Previous Timestamp}}$$

#### Rollover & Reset Handling (`calculate_traffic_rate` in `core/nms_models.py`):
1. **Normal Monotonic Increase ($C_{\text{curr}} \ge C_{\text{prev}}$):**
   $$\Delta_{\text{octets}} = C_{\text{curr}} - C_{\text{prev}}$$
2. **Counter Wrap ($C_{\text{curr}} < C_{\text{prev}}$):**
   - *64-bit Counter Wraparound:* If $C_{\text{prev}}$ is near $2^{64}-1$, wrap is calculated via $(2^{64} - C_{\text{prev}}) + C_{\text{curr}} + 1$.
   - *32-bit Counter Wraparound:* If $C_{\text{prev}} \ge 2.14\text{ GB}$ ($2^{31}$), potential wrap $(2^{32} - C_{\text{prev}}) + C_{\text{curr}} + 1$ is verified against port speed capacity.
   - *Device Reboot or Counter Reset:* If $C_{\text{prev}}$ was low ($< 2.14\text{ GB}$) and dropped, or the calculated rate exceeds physical interface capacity ($> 1.5 \times \text{speed}$), the delta is identified as a reboot/reset and set to zero rather than generating an artificial multi-terabit spike.
3. **No Fake Zeros / Honest Gaps:**
   - On the first sample ($C_{\text{prev}} = \text{None}$) or during polling delays, rate is recorded as `None` (gap) rather than $0.0\text{ bps}$.

---

## 3. Real-Time Telemetry Streaming

- **Telemetry Pipeline:** Polling workers push metrics into SQLite `nms_device_metrics` and `nms_interface_metrics`.
- **WebSocket Broadcast:** The backend pushes `nms_device_status` and `nms_cycle_completed` events over `/ws/nms` and the WebSocket Event Bus bridge.
- **Live Modal Telemetry:** When an engineer inspects a device via `DeviceDetailModal.jsx`, an active polling cycle ensures CPU, RAM, and interface throughput curves update dynamically without closing or manually refreshing the modal.
