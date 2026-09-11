"""
core/logger.py — sistem logging terstruktur AIRA Ecosystem.

Setiap logging.getLogger("aira.<kategori>...") otomatis mengalir ke 4 output:
1. Console      - berwarna, ada tag [LEVEL][kategori], untuk debug langsung.
2. aira.log     - semua kategori digabung, rotating (tidak makan disk terus).
3. categories/  - satu file rotating per kategori (logs/categories/ssh.log,
                   llm.log, dst) supaya troubleshooting fokus tanpa grep file
                   gabungan.
4. logs.db      - SQLite terstruktur (core/log_store.py), dikonsumsi endpoint
                   /api/logs untuk halaman "Logs" di PWA (filter kategori,
                   level, keyword, rentang waktu).

CARA PAKAI DI MODUL LAIN:
    from core.logger import get_logger, log_event
    logger = get_logger("ssh")  # -> logging.getLogger("aira.ssh")

    log_event(
        logger, "INFO", "SSH exec selesai",
        context={"device": "R1", "command": "/system resource print"},
        duration_ms=182.4, success=True,
    )

Modul lama yang masih pakai logging.getLogger("aira.tools.ssh") dkk tetap
otomatis kebagian kategori dari segmen terakhir nama logger (lihat
_infer_category) - tidak perlu migrasi paksa semua file sekaligus.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from core import log_store

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
LOG_DIR = BASE_DIR / "logs"
CATEGORY_LOG_DIR = LOG_DIR / "categories"
MAIN_LOG_FILE = LOG_DIR / "aira.log"

MAX_BYTES = 5 * 1024 * 1024  # 5MB per file
BACKUP_COUNT = 3

_configured = False

LEVEL_COLORS = {
    "DEBUG": "\033[90m",
    "INFO": "\033[36m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[97;41m",
}
RESET = "\033[0m"
CATEGORY_COLOR = "\033[35m"


def _infer_category(logger_name: str) -> str:
    """'aira.tools.ssh' -> 'ssh', 'aira.rei.planner' -> 'planner', 'aira' -> 'system'."""
    parts = logger_name.split(".")
    if len(parts) <= 1:
        return "system"
    return parts[-1]


class ColorConsoleFormatter(logging.Formatter):
    """Formatter berwarna: [LEVEL][kategori] timestamp | logger | pesan."""

    def format(self, record):
        category = getattr(record, "category", None) or _infer_category(record.name)
        level_color = LEVEL_COLORS.get(record.levelname, "")

        base = super().format(record)

        prefix = (
            f"{level_color}[{record.levelname:<8}]{RESET} "
            f"{CATEGORY_COLOR}[{category:<14}]{RESET} "
        )

        return prefix + base


class SQLiteLogHandler(logging.Handler):
    """Menulis tiap log record ke database/logs.db supaya bisa di-query dari
    API dan ditampilkan/difilter di halaman Logs PWA."""

    def emit(self, record):
        try:
            category = getattr(record, "category", None) or _infer_category(record.name)
            context = getattr(record, "context", None)
            duration_ms = getattr(record, "duration_ms", None)
            success = getattr(record, "success", None)

            message = record.getMessage()

            if record.exc_info:
                message += "\n" + self.formatException(record.exc_info)

            log_store.insert_log(
                category=category,
                level=record.levelname,
                logger_name=record.name,
                message=message,
                context=context,
                duration_ms=duration_ms,
                success=success,
                created_at=record.created,
            )
        except Exception:
            self.handleError(record)


class CategoryFileHandler(logging.Handler):
    """Router dinamis: tiap kategori otomatis punya file rotating sendiri di
    logs/categories/<kategori>.log, dibuat on-demand saat pertama kali muncul."""

    def __init__(self, formatter: logging.Formatter):
        super().__init__()
        self._formatter = formatter
        self._handlers: dict[str, logging.handlers.RotatingFileHandler] = {}
        CATEGORY_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _get_handler(self, category: str) -> logging.handlers.RotatingFileHandler:
        handler = self._handlers.get(category)

        if handler is None:
            safe_name = "".join(c for c in category if c.isalnum() or c in ("_", "-")) or "other"
            file_path = CATEGORY_LOG_DIR / f"{safe_name}.log"
            handler = logging.handlers.RotatingFileHandler(
                file_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
            )
            handler.setFormatter(self._formatter)
            self._handlers[category] = handler

        return handler

    def emit(self, record):
        try:
            category = getattr(record, "category", None) or _infer_category(record.name)
            self._get_handler(category).emit(record)
        except Exception:
            self.handleError(record)


def setup_logging(level: int = logging.INFO) -> None:
    """Setup sekali untuk seluruh ekosistem AIRA. Idempotent."""

    global _configured

    if _configured:
        return

    LOG_DIR.mkdir(exist_ok=True)
    CATEGORY_LOG_DIR.mkdir(exist_ok=True)

    root_logger = logging.getLogger("aira")
    root_logger.setLevel(level)

    if root_logger.handlers:
        _configured = True
        return

    plain_formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorConsoleFormatter(
        "%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S"
    ))
    root_logger.addHandler(console_handler)

    main_file_handler = logging.handlers.RotatingFileHandler(
        MAIN_LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    main_file_handler.setFormatter(plain_formatter)
    root_logger.addHandler(main_file_handler)

    root_logger.addHandler(CategoryFileHandler(plain_formatter))
    root_logger.addHandler(SQLiteLogHandler())

    root_logger.propagate = False
    _configured = True

    root_logger.info(
        "LOGGING SETUP | console + %s + categories/ + logs.db",
        MAIN_LOG_FILE.name,
        extra={"category": "system"},
    )


def get_logger(category: str) -> logging.Logger:
    """logging.getLogger('aira.<category>') - nama logger jadi sumber kategori."""
    return logging.getLogger(f"aira.{category}")


def log_event(
    logger: logging.Logger,
    level: str,
    message: str,
    category: Optional[str] = None,
    context: Optional[dict] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
) -> None:
    """Log terstruktur: context/duration/success masuk kolom terpisah di
    logs.db (bukan cuma di-embed ke teks pesan), jadi bisa difilter/di-sort."""

    extra: dict = {}
    if category:
        extra["category"] = category
    if context is not None:
        extra["context"] = context
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    if success is not None:
        extra["success"] = success

    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(message, extra=extra)