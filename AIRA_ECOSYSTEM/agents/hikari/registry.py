"""
agents/hikari/registry.py — pintu masuk resmi ke HIKARI (vision).
"""

from agents.hikari import vision as v

HIKARI_TOOLS = {
    "detect_objects": v.detect_objects,
    "recognize_object": v.recognize_object,
}

HIKARI_TOOL_CATEGORY = {
    "detect_objects": "vision",
    "recognize_object": "vision",
}

HIKARI_DANGEROUS_TOOLS: set[str] = set()

HIKARI_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "detect_objects",
        "description": (
            "Membuka webcam dan melacak objek di depannya selama beberapa detik, "
            "menampilkan window live preview dengan bounding box. Deteksi terbatas "
            "pada 80 kategori umum (COCO). Gunakan saat user minta melihat/deteksi "
            "apa yang ada di depan kamera/webcam secara umum."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "camera_index": {"type": "integer", "description": "Index webcam (0 = default/utama).", "default": 0},
                "duration": {"type": "number", "description": "Lama tracking dalam detik.", "default": 4.0},
                "save_snapshot": {"type": "boolean", "description": "Simpan gambar hasil deteksi ke disk.", "default": True},
            },
            "required": [],
        },
    }},
    {"type": "function", "function": {
        "name": "recognize_object",
        "description": (
            "Mengambil satu foto dari webcam dan mencoba mengenali benda SPESIFIK "
            "yang ditunjukkan. Gunakan saat user menunjukkan benda tertentu dan "
            "minta AI mengenalinya."
        ),
        "parameters": {
            "type": "object",
            "properties": {"camera_index": {"type": "integer", "default": 0}},
            "required": [],
        },
    }},
]
