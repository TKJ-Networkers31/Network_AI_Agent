"""
tools/ssh/shell.py — PersistentShell: satu channel invoke_shell() paramiko
yang dipertahankan hidup dan dipakai berulang untuk banyak command
berurutan, TANPA login ulang tiap command.

Low-level client MURNI (tidak ada reasoning/keputusan) - satu-satunya
pemanggil yang sah adalah agents/akane/connection_manager.py, sesuai
aturan tools/README.md dan docs/architecture.md.

FIX (Optimalisasi APCE):
1. PROMPT_RE sebelumnya HANYA cocok dengan prompt RouterOS polos
   "[user@identity] > ". Begitu router masuk Safe Mode (menampilkan
   "[user@identity] <SAFE> > ") atau punya tag tambahan lain di antara
   "]" dan ">" akhir, regex lama GAGAL COCOK SAMA SEKALI - karena
   "[^\\r\\n>]*" tidak boleh melewati karakter ">" apa pun, termasuk ">"
   penutup tag "<SAFE>". Akibatnya _read_until_prompt() SELALU timeout
   penuh (25s default) setiap kali Safe Mode aktif, dan mengembalikan
   output PARSIAL tanpa ada tanda apa pun ke pemanggil bahwa itu
   terpotong. Regex diganti jadi lebih toleran: apa pun boleh muncul di
   antara "]" dan ">" akhir (termasuk ">" tag lain), selama akhir baris
   tetap "> " (ditemukan lewat backtracking greedy).
2. Deteksi paginasi & prompt sekarang dijalankan terhadap versi buffer
   yang SUDAH dibersihkan dari escape code ANSI (bukan buffer mentah) -
   sebelumnya kode warna terminal di sekitar prompt bisa ikut merusak
   pencocokan regex.
3. execute() sekarang mengembalikan dict {"output", "prompt_matched"}
   bukan string mentah, supaya pemanggil (connection_manager.py) bisa
   tahu dan melaporkan ke user kalau output KEMUNGKINAN terpotong
   karena prompt tidak pernah cocok sebelum timeout - alih-alih diam-
   diam melaporkan sukses dengan data yang mungkin tidak lengkap.
"""

import re
import time
import logging

import paramiko

logger = logging.getLogger("aira.tools.ssh.shell")

