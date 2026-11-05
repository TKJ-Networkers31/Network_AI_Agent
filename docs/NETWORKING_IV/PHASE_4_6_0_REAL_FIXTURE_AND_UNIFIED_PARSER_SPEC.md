# AIRA OS — Work Package 4.6.0 Specification
## Real-Device Fixture & Unified Route Parser Engineering Specification

**Document Version:** 1.0.0  
**Phase:** 4.6 (Route Analytics & Network Path Intelligence)  
**Work Package:** WP 4.6.0  
**Status:** PROPOSED & READY FOR APPROVAL  
**Author:** Senior Network Automation Architect, MikroTik RouterOS Engineer, Software Reliability Engineer  
**Security & Integrity Level:** Read-Only, Non-Mutating, Non-Destructive  

---

## 1. Executive Summary & Objective

The Phase 4.6 Architecture Audit identified that AIRA OS currently maintains two separate, divergent route parsers:
1. `parse_routeros_routes` (located in `AIRA_ECOSYSTEM/agents/akane/network_tools.py`)
2. `parse_mikrotik_routes` (located in `AIRA_ECOSYSTEM/core/topology_parsers.py`)

These parsers produce incompatible output schemas, fail to populate the canonical `NormalizedRoute` model, and suffer from ten distinct functional and semantic defects (D1–D10).

The objective of **Work Package 4.6.0** is to:
1. Provide a single, authoritative, high-performance, line-continuation-aware **Unified Route Parser** (`UnifiedRouteParser`) capable of parsing both RouterOS v6 and RouterOS v7 route outputs in tabular, detail, and compact formats.
2. Standardize on the extended `NormalizedRoute` dataclass as the single source of truth for routing state.
3. Systematically eliminate defects D1 through D10 with comprehensive regression test coverage.
4. Define exact real-device fixture capture requirements and establish backwards-compatible legacy adapter shims for zero breaking changes across existing modules.

---

## 2. RouterOS v6 vs. v7 Routing Architecture & Grammar Analysis

RouterOS changed its routing engine and CLI syntax fundamentally between v6 and v7:

### 2.1 RouterOS v6 Routing Engine
- **Command:** `/ip route print detail` (or tabular `/ip route print`)
- **Flags:** Space-separated uppercase and lowercase flag characters printed in column 1 (e.g., ` #   DST-ADDRESS        PREF-SRC        GATEWAY            DISTANCE`).
- **Flags Grammar:**
  - Column 0: Row index (e.g., `0`, `1`, `2`)
  - Column 1–4: Flags:
    - `X`: disabled
    - `A`: active
    - `D`: dynamic
    - `C`: connect
    - `S`: static
    - `r`: rip, `b`: bgp, `o`: ospf, `m`: mme
    - `B`: blackhole, `U`: unreachable, `P`: prohibit
- **Detail Output Syntax:**
  ```text
  0 A S  dst-address=0.0.0.0/0 gateway=10.66.38.1 gateway-status=10.66.38.1 reachable via ether1 distance=1 scope=30 target-scope=10 
  1 ADC  dst-address=10.66.38.0/24 pref-src=10.66.38.30 gateway=ether1 gateway-status=ether1 reachable distance=0 scope=10 
  ```
  *Note:* In v6, flags may appear either on the line header (e.g. `0 A S`) or inside the key-value body (`flags=X`). Flags like `A` and `S` can be separated by spaces, throwing off naive split-based parsers.

### 2.2 RouterOS v7 Routing Engine
- **Routing Architecture:** Complete redesign around a Linux routing table core and modular routing engines.
- **Commands:**
  - `/ip route print detail`
  - `/routing route print detail` (includes full protocol RIB attributes)
  - `/ip route print`
- **Flags Grammar:** Compact concatenated flags string (e.g. `DAc`, `DAo`, `DAs`, `As`, `I`):
  - `D`: dynamic
  - `X`: disabled
  - `I`: inactive (crucial: replaces absence of `A` with an explicit flag in v7)
  - `A`: active
  - `c`: connect (lowercase)
  - `s`: static (lowercase)
  - `y`: copy
  - `b`: bgp
  - `o`: ospf
  - `r`: rip
  - `v`: vpn
  - `h`: blackhole, `d`: drop, `u`: unreachable, `p`: prohibit
