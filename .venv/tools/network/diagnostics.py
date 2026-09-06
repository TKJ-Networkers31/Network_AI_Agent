import subprocess


def ping(target, count=4):
    try:
        result = subprocess.run(
            ["ping", "-n", str(count), target],
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

    try:

        result = subprocess.run(
            [
                "traceroute",
                target
            ],
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