# FIX: sebelumnya "[^\r\n>]*" antara "]" dan ">" akhir - tidak toleran
# terhadap tag tambahan (mis. "<SAFE>") yang mengandung karakter ">".
# Sekarang pakai ".*" (greedy, backtracking) supaya regex mencari ">"
# TERAKHIR di baris sebagai penutup prompt, apa pun yang ada sebelumnya.
ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:"
    r"\[[0-?]*[ -/]*[@-~]"
    r"|\][^\x07\x1b\r\n]*(?:\x07|\x1b\\|[\r\n]|$)"
    r"|[()#%][A-Za-z0-9]"
    r"|[=><~]"
    r"|[A-Za-z0-9]"
    r")"
)
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PROMPT_RE = re.compile(r"\[[^\]\r\n]+@[^\]\r\n]+\].*>\s*$", re.MULTILINE)
PAGINATE_MARKERS = (
    "-- [q quit",
    "[q quit|d dump",
    "--more--",
    "more--",
    "(q to abort",
    "q to abort",
    "press enter",
    "-- press enter",
)


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
        password: str | None = None,
        port: int = 22,
        key_data: str | None = None,
        term: str = "dumb",
        width: int = 200,
        height: int = 50,
        connect_timeout: float = 15.0,
    ) -> None:
        # Bersihkan channel/koneksi lama jika ada sebelum membuka baru
        self.close()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        pkey = None
        if key_data and key_data.strip():
            import io
            key_file = io.StringIO(key_data.strip())
            for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey):
                try:
                    key_file.seek(0)
                    pkey = key_cls.from_private_key(key_file, password=password or None)
                    break
                except Exception:
                    continue
            if not pkey:
                raise ValueError("Format SSH Private Key tidak dikenali atau passphrase salah.")

        # MikroTik RouterOS mendukung modifier "+ct200w" pada username untuk
        # mematikan deteksi terminal interaktif (\x1b[6n yang bikin hang 10 detik)
        # dan mematikan kode warna ANSI. Jika target bukan RouterOS dan gagal auth,
        # otomatis fallback ke username standar.
        login_user = username if "+" in username else f"{username}+ct200w"
        try:
            client.connect(
                hostname=host,
                port=port,
                username=login_user,
                password=password if not pkey else None,
                pkey=pkey,
                look_for_keys=False,
                allow_agent=False,
                timeout=connect_timeout,
                banner_timeout=max(connect_timeout, 25.0),
                auth_timeout=max(connect_timeout, 20.0),
            )
        except paramiko.AuthenticationException:
            if login_user != username:
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password if not pkey else None,
                    pkey=pkey,
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=connect_timeout,
                    banner_timeout=max(connect_timeout, 25.0),
                    auth_timeout=max(connect_timeout, 20.0),
                )
            else:
                raise

        channel = client.invoke_shell(term=term, width=width, height=height)
        channel.settimeout(0.5)

        self.client = client
        self.channel = channel
        self.host = host
        self.port = port
        self.username = username

        # Buang banner/prompt awal dan tangani prompt interaktif (mis. Software License [Y/n])
        self._drain_initial_handshake(max_wait=6.0)

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

    def execute(self, command: str, timeout: float = 25.0) -> dict:
        """
        Return: {"output": str, "prompt_matched": bool}

        prompt_matched=False artinya prompt RouterOS tidak pernah
        terdeteksi sebelum timeout - output yang dikembalikan tetap
        yang berhasil terbaca sejauh itu, tapi KEMUNGKINAN terpotong.
        """
        if not self.is_alive():
            raise ShellNotConnectedError(
                f"Shell channel ke {self.host} tidak aktif/sudah terputus."
            )

        # Bersihkan sisa buffer dan lepaskan pager/lisensi yang mungkin menggantung
        pre = self._drain_nonblocking()
        if pre:
            lower_pre = pre.lower()
            if any(marker in lower_pre for marker in PAGINATE_MARKERS):
                self.channel.send("q\r\n")
                time.sleep(0.2)
                self._drain_nonblocking()
            elif "[y/n]" in lower_pre or "software license" in lower_pre:
                self.channel.send("n\r\n")
                time.sleep(0.2)
                self._drain_nonblocking()
            elif "new password>" in lower_pre or "ctrl-c to skip" in lower_pre:
                self.channel.send("\x03")
                time.sleep(0.2)
                self._drain_nonblocking()

        self.channel.send(command.strip() + "\r\n")

        raw, prompt_matched = self._read_until_prompt(timeout=timeout)
        cleaned = self._clean_output(raw, command)

        return {"output": cleaned, "prompt_matched": prompt_matched}

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

    def _drain_initial_handshake(self, max_wait: float = 6.0) -> str:
        buffer = ""
        start = time.time()
        last_data = time.time()

        while time.time() - start < max_wait:
            if self.channel.recv_ready():
                chunk = self.channel.recv(4096).decode(errors="replace")
                buffer += chunk
                last_data = time.time()

                # Jawab kueri ukuran layar ANSI DSR (\x1b[6n) dari RouterOS agar tidak hang 10 detik
                if "\x1b[6n" in chunk:
                    self.channel.send("\x1b[50;200R")
                    continue

                probe = ANSI_ESCAPE_RE.sub("", buffer)
                probe_clean = CONTROL_CHARS_RE.sub("", probe).lower()

                if "[y/n]" in probe_clean or "software license" in probe_clean:
                    self.channel.send("n\r\n")
                    time.sleep(0.3)
                    buffer = ""
                    continue

                if any(marker in probe_clean for marker in PAGINATE_MARKERS):
                    self.channel.send("q\r\n")
                    time.sleep(0.3)
                    buffer = ""
                    continue

                if "new password>" in probe_clean or "ctrl-c to skip" in probe_clean:
                    self.channel.send("\x03")
                    time.sleep(0.3)
                    buffer = ""
                    continue

                lines = [l.strip() for l in probe.splitlines() if l.strip()]
                if lines and PROMPT_RE.search(lines[-1]):
                    time.sleep(0.15)
                    if not self.channel.recv_ready():
                        break

            else:
                if buffer and (time.time() - last_data) > 2.0:
                    break
                time.sleep(0.05)

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

    def _read_until_prompt(self, timeout: float) -> "tuple[str, bool]":
        buffer = ""
        start = time.time()
        last_data = time.time()
        prompt_matched = False

        while True:
            if self.channel.recv_ready():
                chunk = self.channel.recv(4096).decode(errors="replace")
                buffer += chunk
                last_data = time.time()

                if "\x1b[6n" in chunk:
                    self.channel.send("\x1b[50;200R")

                # FIX: cek paginasi & prompt terhadap versi TANPA escape
                # ANSI, bukan buffer mentah - kode warna di sekitar
                # prompt sebelumnya bisa merusak pencocokan regex.
                probe = ANSI_ESCAPE_RE.sub("", buffer)
                probe_clean = CONTROL_CHARS_RE.sub("", probe)

                # RouterOS paginasi hasil panjang atau prompt lisensi
                probe_lower = probe_clean.lower()
                if "[y/n]" in probe_lower or "software license" in probe_lower:
                    self.channel.send("n\r\n")
                    time.sleep(0.2)

                if any(marker in probe_lower for marker in PAGINATE_MARKERS):
                    self.channel.send("q\r\n")
                    time.sleep(0.2)

                lines = [line.strip() for line in probe_clean.splitlines() if line.strip()]
                last_line = lines[-1] if lines else ""

                if "\n" in probe_clean and last_line and PROMPT_RE.search(last_line):
                    prompt_matched = True
                    break

            else:
                elapsed = time.time() - start

                if elapsed > timeout:
                    logger.warning(
                        "Timeout menunggu prompt (%.1fs) untuk host=%s - output "
                        "kemungkinan TERPOTONG (prompt tidak pernah cocok dengan "
                        "pola yang diharapkan).",
                        timeout, self.host,
                    )
                    break

                # Tidak ada prompt match tapi sudah lama tidak ada data
                # baru -> anggap output sudah selesai (bukan timeout,
                # tapi tetap tidak match - prompt_matched tetap False).
                if buffer and (time.time() - last_data) > 1.5:
                    break

                time.sleep(0.05)

        return buffer, prompt_matched

    def _clean_output(self, raw: str, command: str) -> str:
        text = ANSI_ESCAPE_RE.sub("", raw)
        text = CONTROL_CHARS_RE.sub("", text)

        # RouterOS mengakhiri baris dengan '\r\n' dan me-redraw baris panjang dengan '\r'.
        # Buang '\r' di ujung baris dulu, lalu ambil segmen terakhir setelah '\r'.
        raw_lines = text.split("\n")
        lines = [rl.rstrip("\r").split("\r")[-1] for rl in raw_lines]

        # Buang baris echo command dan baris prompt RouterOS ([user@host] > ...)
        cmd_s = command.strip()
        cmd_prefix = cmd_s[:20] if cmd_s else ""
        filtered = []
        for idx, l in enumerate(lines):
            ls = l.strip()
            if idx == 0 and cmd_prefix and (cmd_s in ls or ls.startswith(cmd_prefix)):
                continue
            if PROMPT_RE.search(ls) or re.match(r"^\[[^\]\r\n]+@[^\]\r\n]+\].*>", ls):
                continue
            filtered.append(l)
        lines = filtered

        while lines and not lines[-1].strip():
            lines.pop()

        cleaned_lines = [
            line for line in lines
            if not any(marker in line.lower() for marker in PAGINATE_MARKERS)
            and "[y/n]" not in line.lower()
            and "software license" not in line.lower()
            and "license agreement" not in line.lower()
        ]

        return "\n".join(cleaned_lines).strip()