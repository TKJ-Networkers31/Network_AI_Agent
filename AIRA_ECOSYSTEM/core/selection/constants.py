"""
core/selection/constants.py — konstanta Selection Intelligence (Sprint 2.7 / W4).
"""

SOURCE_MESSAGE = "message"
VALID_SOURCE_TYPES = frozenset({SOURCE_MESSAGE})

ACTION_EXPLAIN = "explain"
ACTION_SIMPLIFY = "simplify"
ACTION_EXPAND = "expand"
ACTION_REWRITE = "rewrite"
ACTION_TRANSLATE = "translate"
ACTION_CONTINUE = "continue"
ACTION_CREATE_DOCUMENT = "create_document"
ACTION_ASK = "ask"

VALID_ACTIONS = frozenset({
    ACTION_EXPLAIN, ACTION_SIMPLIFY, ACTION_EXPAND, ACTION_REWRITE,
    ACTION_TRANSLATE, ACTION_CONTINUE, ACTION_CREATE_DOCUMENT, ACTION_ASK,
})

ACTION_LABELS = {
    ACTION_EXPLAIN: "Jelaskan bagian ini",
    ACTION_SIMPLIFY: "Sederhanakan",
    ACTION_EXPAND: "Perluas / detailkan",
    ACTION_REWRITE: "Tulis ulang",
    ACTION_TRANSLATE: "Terjemahkan",
    ACTION_CONTINUE: "Lanjutkan",
    ACTION_CREATE_DOCUMENT: "Jadikan dokumen",
    ACTION_ASK: "Tanya AIRA soal ini",
}

DEFAULT_SURROUNDING_WINDOW = 240   # karakter di kiri/kanan selection
MAX_SELECTED_TEXT_CHARS = 4000
MAX_SURROUNDING_TEXT_CHARS = 2000
DEFAULT_SELECTION_TTL_SECONDS = 3600  # 1 jam - selection bersifat sekali pakai/berumur pendek