- **Detail Output Syntax & Line Wrapping:**
  RouterOS v7 detail output wraps long attributes onto subsequent lines indented by whitespace without repetition of the row prefix:
  ```text
  0  As  dst-address=0.0.0.0/0 routing-table=main gateway=10.66.38.1 
         immediate-gw=10.66.38.1%ether1 distance=1 scope=30 target-scope=10 
         suppress-hw-offload=no 

  1  DAc dst-address=10.66.38.0/24 routing-table=main gateway=ether1 
         immediate-gw=ether1 distance=0 scope=10 suppress-hw-offload=no 
         local-address=10.66.38.30%ether1 
  ```

---

## 3. Defect Remediation Specification (D1–D10)

The Unified Parser must resolve all 10 verified architectural defects:

| Defect ID | Severity | Root Cause in Legacy Code | Unified Parser Resolution |
| :--- | :--- | :--- | :--- |
| **D1** | **CRITICAL** | Tabular parser (`parse_mikrotik_routes`) splits line by whitespace; flags with internal spaces (e.g. `A S`) shift column indices, causing `dst_address='S'` and `gateway='0.0.0.0'`. | Columnar/positional regex or fixed header offset detection that groups columns `[Index] [Flags] [Destination] [Gateway]`. |
| **D2** | **HIGH** | `parse_mikrotik_routes` checked uppercase `'C' in flags` only. In v7, connected routes have lowercase `'c'` (`DAc`), causing connected routes to be classified as unknown. | Case-insensitive flag mapping: normalize flags to an explicit set containing both v6 and v7 flag character mappings. |
| **D3** | **CRITICAL** | `parse_routeros_routes` parsed key-value tokens only and dropped leading flag tokens (`0 A S`), marking active static routes as `active=False`. | Parser explicitly extracts the record header (`^\s*(\d+)\s+([A-Za-z]+|\s+)`) before key-value tokenization, accurately capturing `active` from header flags. |
| **D4** | **CRITICAL** | `parse_routeros_routes` assumed each route was exactly one physical line. In v7, lines wrap with indentation, dropping critical attributes like `distance` and `gateway-status`. | Pre-processing fold pass: merge lines beginning with leading whitespace (continuation lines) into the preceding route block. |
| **D5** | **MEDIUM** | On recursive routes, `gateway-status` contains `"recursive via 192.168.1.1 ether1"`. Legacy regex grabbed `192.168.1.1` as the interface name. | Regex parses structured gateway-status: distinguish `immediate_gw`, `recursive_via_ip`, and `egress_interface`. |
| **D6** | **CRITICAL** | `mikrotik_diagnose_route` Longest Prefix Match (LPM) iterated all parsed routes without checking `route.active`, returning disabled/inactive routes as the best path. | Strict LPM filtering: LPM engine only considers active routes (`active=True`) for forwarding decisions (FIB), with an explicit parameter `include_inactive=False`. |
| **D7** | **HIGH** | Equal-Cost Multi-Path (ECMP) routes with multiple gateways (`gateway=10.0.0.1,10.0.0.2` or multiple next-hop lines) were truncated to the first gateway or caused parse errors. | Multi-gateway support: `gateways: List[str]` and `immediate_gateways: List[str]` populated with all next-hops. |
| **D8** | **MEDIUM** | `scope` and `target-scope` values were ignored, preventing detection of invalid or unresolvable recursive static routes. | `scope` and `target_scope` fields parsed as integers and populated in `NormalizedRoute`. |
| **D9** | **MEDIUM** | `routing-table` / `routing-mark` attribute ignored; VRF routes leaked into default route lookup. | `routing_table` / `vrf` attribute parsed (defaulting to `"main"`). |
| **D10** | **HIGH** | Host routes (`192.168.1.1`) or unmasked subnets produced inconsistent string representations (`192.168.1.1` vs `192.168.1.1/32`), breaking dict lookups. | Normalization pass: all destinations converted using `ipaddress.ip_network(strict=False)` to canonical CIDR format. |

---

## 4. Flag Matrix & Normalization Specification

The parser must map raw RouterOS flag strings to standard boolean attributes and `RouteProtocol` enum values:

