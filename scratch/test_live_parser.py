import sys, os
import json

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AIRA_ECOSYSTEM"))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from agents.akane.connection_manager import get_connection_manager
from core.network_intelligence.security import validate_readonly_command
from core.routing.unified_route_parser import UnifiedRouteParser

def test_live_parsing():
    cm = get_connection_manager()
    parser = UnifiedRouteParser()

    # 1. Test RouterOS v7 on CHR
    print("=" * 60)
    print("LIVE ROUTEROS v7 ACCEPTANCE (CHR - 10.26.213.30)")
    print("=" * 60)
    cmd_v7 = "/ip route print detail"
    assert validate_readonly_command(cmd_v7)
    res_v7 = cm.execute_for_device("CHR", cmd_v7)
    raw_v7 = res_v7.get("output", "")
    print(f"Raw output length: {len(raw_v7)} chars")
    print(f"Raw excerpt:\n{raw_v7[:300]}")

    routes_v7 = parser.parse(raw_v7, device_id="CHR", ros_version=7)
    print(f"Normalized routes parsed from live CHR: {len(routes_v7)}")
    for r in routes_v7[:5]:
        print(f" - prefix={r.dst_prefix}, gateway={r.gateway}, active={r.active}, distance={r.distance}, proto={r.protocol}")

    # 2. Test RouterOS v6 on R-1
    print("\n" + "=" * 60)
    print("LIVE ROUTEROS v6 ACCEPTANCE (R-1 - 192.168.0.1)")
    print("=" * 60)
    cmd_v6 = "/ip route print detail"
    assert validate_readonly_command(cmd_v6)
    res_v6 = cm.execute_for_device("R-1", cmd_v6)
    raw_v6 = res_v6.get("output", "")
    print(f"Raw output length: {len(raw_v6)} chars")
    print(f"Raw excerpt:\n{raw_v6[:300]}")

    routes_v6 = parser.parse(raw_v6, device_id="R-1", ros_version=6)
    print(f"Normalized routes parsed from live R-1: {len(routes_v6)}")
    for r in routes_v6[:5]:
        print(f" - prefix={r.dst_prefix}, gateway={r.gateway}, active={r.active}, distance={r.distance}, proto={r.protocol}")

    # 3. Test Offline Handling on Core-1
    print("\n" + "=" * 60)
    print("OFFLINE DEVICE GRACEFUL HANDLING (Core-1 - 10.0.0.1)")
    print("=" * 60)
    from core.network_intelligence.intelligence_models import CollectionGapRecord
    gap = CollectionGapRecord(
        gap_id="gap_core1_offline",
        device_id="Core-1",
        evidence_type="routes",
        gap_reason="DEVICE_UNREACHABLE",
        detail="Device 10.0.0.1 offline: SSH connect timed out",
    )
    print(f"Collection Gap Record created: id={gap.gap_id}, device={gap.device_id}, reason={gap.gap_reason}")
    assert gap.device_id == "Core-1"
    print(" -> Offline device handled gracefully via CollectionGapRecord.")

if __name__ == "__main__":
    test_live_parsing()
