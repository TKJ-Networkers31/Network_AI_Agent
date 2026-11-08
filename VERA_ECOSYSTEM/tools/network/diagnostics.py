import logging
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from core.security.masking import validate_network_target

logger = logging.getLogger("aira.network.diagnostics")


def ping(target, count=4, timeout_sec=4):
    """
    Cross-platform ping with structured alive & RTT parsing.

    Windows  : ping -n <count> -w <ms> <target>
    Unix/Mac : ping -c <count> -W <sec> <target>
    """
    from core.topology_models import parse_ping_output

    try:
        is_windows = platform.system().lower() == "windows"
        count = max(1, min(int(count), 10))
        timeout_sec = max(1, min(int(timeout_sec), 10))

        extra_kwargs = {}
        if is_windows:
            cmd = ["ping", "-n", str(count), "-w", str(timeout_sec * 1000), str(target)]
            extra_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        else:
            cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), str(target)]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(10, count * timeout_sec + 4),
            **extra_kwargs,
        )
        parsed = parse_ping_output(result.stdout, result.returncode)

        return {
            "success": parsed["alive"],
            "alive": parsed["alive"],
            "avg_rtt_ms": parsed["avg_rtt_ms"],
            "tool": "ping",
            "target": target,
            "output": result.stdout,
            "error": result.stderr,
        }

    except Exception as exc:
        return {
            "success": False,
            "alive": False,
            "avg_rtt_ms": 0.0,
            "tool": "ping",
            "target": target,
            "error": str(exc),
        }


def nslookup(
    target
):

    try:

        extra_kwargs = {}
        if platform.system().lower() == "windows":
            extra_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        result = subprocess.run(
            [
                "nslookup",
                target
            ],
            capture_output=True,
            text=True,
            timeout=20,
            **extra_kwargs,
        )

        return {
            "success": result.returncode == 0,
            "tool": "nslookup",
            "target": target,
            "output": result.stdout,
            "error": result.stderr
        }

    except Exception as exc:

        return {
            "success": False,
            "tool": "nslookup",
            "target": target,
            "error": str(exc)
        }


