# AIRA OS — NETWORKING VI RESOURCE & CONCURRENCY MODEL
## Hardware-Conscious Engineering for 8 GB RAM / CPU-Only Operation (WP 6.0 / WP 6.17)

**Document Status:** WP 6.0 Accepted Specification

---

## 1. Host Hardware Constraints

- **Target System:** Lenovo ThinkPad X270
- **CPU:** Intel Core i7-7500U (2 physical cores / 4 logical threads @ 2.70 GHz)
- **Total Physical RAM:** 7.86 GB (~1.13 GB available during preflight alongside OS & IDE processes)
- **GPU:** Integrated Intel HD Graphics 620 (CPU-only AI inference)
- **Storage:** Local SSD hosting SQLite WAL databases (`topology.db`, `network_intelligence.db`)

---

## 2. Memory, CPU & I/O Budgets

| Subsystem | Hard Bound / Cap | Mechanism |
|---|---|---|
| **Evidence Bundle Cache** | Max `16` cached bundles, TTL `45s` | Bounded `OrderedDict` LRU storing compact normalized projections and snapshot IDs instead of raw multi-megabyte CLI strings |
| **Knowledge Graph Traversal** | `max_depth = 8` (ceiling `16`), `max_visited_nodes = 500` (ceiling `2,000`) | Iterative BFS/DFS (`collections.deque`) with visited-set cycle protection; zero recursive stack frames |
| **Path Reconstruction** | `max_hops = 16`, `max_ecmp_branches = 8`, `max_recursion_depth = 16` | Reuses `UnifiedRouteParser` + bounded `RoutePathEvaluator` |
| **Concurrent Investigations** | Max `2` concurrent live-collecting investigations (`asyncio.Semaphore(2)`) | Prevents SSH/CPU saturation on the 2-core i7-7500U while keepingNMS background polling responsive |
| **Investigation Timeout** | `15.0s` deterministic / `25.0s` with LLM, cooperative `cancel_event` checked between pipeline stages | `asyncio.wait_for` + `InvestigationCancellationToken` |
| **SQLite Retention (`network_intelligence.db`)** | Max `500` investigations, `2,000` anomalies, `1,000` active baselines, expired contexts purged automatically | Indexed `DELETE` pruning inside `NetworkIntelligenceStore` write lock |
| **LLM Prompt Payload** | Max `6,000` chars (~`1,500` tokens), `tools=None`, `8.0s` timeout | Selective invocation (only on explicit user NL investigation when `enable_llm=True`); zero background polling LLM calls |
| **Anomaly & Baseline Math** | Pure Python `statistics.median` + MAD + EWMA over bounded window (`max_points = 60`) | Zero PyTorch / TensorFlow / scikit-learn imports in Networking VI |

---

## 3. Non-Interference with NMS & Topology Engines

1. **Zero Duplicate Background Pollers:** Networking VI adds **zero** autonomous background SSH polling threads or tasks. Continuous telemetry remains the sole responsibility of `NmsEngine` / `HardenedNmsScheduler`.
2. **Per-Device Single-Flight Coordination:** `NmsEngine.poll_single_device()` acquires a per-device `asyncio.Lock` (aligned with `DevicePollCoordinator`), ensuring manual diagnostics and scheduled NMS cycles never open concurrent competing polls to the same router.
3. **Failure Isolation:** Every analyzer in Layer 4 catches domain exceptions locally, records structured warnings in `bundle.collection_gaps` or `report.limitations`, and degrades gracefully to partial results—ensuring an investigation error can never crash FastAPI, `NmsEngine`, or `TopologyEngine`.
