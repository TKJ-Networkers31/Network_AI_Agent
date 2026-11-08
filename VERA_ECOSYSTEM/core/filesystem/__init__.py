"""
core/filesystem/ — File System Engine (FSE) untuk AIRA OS (Sprint 02).

Public API:
    from core.filesystem import get_workspace_manager, FileOperations

FSE TIDAK PERNAH tahu apakah host Windows atau Linux - semua info host
datang dari core/host/ (HAL), diinjeksikan lewat WorkspaceManager.
"""

from core.filesystem.workspace import WorkspaceManager, get_workspace_manager, PathTraversalError
from core.filesystem.operations import FileOperations
from core.filesystem.permissions import PermissionEngine, get_permission_engine
from core.filesystem.history import HistoryEngine
from core.filesystem.trash import TrashEngine
from core.filesystem.models import (
    FileEntry, TreeNode, OperationResult, ReadResult, WriteResult,
    HistorySnapshot, TrashEntry, PermissionLevel,
)

__all__ = [
    "WorkspaceManager", "get_workspace_manager", "PathTraversalError",
    "FileOperations", "PermissionEngine", "get_permission_engine",
    "HistoryEngine", "TrashEngine",
    "FileEntry", "TreeNode", "OperationResult", "ReadResult", "WriteResult",
    "HistorySnapshot", "TrashEntry", "PermissionLevel",
]