def discover_traceroute_binary() -> Tuple[Optional[str], Optional[str]]:
    """
    Discovers available traceroute executable across Linux, Windows, and BusyBox.
    Returns (executable_path, method_name) e.g. ('/usr/bin/traceroute', 'traceroute'),
    or ('/usr/bin/tracepath', 'tracepath'), or ('tracert', 'tracert'),
    or (None, None) if no traceroute tool is present.
    """
    is_windows = platform.system().lower() == "windows"
    if is_windows:
        tracert_bin = shutil.which("tracert")
        if tracert_bin:
            return (tracert_bin, "tracert")
        return (None, None)

    # Linux / macOS / BSD
    for candidate in ("traceroute", "tracepath"):
        bin_path = shutil.which(candidate)
        if bin_path:
            return (bin_path, candidate)

    # Busybox fallback
    busybox_bin = shutil.which("busybox")
    if busybox_bin:
        try:
            res = subprocess.run([busybox_bin, "traceroute", "--help"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 or "traceroute" in (res.stdout + res.stderr).lower():
                return (busybox_bin, "busybox")
        except Exception:
            pass

    return (None, None)


def parse_traceroute_output(stdout: str, method: str = "traceroute", target: Optional[str] = None) -> Dict[str, Any]:
    """
    Parses traceroute, tracepath, or tracert stdout into structured hops.
    Returns:
    {
        "total_hops": int,
        "hops": [
            {
                "hop": int,
                "host": str,
                "ip": Optional[str],
                "rtts": List[float],
                "avg_rtt_ms": Optional[float],
                "status": str ("SUCCESS", "TIMEOUT", "UNREACHABLE", "REACHED"),
                "raw": str,
            }
        ],
        "reached": bool,
    }
    """
    lines = (stdout or "").strip().splitlines()
    hops: List[Dict[str, Any]] = []

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Check tracepath
        if method == "tracepath":
            if "?:" in line_str or "[LOCALHOST]" in line_str:
                continue
            m = re.match(r"^\s*(\d+)\??:\s+(.*)$", line_str)
            if not m:
                continue
            hop_num = int(m.group(1))
            rest = m.group(2).strip()
            if "no reply" in rest.lower():
                hops.append({
                    "hop": hop_num, "host": "*", "ip": None, "rtts": [], "avg_rtt_ms": None,
                    "status": "TIMEOUT", "raw": line_str,
                })
                continue
            is_reached = "reached" in rest.lower()
            rtts = [round(float(x), 3) for x in re.findall(r"(\d+(?:\.\d+)?)\s*ms", rest, re.IGNORECASE)]
            ip_m = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", rest)
            ip = ip_m.group(1) if ip_m else None
            host = rest.split()[0] if rest.split() else (ip or "*")
            status = "REACHED" if is_reached or (target and ip == target) else ("SUCCESS" if rtts else "TIMEOUT")
            avg_rtt = round(sum(rtts) / len(rtts), 3) if rtts else None
            hops.append({
                "hop": hop_num, "host": host, "ip": ip, "rtts": rtts, "avg_rtt_ms": avg_rtt,
                "status": status, "raw": line_str,
            })
            continue

        # Check tracert (Windows)
        if method == "tracert":
            m = re.match(r"^\s*(\d+)\s+((?:(?:<|\d+)\s*ms|\*)\s+.*)$", line_str)
            if not m:
                continue
            hop_num = int(m.group(1))
            rest = m.group(2).strip()
            if "request timed out" in rest.lower() or (rest.startswith("*") and not re.search(r"\d+\.\d+", rest)):
                hops.append({
                    "hop": hop_num, "host": "*", "ip": None, "rtts": [], "avg_rtt_ms": None,
                    "status": "TIMEOUT", "raw": line_str,
                })
                continue
            rtt_matches = re.findall(r"(?:<1|\d+(?:\.\d+)?)\s*ms", rest, re.IGNORECASE)
            rtts = []
            for rm in rtt_matches:
                val_str = re.sub(r"\s*ms", "", rm, flags=re.IGNORECASE).strip()
                rtts.append(0.5 if "<1" in val_str else round(float(val_str), 3))
            ip_m = re.search(r"\[?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]?", rest)
            ip = ip_m.group(1) if ip_m else None
            host_m = re.search(r"(\S+)\s+\[\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\]", rest)
            host = host_m.group(1) if host_m else (ip or "*")
            status = "REACHED" if target and (ip == target or host == target) else ("SUCCESS" if rtts else "TIMEOUT")
            avg_rtt = round(sum(rtts) / len(rtts), 3) if rtts else None
            hops.append({
                "hop": hop_num, "host": host, "ip": ip, "rtts": rtts, "avg_rtt_ms": avg_rtt,
                "status": status, "raw": line_str,
            })
            continue

        # Default: traceroute / busybox
        m = re.match(r"^\s*(\d+)\s+(.*)$", line_str)
        if not m:
            continue
        hop_num = int(m.group(1))
        rest = m.group(2).strip()
        if rest.startswith("*") and not re.search(r"\d+\.\d+", rest):
            hops.append({
                "hop": hop_num, "host": "*", "ip": None, "rtts": [], "avg_rtt_ms": None,
                "status": "TIMEOUT", "raw": line_str,
            })
            continue
        is_unreach = any(x in rest for x in ("!H", "!N", "!P", "!X", "!Z"))
        rtts = [round(float(x), 3) for x in re.findall(r"(\d+(?:\.\d+)?)\s*ms", rest, re.IGNORECASE)]
        ip_m = re.search(r"(?:^|\s|\()(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:\)|\s|$)", rest)
        ip = ip_m.group(1) if ip_m else None
        host_m = re.search(r"^([^\s\(]+)(?:\s+\([^\)]+\))?", rest)
        host = host_m.group(1) if host_m else (ip or "*")
        if is_unreach:
            status = "UNREACHABLE"
        elif target and (ip == target or host == target):
            status = "REACHED"
        elif rtts:
            status = "SUCCESS"
        else:
            status = "TIMEOUT"
        avg_rtt = round(sum(rtts) / len(rtts), 3) if rtts else None
        hops.append({
            "hop": hop_num, "host": host, "ip": ip, "rtts": rtts, "avg_rtt_ms": avg_rtt,
            "status": status, "raw": line_str,
        })

    reached = any(h["status"] == "REACHED" or (target and h.get("ip") == target) for h in hops)
    if hops and target and (hops[-1].get("ip") == target or hops[-1].get("host") == target):
        hops[-1]["status"] = "REACHED"
        reached = True

    return {"total_hops": len(hops), "hops": hops, "reached": reached}


def traceroute(
    target: str,
    max_hops: int = 20,
    wait_sec: int = 2,
    probes: int = 1,
) -> Dict[str, Any]:
    """
    Cross-platform, bounded traceroute with structured hop parsing and honest error status.
    Supports traceroute, tracepath (Linux), and tracert (Windows).
    """
    # 1. Target validation (prevents command injection / option injection)
    try:
        valid_target = validate_network_target(target)
    except Exception as exc:
        return {
            "success": False,
            "tool": "traceroute",
            "target": target,
            "hops": [],
            "total_hops": 0,
            "reached": False,
            "error_type": "invalid_target",
            "error": f"Invalid traceroute target '{target}': {exc}",
        }

    # 2. Executable discovery via shutil.which()
    bin_path, method = discover_traceroute_binary()
    if not bin_path or not method:
        return {
            "success": False,
            "tool": "traceroute",
            "target": valid_target,
            "hops": [],
            "total_hops": 0,
            "reached": False,
            "method_used": None,
            "error_type": "binary_missing",
            "error": "No traceroute executable found (checked 'traceroute', 'tracepath', 'tracert'). Please install 'traceroute' or 'iputils-tracepath'.",
        }

    # 3. Build bounded argument list (NEVER shell=True)
    max_hops = max(1, min(int(max_hops), 30))
    wait_sec = max(1, min(int(wait_sec), 5))
    probes = max(1, min(int(probes), 3))
    is_windows = platform.system().lower() == "windows"

    if method == "tracert":
        command = [bin_path, "-d", "-h", str(max_hops), "-w", str(wait_sec * 1000), valid_target]
    elif method == "tracepath":
        command = [bin_path, "-n", "-m", str(max_hops), valid_target]
    elif method == "busybox":
        command = [bin_path, "traceroute", "-n", "-q", str(probes), "-m", str(max_hops), valid_target]
    else:  # standard unix traceroute
        command = [bin_path, "-n", "-q", str(probes), "-w", str(wait_sec), "-m", str(max_hops), valid_target]

    timeout_seconds = max(15, min(max_hops * wait_sec * probes + 10, 45))

    try:
        extra_kwargs: Dict[str, Any] = {}
        if is_windows:
            extra_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            **extra_kwargs,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        err_lower = stderr.lower() + " " + stdout.lower()

        # Parse hops
        parsed = parse_traceroute_output(stdout, method=method, target=valid_target)

        # Categorize errors on non-zero exit or empty hops
        error_type: Optional[str] = None
        error_msg: Optional[str] = None

        if "operation not permitted" in err_lower or "permission denied" in err_lower:
            error_type = "permission_denied"
            error_msg = f"Traceroute failed: Permission denied (raw socket privileges required). {stderr.strip()}"
        elif "name or service not known" in err_lower or "cannot resolve" in err_lower or "could not find host" in err_lower:
            error_type = "dns_failed"
            error_msg = f"Traceroute failed: DNS resolution error for target '{valid_target}'."
        elif "network is unreachable" in err_lower or "network down" in err_lower or "no route to host" in err_lower:
            error_type = "network_unreachable"
            error_msg = f"Traceroute failed: Network unreachable for '{valid_target}'."
        elif result.returncode != 0 and not parsed["hops"]:
            error_type = "command_failed"
            error_msg = f"Traceroute exited with code {result.returncode}: {stderr.strip() or stdout.strip()}"

        success = (result.returncode == 0 or len(parsed["hops"]) > 0) and error_type is None

        return {
            "success": success,
            "tool": "traceroute",
            "target": valid_target,
            "method_used": method,
            "reached": parsed["reached"],
            "total_hops": parsed["total_hops"],
            "hops": parsed["hops"],
            "output": stdout,
            "error": error_msg or (stderr if not success else None),
            "error_type": error_type,
        }

    except subprocess.TimeoutExpired as exc:
        partial_output = exc.stdout or ""
        partial_error = exc.stderr or ""
        parsed = parse_traceroute_output(partial_output, method=method, target=valid_target)

        return {
            "success": False,
            "tool": "traceroute",
            "target": valid_target,
            "method_used": method,
            "reached": parsed["reached"],
            "total_hops": parsed["total_hops"],
            "hops": parsed["hops"],
            "output": partial_output,
            "error_type": "timeout",
            "error": f"Traceroute timed out after {timeout_seconds}s. Partial hops retained.",
        }

    except PermissionError as exc:
        return {
            "success": False,
            "tool": "traceroute",
            "target": valid_target,
            "method_used": method,
            "hops": [],
            "total_hops": 0,
            "reached": False,
            "error_type": "permission_denied",
            "error": f"Permission denied executing traceroute binary: {exc}",
        }

    except Exception as exc:
        return {
            "success": False,
            "tool": "traceroute",
            "target": valid_target,
            "method_used": method,
            "hops": [],
            "total_hops": 0,
            "reached": False,
            "error_type": "command_failed",
            "error": str(exc),
        }