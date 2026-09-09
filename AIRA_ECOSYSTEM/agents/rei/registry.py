"""
agents/rei/registry.py — pintu masuk kemampuan riset & memori REI
(web_search, web_fetch, remember, recall, forget).
"""

from agents.rei import research_tools as rt
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
}

REI_TOOL_CATEGORY = {
    "web_search": "web",
    "web_fetch": "web",
    "remember": "memory",
    "recall": "memory",
    "forget": "memory",
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
]
