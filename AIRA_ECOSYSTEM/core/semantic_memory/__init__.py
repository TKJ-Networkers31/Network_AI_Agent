"""
core/semantic_memory/ — Semantic Memory (Sprint 2.4).

Menyimpan fakta penting pengguna dan mengambilnya kembali berdasarkan
kemiripan embedding (cosine similarity), disimpan di database/semantic_memory.db.

Public API:
    from core.semantic_memory import (
        SemanticMemory, MemoryRecord, MemoryRetriever, EmbeddingProvider,
    )

    memory = SemanticMemory()
    memory.remember("sesi-1", "Router utama memakai MikroTik RB4011", category="network")
    hasil = memory.retrieve("router apa yang dipakai?", "sesi-1", top_k=3)

BELUM diintegrasikan ke Brain / Context Builder (tugas Worker 5). Modul ini
tidak memanggil REI/LLM, tidak mempublish Event Bus, tidak melakukan network
request, dan tidak butuh dependency ML/numpy.
"""

from core.semantic_memory.embedder import DefaultEmbeddingProvider, EmbeddingProvider
from core.semantic_memory.models import MemoryCategory, MemoryRecord, RetrievalResult
from core.semantic_memory.retriever import MemoryRetriever, SemanticMemory, get_semantic_memory
from core.semantic_memory.scorer import (
    category_weight,
    combine_score,
    cosine_similarity,
    importance_score,
    recency_score,
)
from core.semantic_memory.store import MemoryStore

__all__ = [
    # API utama
    "SemanticMemory", "MemoryRecord", "MemoryRetriever", "EmbeddingProvider",
    # pendukung
    "MemoryCategory", "RetrievalResult", "MemoryStore", "DefaultEmbeddingProvider",
    "get_semantic_memory",
    "cosine_similarity", "importance_score", "recency_score",
    "category_weight", "combine_score",
]