```
+----------------------------------------------------------------------------------------------------+
| RouterOS Flag | v6 Meaning         | v7 Meaning         | Normalized Attribute / Enum              |
+---------------+--------------------+--------------------+------------------------------------------+
| A             | Active             | Active             | is_active = True                         |
| I             | (none)             | Inactive           | is_active = False                        |
| X             | Disabled           | Disabled           | is_disabled = True, is_active = False    |
| D             | Dynamic            | Dynamic            | is_dynamic = True                        |
| C or c        | Connect            | Connect            | protocol = RouteProtocol.CONNECTED       |
| S or s        | Static             | Static             | protocol = RouteProtocol.STATIC          |
| O or o        | OSPF               | OSPF               | protocol = RouteProtocol.OSPF            |
| B or b        | BGP                | BGP                | protocol = RouteProtocol.BGP             |
| R or r        | RIP                | RIP                | protocol = RouteProtocol.RIP             |
| H or h        | Blackhole          | Blackhole          | route_type = RouteType.BLACKHOLE         |
| U or u        | Unreachable        | Unreachable        | route_type = RouteType.UNREACHABLE       |
| P or p        | Prohibit           | Prohibit           | route_type = RouteType.PROHIBIT          |
+----------------------------------------------------------------------------------------------------+
```

### Protocol Precedence Resolution
If multiple protocol flags appear (rare, e.g. `D A c`), the protocol flag takes precedence:
1. `c` / `C` $\rightarrow$ `CONNECTED`
2. `s` / `S` $\rightarrow$ `STATIC`
3. `o` / `O` $\rightarrow$ `OSPF`
4. `b` / `B` $\rightarrow$ `BGP`
5. `r` / `R` $\rightarrow$ `RIP`
6. If no protocol flag is present, default to `STATIC` if non-dynamic, or `UNKNOWN` if dynamic.

---

## 5. Canonical Data Model: Extended `NormalizedRoute`

The parser will emit instances of `NormalizedRoute` (located in `AIRA_ECOSYSTEM/core/canonical_network.py`):

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import ipaddress

class RouteProtocol(str, Enum):
    CONNECTED = "connected"
    STATIC = "static"
    OSPF = "ospf"
    BGP = "bgp"
    RIP = "rip"
    MME = "mme"
    VPN = "vpn"
    UNKNOWN = "unknown"

class RouteType(str, Enum):
    UNICAST = "unicast"
    BLACKHOLE = "blackhole"
    UNREACHABLE = "unreachable"
    PROHIBIT = "prohibit"

