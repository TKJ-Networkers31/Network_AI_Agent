# AIRA OS — NETWORKING VII
# NETWORK CHANGE IMPACT INTELLIGENCE SPECIFICATION (WP 7.2)

**Module:** `AIRA_ECOSYSTEM/core/operations/change_impact_engine.py`  
**Data Models:** `AIRA_ECOSYSTEM/core/operations/models.py`  
**Phase:** Phase C — Network Change Impact Intelligence  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Operational Problem

Executing network maintenance (e.g. interface shutdowns, route changes, VLAN migrations, router firmware reboots) without verified blast-radius modeling frequently leads to unexpected service outages, routing blackholes, and secondary link saturation.

The **Change Impact Intelligence Engine** performs in-memory analytical simulations of proposed maintenance actions against a deep-cloned `NetworkKnowledgeGraph`, evaluating:
1. Directly and indirectly severed devices and subnets.
2. Loss of high-availability (HA) redundancy and creation of single points of failure (SPOFs).
3. Secondary transit link traffic load shifts.
4. Preflight validation checklists and deterministic rollback commands.

---

## 2. In-Memory Isolation & Safety Guarantees

1. **Zero Live Mutation:** Live RouterOS devices (`CHR`, `R-1`) are never touched. No configuration or admin state changes are sent across SSH/API.
2. **Zero Database Mutation:** The production `topology.db` and live `NetworkKnowledgeGraph` are untouched. All graph alterations occur exclusively on an in-memory clone (`copy.deepcopy(graph)`).
3. **Explicit Epistemic Flag:** Every generated report has `is_simulation = True`.

---

## 3. Supported Change Scenarios

| Scenario Code | Target Entity | Simulated Modification | Evaluated Impact |
| :--- | :--- | :--- | :--- |
| `INTERFACE_DOWN` | Interface name (e.g. `ether1`) | Disables interface node, removes physical/L2/L3 edges passing through interface | Peer device isolation, subnet severance, secondary link load shift |
| `ROUTE_WITHDRAWAL` | Destination CIDR (e.g. `10.0.0.0/16`) | Removes route node, breaks next-hop resolution | L3 transit reachability loss, blackholing |
| `VLAN_REMOVE` | VLAN ID / Subnet | Removes VLAN and member ports | Inter-VLAN routing failure, client endpoint isolation |
| `DEVICE_REBOOT` | Device ID (e.g. `R-1`) | Severs all inbound and outbound edges from device | Complete multi-hop downstream dependency cascade |

---

## 4. Blast Radius & Secondary Link Load Shift

When a primary transit link is severed:
1. Surviving alternate paths to core/WAN are enumerated.
2. If no alternate path exists, the device is flagged as `ISOLATED` (Severity `CRITICAL`).
3. If an alternate path exists:
   - Primary link traffic volume is analytically shifted to the secondary link.
   - Projected total rate: $R_{\text{projected}} = R_{\text{secondary\_baseline}} + R_{\text{primary\_shifted}}$.
   - If $R_{\text{projected}} > 0.80 \times \text{Capacity}_{\text{secondary}}$, a secondary link saturation warning is flagged.
