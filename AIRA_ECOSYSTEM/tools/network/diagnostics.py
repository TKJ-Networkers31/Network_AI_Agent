import platform
import subprocess


def ping(target, count=4):
    """
    Cross-platform ping.

    Windows  : ping -n <count> <target>
    Unix/Mac : ping -c <count> <target>
    """

    try:
        is_windows = platform.system().lower() == "windows"

        count_flag = "-n" if is_windows else "-c"

        result = subprocess.run(
            ["ping", count_flag, str(count), target],
            capture_output=True,
            text=True,
            timeout=20
        )

        return {
            "success": result.returncode == 0,
            "tool": "ping",
            "target": target,
            "output": result.stdout,
            "error": result.stderr
        }

    except Exception as exc:
        return {
            "success": False,
            "tool": "ping",
            "target": target,
            "error": str(exc)
        }


def nslookup(
    target
):

    try:

        result = subprocess.run(
            [
                "nslookup",
                target
            ],
            capture_output=True,
            text=True,
            timeout=20
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

    Windows      : tracert <target>
    Unix/Linux/Mac: traceroute <target>

    FIX (regresi Phase 0): sebelumnya command 'traceroute' selalu
    hardcode, sehingga di Windows selalu gagal dengan
    '[WinError 2] The system cannot find the file specified' karena
    binary bernama 'traceroute' memang tidak ada di Windows - yang
    ada 'tracert'. Ini persis bug yang sebelumnya sudah pernah
    diperbaiki (lihat catatan migrasi) tapi hilang lagi saat porting
    ke AIRA_ECOSYSTEM. Deteksi OS dipakai lagi di sini seperti fix
    aslinya.
    """

    try:

        is_windows = platform.system().lower() == "windows"

        command = (
            ["tracert", target]
            if is_windows
            else ["traceroute", target]
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "success": result.returncode == 0,
            "tool": "traceroute",
            "target": target,
            "output": result.stdout,
            "error": result.stderr
        }

    except Exception as exc:

        return {
            "success": False,
            "tool": "traceroute",
            "target": target,
            "error": str(exc)
        }