"""
tools/ssh/shell.py — PersistentShell: satu channel invoke_shell() paramiko
yang dipertahankan hidup dan dipakai berulang untuk banyak command
berurutan, TANPA login ulang tiap command.

Low-level client MURNI (tidak ada reasoning/keputusan) - satu-satunya
pemanggil yang sah adalah agents/akane/connection_manager.py, sesuai
aturan tools/README.md dan docs/architecture.md.
"""

import re
import time
import logging

import paramiko

logger = logging.getLogger("aira.tools.ssh.shell")

PROMPT_RE = re.compile(r"\[[^\]\r\n]*@[^\]\r\n]*\][^\r\n>]*>\s*$")
PAGINATE_MARKERS = ("-- [Q quit", "[Q quit|D dump", "--more--")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


class ShellNotConnectedError(Exception):
    pass


class PersistentShell:
    """
    Wrapper tipis di atas paramiko SSHClient + invoke_shell(). Satu
    instance = satu channel interaktif hidup terhadap satu device.
    """

    def __init__(self):
        self.client: "paramiko.SSHClient | None" = None
        self.channel = None
        self.host = None
        self.port = None
        self.username = None

    def open(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        term: str = "dumb",
        width: int = 200,
        height: int = 50,
        connect_timeout: float = 10.0,
    ) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=connect_timeout,
            banner_timeout=connect_timeout,
            auth_timeout=connect_timeout,
        )

        channel = client.invoke_shell(term=term, width=width, height=height)
        channel.settimeout(0.5)

        self.client = client
        self.channel = channel
        self.host = host
        self.port = port
        self.username = username

        # Buang banner/prompt awal supaya buffer bersih sebelum command
        # pertama user dikirim.
        self._read_until_idle(max_wait=3.0, idle_gap=0.4)

        logger.info("SHELL OPEN | host=%s user=%s - invoke_shell aktif.", host, username)

    def is_alive(self) -> bool:
        if not self.client or not self.channel:
            return False

        transport = self.client.get_transport()

        return bool(
            transport
            and transport.is_active()
            and not self.channel.closed
        )

    def execute(self, command: str, timeout: float = 25.0) -> str:
        if not self.is_alive():
            raise ShellNotConnectedError(
                f"Shell channel ke {self.host} tidak aktif/sudah terputus."
            )

        # Bersihkan sisa buffer yang mungkin belum terbaca dari command
        # sebelumnya (safety net - normalnya sudah kosong).
        self._drain_nonblocking()

        self.channel.send(command.strip() + "\r\n")

        raw = self._read_until_prompt(timeout=timeout)

        return self._clean_output(raw, command)

    def close(self) -> None:
        try:
            if self.channel:
                self.channel.close()
        except Exception:
            pass

        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

        logger.info("SHELL CLOSE | host=%s user=%s", self.host, self.username)

    # ----------------------------------------------------------------
    # INTERNAL
    # ----------------------------------------------------------------

    def _drain_nonblocking(self) -> str:
        buffer = ""

        while self.channel.recv_ready():
            buffer += self.channel.recv(4096).decode(errors="replace")

        return buffer

    def _read_until_idle(self, max_wait: float, idle_gap: float) -> str:
        buffer = ""
        start = time.time()
        last_data = time.time()

        while time.time() - start < max_wait:
            if self.channel.recv_ready():
                buffer += self.channel.recv(4096).decode(errors="replace")
                last_data = time.time()
            else:
                if buffer and (time.time() - last_data) > idle_gap:
                    break
                time.sleep(0.05)

        return buffer

    def _read_until_prompt(self, timeout: float) -> str:
        buffer = ""
        start = time.time()
        last_data = time.time()

        while True:
            if self.channel.recv_ready():
                chunk = self.channel.recv(4096).decode(errors="replace")
                buffer += chunk
                last_data = time.time()

                # RouterOS paginasi hasil panjang - kirim 'Q' supaya
                # keluar dari mode paging alih-alih macet menunggu prompt
                # yang tidak akan pernah muncul.
                if any(marker in buffer for marker in PAGINATE_MARKERS):
                    self.channel.send("Q")

                if PROMPT_RE.search(buffer):
                    break

            else:
                elapsed = time.time() - start

                if elapsed > timeout:
                    logger.warning(
                        "Timeout menunggu prompt (%.1fs) untuk host=%s.", timeout, self.host
                    )
                    break

                # Tidak ada prompt match tapi sudah lama tidak ada data
                # baru -> anggap output sudah selesai.
                if buffer and (time.time() - last_data) > 1.5:
                    break

                time.sleep(0.05)

        return buffer

    def _clean_output(self, raw: str, command: str) -> str:
        text = ANSI_ESCAPE_RE.sub("", raw)
        text = text.replace("\r", "")

        lines = text.split("\n")

        # Baris pertama biasanya echo dari command yang kita kirim.
        if lines and command.strip() in lines[0]:
            lines = lines[1:]

        # Buang baris kosong / prompt baru di ekor output.
        while lines and not lines[-1].strip():
            lines.pop()

        if lines and PROMPT_RE.search(lines[-1]):
            lines.pop()

        while lines and not lines[-1].strip():
            lines.pop()

        cleaned_lines = [
            line for line in lines
            if not any(marker in line for marker in PAGINATE_MARKERS)
        ]

        return "\n".join(cleaned_lines).strip()