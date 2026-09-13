"""
core/filesystem/models.py — dataclass untuk File System Engine (FSE).

Semua operasi FSE mengembalikan dataclass di sini, BUKAN dict/JSON
mentah. api/routers/files.py yang mengubahnya jadi JSON di titik keluar
HTTP paling akhir (FastAPI melakukan ini otomatis lewat jsonable_encoder).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PermissionLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"
    DENY = "DENY"


@dataclass
class FileEntry:
    name: str
    path: str            # path relatif terhadap workspace root
    is_dir: bool
    size: int
    modified_at: float


@dataclass
class TreeNode:
    entry: FileEntry
    children: list["TreeNode"] = field(default_factory=list)


@dataclass
class OperationResult:
    success: bool
    path: Optional[str] = None
    message: str = ""
    error: Optional[str] = None


@dataclass
class ReadResult:
    success: bool
    path: Optional[str] = None
    content: Optional[str] = None
    error: Optional[str] = None


@dataclass
class WriteResult:
    success: bool
    path: Optional[str] = None
    snapshot_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class HistorySnapshot:
    snapshot_id: str
    path: str
    checksum: str
    created_at: float
    size: int


@dataclass
class TrashEntry:
    trash_id: str
    original_path: str
    trashed_path: str
    deleted_at: float
    checksum: str
    size: int