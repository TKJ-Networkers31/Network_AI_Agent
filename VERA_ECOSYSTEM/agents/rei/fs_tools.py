"""
agents/rei/fs_tools.py — wrapper tipis REI di atas File System Engine
(core/filesystem/*) supaya AIRA bisa membaca/menulis/mengelola file di
AIRA Workspace lewat percakapan biasa, bukan cuma lewat halaman
Workspace di PWA.

KENAPA FILE INI ADA (root cause "AI bilang tidak punya fitur file"):
core/filesystem/* (FSE) dan api/routers/files.py SUDAH lengkap - tapi
HANYA dipanggil dari REST endpoint yang dipakai WorkspacePage.jsx (UI
file manager). agents/rei/planner.py (LLM) TIDAK PERNAH tahu FSE itu
ada, karena satu-satunya sumber kemampuan yang dikirim ke model adalah
AGENT_TOOL_SCHEMAS di core/orchestrator.py, yang cuma menggabungkan
AKANE_TOOLS + HIKARI_TOOLS + REI_TOOLS. FSE tidak pernah masuk salah
satu dari tiga itu -> LLM (benar secara teknis) menjawab "saya tidak
punya fitur itu".

Fix: daftarkan FSE sebagai kemampuan REI (lihat agents/rei/registry.py)
- TIDAK ADA perubahan pada core/filesystem/* atau api/routers/files.py
sama sekali. File ini murni wrapper tipis yang mengubah dataclass hasil
FSE (FileEntry/TreeNode/OperationResult/dll) menjadi dict biasa - WAJIB,
karena agents/rei/planner.py mem-json.dumps() hasil tool apa adanya, dan
dataclass BUKAN JSON-serializable secara default (kalau tidak dikonversi,
tool call akan gagal dengan TypeError).

Ranah operasi TETAP dibatasi ke <workspace_root> (sandbox
PathTraversalError di core/filesystem/workspace.py::WorkspaceManager.resolve())
- persis desain awal "ranah masih di workspace, bisa diperluas nanti",
lintas platform Windows/Linux lewat core/host/* (HAL) - TIDAK disentuh
sama sekali di file ini.
"""

from dataclasses import asdict

from core.filesystem import (
    get_workspace_manager,
    FileOperations,
    PathTraversalError,
)
from core.filesystem.trash import TrashEngine


def _ops() -> FileOperations:
    return FileOperations()


def _workspace():
    return get_workspace_manager()


def list_workspace(path: str = "", max_depth: int = 2) -> dict:
    """Lihat isi folder di AIRA Workspace (default: root workspace)."""
    workspace = _workspace()

    try:
        node = workspace.tree(path, max_depth=max_depth)
    except PathTraversalError as exc:
        return {"success": False, "tool": "list_workspace", "error": str(exc)}
    except FileNotFoundError as exc:
        return {"success": False, "tool": "list_workspace", "error": str(exc)}

    return {
        "success": True,
        "tool": "list_workspace",
        "path": path or "/",
        "tree": asdict(node),
    }


def read_file(path: str) -> dict:
    result = _ops().read_text(path)
    data = asdict(result)
    data["tool"] = "read_file"
    return data


def write_file(path: str, content: str) -> dict:
    result = _ops().write_text(path, content)
    data = asdict(result)
    data["tool"] = "write_file"
    return data


def create_folder(path: str) -> dict:
    result = _ops().mkdir(path)
    data = asdict(result)
    data["tool"] = "create_folder"
    return data


def move_file(source: str, destination: str) -> dict:
    result = _ops().move(source, destination)
    data = asdict(result)
    data["tool"] = "move_file"
    return data


def copy_file(source: str, destination: str) -> dict:
    result = _ops().copy(source, destination)
    data = asdict(result)
    data["tool"] = "copy_file"
    return data


def rename_file(source: str, destination: str) -> dict:
    result = _ops().rename(source, destination)
    data = asdict(result)
    data["tool"] = "rename_file"
    return data


def delete_file(path: str) -> dict:
    """Tidak pernah permanen - dipindahkan ke Trash (core/filesystem/trash.py),
    bisa dikembalikan lewat restore_file()."""
    result = _ops().delete(path)
    data = asdict(result)
    data["tool"] = "delete_file"
    return data


def restore_file(trash_id: str) -> dict:
    result = _ops().restore(trash_id)
    data = asdict(result)
    data["tool"] = "restore_file"
    return data


def list_trash() -> dict:
    workspace = _workspace()
    entries = TrashEngine(workspace.root).list_trash()

    return {
        "success": True,
        "tool": "list_trash",
        "count": len(entries),
        "entries": [asdict(e) for e in entries],
    }