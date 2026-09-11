"""
core/logger.py — konfigurasi logging terpusat untuk AIRA Ecosystem.

KENAPA FILE INI PERLU ADA:
Setiap modul (agents/*, core/*, tools/*) sudah konsisten memanggil
`logging.getLogger("aira.xxx")`, tapi tanpa ada satu titik pun yang
men-setup HANDLER (file/console) untuk logger induk "aira", Python
logging cuma memakai lastResort handler (stderr, level WARNING+ saja).

Akibatnya semua log INFO/DEBUG yang biasa dipakai untuk debug (mis.
"TOOL CALL", "LLM REQUEST", "SSH CONNECT", dst - seperti isi
logs/agent.log di sistem lama) HILANG TOTAL di AIRA_ECOSYSTEM kalau
setup_logging() ini tidak dipanggil.

CARA PAKAI:
Panggil setup_logging() SEKALI di entrypoint (api/main.py atau
run_chat.py), sebelum modul lain benar-benar mengeksekusi kode yang
melakukan logging. Import ini boleh dilakukan kapan saja - yang
penting setup_logging() dipanggil sebelum request/percakapan pertama
diproses.
"""

import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "aira.log"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """
    Setup logging sekali untuk seluruh ekosistem AIRA. Aman dipanggil
    berkali-kali (idempotent) - panggilan kedua dst akan di-skip kalau
    sudah pernah konfigurasi sebelumnya.
    """

    global _configured

    if _configured:
        return

    LOG_DIR.mkdir(exist_ok=True)

    root_logger = logging.getLogger("aira")
    root_logger.setLevel(level)

    # Kalau entah bagaimana sudah ada handler terpasang (mis. dipanggil
    # dua kali di proses yang sama), jangan pasang dobel.
    if root_logger.handlers:
        _configured = True
        return

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Jangan propagate ke root logger bawaan Python (hindari log
    # dobel kalau ada library lain yang basicConfig() sendiri).
    root_logger.propagate = False

    _configured = True

    root_logger.info(
        "LOGGING SETUP | log file: %s", LOG_FILE
    )
