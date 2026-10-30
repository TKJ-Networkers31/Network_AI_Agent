import platform
import subprocess


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


def traceroute(
    target
):
    """
    Cross-platform traceroute.

    Windows      : tracert -d -h 20 -w 800 <target>
    Unix/Linux/Mac: traceroute -n -q 1 -w 2 -m 20 <target>

    FIX (regresi ronde 2 - Phase 0):
    Command 'tracert'/'traceroute' polos (tanpa flag pembatas) di
    dunia nyata WAJAR butuh lebih dari 30 detik, karena:
    - Defaultnya coba sampai 30 hop.
    - Tiap hop coba resolve reverse-DNS dulu (lambat kalau DNS server
      lambat/hop tidak punya PTR record).
    Sebelumnya subprocess timeout=30 selalu memotong proses sebelum
    sempat selesai wajar, DAN output parsial yang sudah sempat
    terekam dibuang total - sehingga user tidak dapat apa-apa sama
    sekali walau sebagian hop sebenarnya sudah berhasil dilacak.

    Fix di sini:
    1. Tambah flag supaya proses lebih cepat & dapat diprediksi
       durasinya: -d/-n (skip reverse-DNS tiap hop, ini penghemat
       waktu TERBESAR), batasi jumlah hop (-h/-m 20), dan batasi
       waktu tunggu per-probe (-w).
    2. Kalau tetap kena TimeoutExpired, AMBIL output parsial dari
       exc.stdout/exc.stderr (subprocess tetap menyimpannya walau
       proses dipaksa berhenti) - supaya user tetap dapat hop-hop
       yang sempat terlacak, bukan cuma pesan error kosong.
    """

    is_windows = platform.system().lower() == "windows"

    if is_windows:
        command = ["tracert", "-d", "-h", "20", "-w", "800", target]
    else:
        command = ["traceroute", "-n", "-q", "1", "-w", "2", "-m", "20", target]

    timeout_seconds = 45

    try:

        extra_kwargs = {}
        if is_windows:
            extra_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            **extra_kwargs,
        )

        return {
            "success": result.returncode == 0,
            "tool": "traceroute",
            "target": target,
            "output": result.stdout,
            "error": result.stderr
        }

    except subprocess.TimeoutExpired as exc:

        # exc.stdout/exc.stderr tetap berisi apa pun yang sempat
        # ditangkap sebelum proses di-kill paksa oleh subprocess.
        partial_output = exc.stdout or ""
        partial_error = exc.stderr or ""

        error_message = (
            f"Traceroute melebihi batas waktu {timeout_seconds}s dan "
            f"dihentikan paksa."
        )

        if partial_error:
            error_message += f" Detail stderr: {partial_error.strip()}"

        return {
            "success": False,
            "tool": "traceroute",
            "target": target,
            "output": partial_output,
            "error": error_message,
        }

    except Exception as exc:

        return {
            "success": False,
            "tool": "traceroute",
            "target": target,
            "error": str(exc)
        }