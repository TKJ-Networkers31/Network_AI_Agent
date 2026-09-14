"""
agents/rei/registry.py — pintu masuk kemampuan riset, memori, dan File
System Engine (FSE) milik REI: web_search, web_fetch, remember, recall,
forget, list_workspace, read_file, write_file, create_folder, move_file,
copy_file, rename_file, delete_file, restore_file, list_trash.

FIX (root cause "AI bilang tidak punya fitur file"):
FSE didaftarkan lewat agents/rei/fs_tools.py (wrapper tipis di atas
core/filesystem/*, TIDAK mengubah FSE/UI Workspace sama sekali) dan
digabung ke REI_TOOLS/REI_TOOL_CATEGORY/REI_TOOL_SCHEMAS di bawah.
core/orchestrator.py TIDAK PERLU disentuh - dia sudah men-spread
REI_TOOL_SCHEMAS secara otomatis ke AGENT_TOOL_SCHEMAS yang dikirim ke
LLM.

Ranah operasi TETAP dibatasi ke <workspace_root> (sandbox di
core/filesystem/workspace.py), lintas platform Windows/Linux lewat
core/host/* (HAL) - tidak diubah.

Catatan desain: tool tulis/hapus (write_file/delete_file/move_file/dst)
SENGAJA tidak dimasukkan ke *_DANGEROUS_TOOLS. Kalau dimasukkan, planner
(agents/rei/planner.py) akan otomatis MELEWATI tool itu tanpa pernah
benar-benar menjalankannya (belum ada mekanisme konfirmasi interaktif
di chat/WS - lihat "confirmation_required" di planner.py), jadi fitur
tulis-file lewat chat akan mati total. Sebagai gantinya, keamanan
didapat dari sandbox workspace + Trash (delete tidak permanen) + History
snapshot (write menimpa file lama otomatis disimpan) yang sudah ada di
FSE. Kalau nanti mau menambah konfirmasi interaktif, tambahkan
REI_DANGEROUS_TOOLS di sini DAN gabungkan ke DANGEROUS_TOOLS di
core/orchestrator.py (saat ini orchestrator.py hanya menggabungkan
AKANE_DANGEROUS_TOOLS | HIKARI_DANGEROUS_TOOLS, REI belum diikutkan).
"""

from agents.rei import research_tools as rt
from agents.rei import fs_tools as fs
from core.memory import remember_fact, recall_facts, forget_fact


def recall(query: str) -> dict:
    results = recall_facts(query)
    return {"success": True, "tool": "recall", "query": query, "count": len(results), "facts": results}


REI_TOOLS = {
    "web_search": rt.web_search,
    "web_fetch": rt.web_fetch,
    "remember": remember_fact,
    "recall": recall,
    "forget": forget_fact,
    "list_workspace": fs.list_workspace,
    "read_file": fs.read_file,
    "write_file": fs.write_file,
    "create_folder": fs.create_folder,
    "move_file": fs.move_file,
    "copy_file": fs.copy_file,
    "rename_file": fs.rename_file,
    "delete_file": fs.delete_file,
    "restore_file": fs.restore_file,
    "list_trash": fs.list_trash,
}

REI_TOOL_CATEGORY = {
    "web_search": "web",
    "web_fetch": "web",
    "remember": "memory",
    "recall": "memory",
    "forget": "memory",
    "list_workspace": "filesystem",
    "read_file": "filesystem",
    "write_file": "filesystem",
    "create_folder": "filesystem",
    "move_file": "filesystem",
    "copy_file": "filesystem",
    "rename_file": "filesystem",
    "delete_file": "filesystem",
    "restore_file": "filesystem",
    "list_trash": "filesystem",
}

REI_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Mencari informasi terkini di internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian."},
                    "max_results": {"type": "integer", "description": "Jumlah hasil (default 5).", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Mengambil isi teks dari sebuah URL, setelah web_search jika perlu detail lebih dalam.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL halaman yang ingin dibaca."}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Simpan fakta penting lintas sesi (preferensi, threshold, konfigurasi standar).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nama singkat fakta, misal 'threshold_cpu_r1'."},
                    "value": {"type": "string", "description": "Isi fakta yang ingin diingat."},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Cari fakta yang pernah disimpan sebelumnya berdasarkan kata kunci.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Hapus fakta yang tersimpan berdasarkan key-nya.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workspace",
            "description": (
                "Melihat isi folder di dalam AIRA Workspace (folder sandbox "
                "milik pengguna, sama persis dengan yang tampil di halaman "
                "'Workspace' pada PWA - BUKAN seluruh filesystem komputer). "
                "WAJIB dipakai untuk permintaan seperti 'file apa saja yang "
                "ada', 'lihat isi folder Projects', 'cek Workspace-ku'. Path "
                "kosong ('') berarti root workspace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relatif terhadap root workspace, mis. 'Projects' atau 'Documents/laporan'. Kosongkan untuk root.",
                        "default": "",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Seberapa dalam folder ditelusuri.",
                        "default": 2,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Membaca isi sebuah file teks di dalam AIRA Workspace. WAJIB "
                "dipakai kalau user minta 'baca file X', 'apa isi "
                "catatan.txt', dsb - JANGAN mengarang isi file."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path relatif file, mis. 'Documents/catatan.txt'."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Menulis/membuat/menimpa isi sebuah file teks di dalam AIRA "
                "Workspace. Kalau file sudah ada, isi lama otomatis disimpan "
                "sebagai snapshot yang bisa di-restore sebelum ditimpa - "
                "aman dipakai untuk mengedit file yang sudah ada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relatif file tujuan, mis. 'Documents/catatan.txt'."},
                    "content": {"type": "string", "description": "Isi lengkap file (menimpa seluruh isi lama)."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Membuat folder baru di dalam AIRA Workspace (termasuk folder induk yang belum ada).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path relatif folder baru, mis. 'Projects/aira-os'."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Memindahkan file/folder dari satu path ke path lain di dalam AIRA Workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Path relatif sumber."},
                    "destination": {"type": "string", "description": "Path relatif tujuan."},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Menyalin file/folder ke path lain di dalam AIRA Workspace (sumber tetap ada).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Path relatif sumber."},
                    "destination": {"type": "string", "description": "Path relatif tujuan salinan."},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Mengganti nama file/folder di dalam AIRA Workspace (tetap di folder yang sama).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Path relatif file/folder saat ini."},
                    "destination": {"type": "string", "description": "Path relatif baru (termasuk nama baru)."},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "Menghapus file/folder di dalam AIRA Workspace. TIDAK "
                "PERNAH permanen - item dipindahkan ke Trash workspace dan "
                "masih bisa dikembalikan lewat restore_file()."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path relatif file/folder yang ingin dihapus."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restore_file",
            "description": "Mengembalikan file/folder yang sebelumnya dihapus (dari Trash) ke lokasi asalnya, berdasarkan trash_id dari list_trash().",
            "parameters": {
                "type": "object",
                "properties": {"trash_id": {"type": "string", "description": "ID entri trash, didapat dari list_trash()."}},
                "required": ["trash_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_trash",
            "description": "Menampilkan daftar file/folder yang ada di Trash workspace (hasil delete_file sebelumnya), lengkap dengan trash_id untuk restore_file().",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]