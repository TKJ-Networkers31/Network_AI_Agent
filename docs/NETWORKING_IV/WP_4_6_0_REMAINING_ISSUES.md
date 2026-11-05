# AIRA OS — WORK PACKAGE 4.6.0 REMAINING ISSUES & VALIDATION GAP REGISTER

**Document Version:** 1.0.0  
**Phase:** 4.6 (Route Analytics & Network Path Intelligence)  
**Work Package:** WP 4.6.0  
**Date:** November 3, 2026  
**Auditor:** Principal Network Automation Architect & Independent QA Auditor  

---

## 1. REMAINING VALIDATION GAPS

### GAP-01: Physical Lab Device Network Reachability
- **Severity:** Medium (Operational / Environmental)
- **Description:** Real lab devices `dev_chr` (`10.66.38.30:22`, RouterOS v7.23.8) and `dev_r-1` (`192.168.0.1:22`, RouterOS 6.49.18) are defined in inventory but were unreachable over TCP port 22 because the host workstation was connected to an external Wi-Fi subnet (`10.26.213.223/24`).
- **Impact:** Live real-time command pulls could not be freshly executed against physical ports in this exact session.
- **Mitigation Applied:** Real-device captures previously obtained from these identical physical routers during Phase 5 live testing were verified, hashed, and organized under `tests/fixtures/routes/routeros_v6/` and `routeros_v7/`.
- **Remaining Action:** When the host machine is physically or virtually bridged to the lab subnets, re-run live command execution in WP 4.6.1 or WP 4.6.6 to confirm parity on live wire.

---

## 2. UNMODELED ROUTEROS KERNEL BEHAVIORS (ARCHITECTURAL DISCLOSURE)

### GAP-02: Policy Routing Rules & Routing Marks Not Evaluated in Statically Computed LPM
- **Severity:** Low (Architectural Boundary / Disclosed)
- **Description:** `evaluate_longest_prefix_match` evaluates routing table entries statically (with support for `routing_table="main"` or specified VRF table). However, RouterOS policy routing rules (`/ip route rule` or `/routing rule`) and packet-level firewall mangle routing-marks are not dynamically simulated.
- **Impact:** If a device uses policy routing rules that override the standard routing table lookup, the actual forwarding path may diverge from static LPM.
- **Mitigation Applied:** Explicitly disclosed in `evaluate_longest_prefix_match` output under `missing_evidence` and `limits_disclosure`. Statically computed LPM results are surfaced as `inferred_hypotheses` rather than verified forwarding proof.

### GAP-03: FastTrack & Hardware Switch-Chip Offload
- **Severity:** Low (Architectural Boundary / Disclosed)
- **Description:** FastTrack-accelerated flows and hardware switch chip offloaded frames bypass CPU routing table lookups entirely.
- **Impact:** Observed live traffic flows might not increment CPU route counters or traverse software routing hooks.
- **Mitigation Applied:** Explicitly classified as out-of-scope for static route table parsing and disclosed in architecture documentation.

---

## 3. AUDIT CONCLUSION

All remaining issues are strictly environmental or unmodeled kernel behaviors with explicit architectural disclosure. No unresolved software bugs or regressions exist within the WP 4.6.0 implementation.
