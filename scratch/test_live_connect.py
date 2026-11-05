import sys, os

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AIRA_ECOSYSTEM"))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from agents.akane.connection_manager import get_connection_manager
from core.network_intelligence.security import validate_readonly_command

def test_live_connections():
    cm = get_connection_manager()
    devices_to_test = ["CHR", "R-1", "Core-1", "ISP-1"]

    for d in devices_to_test:
        print(f"\n--- Testing connection for: {d} ---")
        try:
            res = cm.open_connection_for_device(d)
            print(f" -> open_connection_for_device result: success={res.get('success')}, status={res.get('status')}, error={res.get('error')}")
            if res.get("success"):
                cmd = "/system identity print"
                assert validate_readonly_command(cmd)
                out = cm.execute_for_device(d, cmd)
                print(f" -> Output for '{cmd}':\n{out.get('output', '')[:200]}")
                
                route_cmd = "/ip route print"
                assert validate_readonly_command(route_cmd)
                rout_out = cm.execute_for_device(d, route_cmd)
                print(f" -> Output for '{route_cmd}':\n{rout_out.get('output', '')[:200]}")
            else:
                print(f" -> Connection not successful: {res.get('error')}")
        except Exception as e:
            print(f" -> Exception connecting to {d}: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_live_connections()