@dataclass
class NormalizedRoute:
    # Addressing & Identification
    destination: str                 # Canonical CIDR, e.g. "192.168.1.0/24" or "0.0.0.0/0"
    prefix_length: int               # e.g. 24 or 0
    routing_table: str = "main"      # Default table is "main"
    
    # Next-Hop Forwarding State (FIB)
    gateway: Optional[str] = None    # Next-hop IP address or interface, e.g. "10.66.38.1"
    gateways: List[str] = field(default_factory=list) # Multi-gateway support (ECMP)
    immediate_gw: Optional[str] = None # Resolved physical next-hop (v7 immediate-gw)
    interface: Optional[str] = None  # Egress interface name, e.g. "ether1"
    pref_src: Optional[str] = None   # Preferred source IP
    
    # Metrics & Administrative Distance
    distance: int = 1                # Admin distance: connected=0, static=1, ospf=110, etc.
    metric: Optional[int] = None     # Protocol metric / cost
    scope: Optional[int] = None      # Scope for recursive next-hop resolution
    target_scope: Optional[int] = None # Target-scope for recursive resolution
    
    # Operational Status
    active: bool = True              # Active in FIB (flag 'A' and not 'I' and not 'X')
    dynamic: bool = False            # Dynamic flag ('D')
    disabled: bool = False           # Disabled flag ('X')
    protocol: RouteProtocol = RouteProtocol.UNKNOWN
    route_type: RouteType = RouteType.UNICAST
    
    # Metadata & Raw Provenance
    raw_flags: str = ""              # Original flag string from router, e.g. "DAc", "0 A S"
    device_id: Optional[str] = None  # Canonical device identifier
    routeros_version: Optional[int] = None # 6 or 7
    raw_attributes: Dict[str, Any] = field(default_factory=dict) # Full parsed KV dict

    def is_default_route(self) -> bool:
        return self.destination == "0.0.0.0/0" or self.destination == "::/0"

    def matches_address(self, ip_str: str) -> bool:
        """Evaluates whether an IP matches this route prefix."""
        try:
            target = ipaddress.ip_address(ip_str)
            net = ipaddress.ip_network(self.destination, strict=False)
            return target in net
        except ValueError:
            return False

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Adapter for backward compatibility with legacy parsers."""
        return {
            "dst_address": self.destination,
            "pref_src": self.pref_src,
            "gateway": self.gateway,
            "gateway_status": self.immediate_gw or self.gateway,
            "distance": self.distance,
            "scope": self.scope,
            "target_scope": self.target_scope,
            "active": self.active,
            "dynamic": self.dynamic,
            "connect": self.protocol == RouteProtocol.CONNECTED,
            "static": self.protocol == RouteProtocol.STATIC,
            "ospf": self.protocol == RouteProtocol.OSPF,
            "bgp": self.protocol == RouteProtocol.BGP,
            "disabled": self.disabled,
            "interface": self.interface,
            "raw_flags": self.raw_flags,
            "routing_table": self.routing_table,
        }
```

---

## 6. Architecture & Implementation of `UnifiedRouteParser`

### 6.1 Class Hierarchy and Module Placement
The parser will be placed in a dedicated module:
`AIRA_ECOSYSTEM/core/routing/unified_route_parser.py`

### 6.2 Line-Continuation & Block-Folding Engine
Before tokenizing attributes, the parser executes a folding pass:
```python
def _fold_continuation_lines(raw_text: str) -> List[str]:
    """
    Folds multi-line detail outputs into single logical route records.
    Lines starting with whitespace or without a row index are folded into the previous row.
    """
    logical_lines: List[str] = []
    current_block: List[str] = []
    
    for line in raw_text.splitlines():
        trimmed = line.rstrip()
        if not trimmed:
            if current_block:
                logical_lines.append(" ".join(current_block))
                current_block = []
            continue
            
        # Check if line begins a new record: starts with optional space + digit + space
        if re.match(r"^\s*\d+\s+", trimmed):
            if current_block:
                logical_lines.append(" ".join(current_block))
                current_block = []
            current_block.append(trimmed.strip())
        else:
            # Continuation line
            if current_block:
                current_block.append(trimmed.strip())
            else:
                # Banner or header line before records
                pass
                
    if current_block:
        logical_lines.append(" ".join(current_block))
        
    return logical_lines
```

### 6.3 Dual-Format Grammar Processor
The parser supports two input formats:
1. **Detail Format (`print detail`):**
   - Extracts leading row index and flag block.
   - Extracts all `key=value` pairs into a structured dictionary.
   - Parses `immediate-gw`, `gateway-status`, `scope`, and `target-scope`.
2. **Compact Tabular Format (`print`):**
   - Matches header column widths or uses anchor regex `^\s*(\d+)\s+([A-Za-z\s]{1,6})\s+([0-9\.\/]+)\s+([0-9\.\/]+|[\w\-]+)`.
   - Safely parses whitespace-padded flags without column slippage.

---

## 7. Backwards-Compatible Adapter Shims

Existing modules MUST NOT break during or after migration:

### 7.1 Adapter 1: `AIRA_ECOSYSTEM/agents/akane/network_tools.py`
```python
def parse_routeros_routes(raw_output: str) -> List[Dict[str, Any]]:
    """
    Backwards-compatible wrapper delegating to UnifiedRouteParser.
    Returns list of dictionaries conforming to legacy ParsedRoute schema.
    """
    from core.routing.unified_route_parser import UnifiedRouteParser
    parser = UnifiedRouteParser()
    normalized_routes = parser.parse(raw_output)
    return [r.to_legacy_dict() for r in normalized_routes]
```

### 7.2 Adapter 2: `AIRA_ECOSYSTEM/core/topology_parsers.py`
```python
def parse_mikrotik_routes(raw_output: str) -> List[Dict[str, Any]]:
    """
    Backwards-compatible wrapper delegating to UnifiedRouteParser.
    Returns list of dictionaries conforming to legacy topology route schema.
    """
    from core.routing.unified_route_parser import UnifiedRouteParser
    parser = UnifiedRouteParser()
    normalized_routes = parser.parse(raw_output)
    return [
        {
            "dst_address": r.destination,
            "gateway_ip": r.gateway if (r.gateway and not r.protocol == RouteProtocol.CONNECTED) else None,
            "interface": r.interface or (r.gateway if r.protocol == RouteProtocol.CONNECTED else None),
            "distance": r.distance,
            "scope": r.scope,
            "target_scope": r.target_scope,
            "active": r.active,
            "flags": r.raw_flags,
            "protocol": r.protocol.value,
        }
        for r in normalized_routes
    ]
```

---

## 8. Real-Device Fixture Capture Specification

In accordance with approved Decision 1:
- Real-device fixtures are **strictly mandatory** for WP 4.6.0 acceptance.
- Synthetic fixtures are **prohibited** as evidence of parser correctness.
- Fixtures must be captured from actual RouterOS devices, sanitized of sensitive credentials, and saved under `AIRA_ECOSYSTEM/tests/fixtures/routes/`.

### 8.1 Required Fixture Files

| Fixture Filename | Device Platform | Command Output | Target Cases Covered |
| :--- | :--- | :--- | :--- |
| `v6_ip_route_detail_standard.txt` | RouterOS v6 (hAP ac lite / RB952Ui) | `/ip route print detail` | Static routes, connected routes, default route, flag extraction (D3), recursive gateways (D5). |
| `v6_ip_route_tabular.txt` | RouterOS v6 (hAP ac lite / RB952Ui) | `/ip route print` | Space-separated tabular flags (`A S`, `ADC`), column alignment (D1). |
| `v6_ip_route_ecmp_detail.txt` | RouterOS v6 | `/ip route print detail` | Multi-gateway ECMP routes (D7). |
| `v7_ip_route_detail_standard.txt` | RouterOS v7 (CHR v7.23.8) | `/ip route print detail` | Compact flags (`DAc`, `As`), line-continuation folding (D4), lowercase flags (D2). |
| `v7_ip_route_tabular.txt` | RouterOS v7 (CHR v7.23.8) | `/ip route print` | Compact tabular output, inactive flag `I` (D6). |
| `v7_routing_route_detail.txt` | RouterOS v7 (CHR v7.23.8) | `/routing route print detail` | RIB table attributes, BGP/OSPF protocol attributes. |

### 8.2 Sanitization Protocol
1. Replace private or lab management passwords with placeholder strings (passwords should not exist in route outputs, but verify).
2. If public IP addresses are present that belong to private lab infrastructure, map them into RFC 5737 documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`) while preserving exact subnet bitmasks.
3. Preserve all whitespace, line breaks, indentation, and flag characters verbatim.

---

## 9. Comprehensive Acceptance Test Plan for WP 4.6.0

A dedicated test suite `AIRA_ECOSYSTEM/tests/test_unified_route_parser.py` will be created with minimum 15 unit tests:

1. `test_v6_detail_parsing_flags_extracted`: Proves `0 A S` sets `active=True`, `protocol=STATIC`, resolving D3.
2. `test_v6_tabular_spaced_flags_alignment`: Proves `0 A S 0.0.0.0/0` correctly parses destination `0.0.0.0/0`, resolving D1.
3. `test_v7_detail_line_continuation_folding`: Proves multi-line wrapped routes retain distance and gateway-status, resolving D4.
4. `test_v7_compact_lowercase_flags`: Proves `DAc` sets `active=True`, `protocol=CONNECTED`, resolving D2.
5. `test_v6_recursive_gateway_status`: Proves IP address is not confused with interface name, resolving D5.
6. `test_inactive_route_not_selected_by_fib`: Proves `active=False` routes are rejected by LPM, resolving D6.
7. `test_ecmp_multi_gateway_extraction`: Proves multiple next-hops are parsed into `gateways`, resolving D7.
8. `test_scope_and_target_scope_populated`: Proves integer parsing of scopes, resolving D8.
9. `test_vrf_routing_table_attribution`: Proves non-default routing tables are parsed, resolving D9.
10. `test_destination_cidr_normalization`: Proves bare IP addresses become `/32` CIDRs, resolving D10.
11. `test_legacy_parse_routeros_routes_backward_compatibility`: Proves existing callers receive expected dictionary schema.
12. `test_legacy_parse_mikrotik_routes_backward_compatibility`: Proves existing topology callers receive expected dictionary schema.
13. `test_empty_and_garbage_input_handling`: Proves graceful handling of empty strings or banner-only outputs.
14. `test_performance_5000_routes`: Proves 5,000 routes parse in $< 350\text{ ms}$ with zero memory leaks.
15. `test_zero_mutation_guarantee`: Proves parser executes pure functions with zero I/O or state modification.

---

## 10. Work Package Acceptance Criteria

WP 4.6.0 shall be considered complete and ready for acceptance only when:
- [ ] Real-device fixture captures for RouterOS v7 (CHR) are committed to `tests/fixtures/routes/v7_*.txt`.
- [ ] Real-device fixture captures for RouterOS v6 (hAP ac lite) are committed (or explicitly documented under validation gap until physical lab reachability is restored).
- [ ] `UnifiedRouteParser` is implemented and passes all 15 test cases in `test_unified_route_parser.py`.
- [ ] Legacy adapter wrappers pass all existing regression tests (`test_canonical_network.py`, `test_phase6_diagnostic_validation.py`, `test_automatic_orchestration.py`).
- [ ] Live database `topology.db` remains untouched with baseline hash `9729b243a47b3e8388bbe67dbcb78db002ffbe3d70a1736318bbbdaa879f0fba`.
