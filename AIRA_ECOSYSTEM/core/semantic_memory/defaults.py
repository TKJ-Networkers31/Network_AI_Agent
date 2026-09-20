"""
core/semantic_memory/defaults.py — konstanta & bobot bawaan Semantic Memory
(Sprint 2.4).

Semua angka "tuning" ada di sini supaya bisa diubah tanpa menyentuh logika
di modul lain. Modul ini SENGAJA tidak mengimpor modul AIRA mana pun (aman
diimpor di mana saja, tanpa efek samping - tidak membuat file/folder).
"""

from pathlib import Path

# ------------------------------------------------------------------ storage

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
DB_FILENAME = "semantic_memory.db"
DEFAULT_DB_FILE = BASE_DIR / "database" / DB_FILENAME

# Pseudo-session untuk fakta lintas sesi. Retrieval TIDAK menyertakannya
# kecuali diminta eksplisit (include_global=True) - isolasi sesi tetap default.
GLOBAL_SESSION_ID = "__global__"

# ---------------------------------------------------------------- embedding

EMBEDDING_DIMENSION = 256      # panjang vektor DefaultEmbeddingProvider
NGRAM_SIZE = 3                 # panjang character n-gram
WORD_FEATURE_WEIGHT = 1.0      # bobot fitur kata utuh
NGRAM_FEATURE_WEIGHT = 0.5     # bobot fitur character n-gram

# ---------------------------------------------------------------- retrieval

DEFAULT_TOP_K = 5
DEFAULT_MIN_SIMILARITY = 0.0   # ambang tambahan; similarity <= 0 TIDAK PERNAH lolos

# Skor akhir ranking = SIMILARITY_WEIGHT * cosine + IMPORTANCE_WEIGHT * importance
SIMILARITY_WEIGHT = 0.8
IMPORTANCE_WEIGHT = 0.2

# --------------------------------------------------------------- importance

DEFAULT_IMPORTANCE = 0.5       # importance manual bawaan (0-1)
RECENCY_HALF_LIFE_DAYS = 30.0  # setiap 30 hari, skor recency turun separuh

# Bobot tiga faktor importance (jumlah = 1.0 supaya hasil tetap 0-1).
IMPORTANCE_FACTOR_WEIGHTS = {
    "manual": 0.40,
    "category": 0.35,
    "recency": 0.25,
}

# Bobot per kategori (kunci = MemoryCategory.value; 0-1).
CATEGORY_WEIGHTS = {
    "user_preference": 0.90,
    "network": 0.80,
    "project": 0.80,
    "task": 0.70,
    "personal": 0.60,
    "knowledge": 0.50,
}
DEFAULT_CATEGORY_WEIGHT = 0.50  # kategori yang tidak terdaftar
