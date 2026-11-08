"""
core/semantic_memory/retriever.py — retrieval berbasis embedding + fasad
SemanticMemory (Sprint 2.4).

  MemoryRetriever  query -> embed -> cosine similarity -> ranking -> top_k
  SemanticMemory   fasad: MemoryStore + EmbeddingProvider + MemoryRetriever
                   (remember / update / delete / get / list / retrieve)

SemanticMemory ditaruh di sini (bukan file terpisah) supaya arah dependensi
tetap satu jurusan: models/defaults <- scorer/embedder <- store <- retriever.

Aturan Sprint 2.4: tidak memanggil REI/LLM, tidak mempublish Event Bus, tidak
ada network, tidak ada dependency ML. Semantic Memory BELUM disambungkan ke
Brain / Context Builder (tugas Worker 5). Error dari EmbeddingProvider
DIPROPAGASI apa adanya - pemanggil (Worker 5) yang memutuskan degradasi aman.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Optional

from core.semantic_memory.defaults import (
    DEFAULT_IMPORTANCE,
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_TOP_K,
    GLOBAL_SESSION_ID,
    IMPORTANCE_WEIGHT,
    SIMILARITY_WEIGHT,
)
from core.semantic_memory.embedder import DefaultEmbeddingProvider, EmbeddingProvider
from core.semantic_memory.models import MemoryCategory, MemoryRecord, RetrievalResult
from core.semantic_memory.scorer import combine_score, cosine_similarity, importance_score
from core.semantic_memory.store import MemoryStore

logger = logging.getLogger("aira.semantic_memory.retriever")


def _require_session(session_id: Any) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id tidak boleh kosong.")

    return session_id.strip()


def _query_vector(embedder: EmbeddingProvider, query: str) -> list[float]:
    vector = [float(value) for value in embedder.embed(query)]

    if not all(math.isfinite(value) for value in vector):
        raise ValueError("EmbeddingProvider mengembalikan nilai NaN/inf.")

    return vector


# ============================================================ MemoryRetriever

class MemoryRetriever:

    def __init__(
        self,
        store: MemoryStore,
        embedder: Optional[EmbeddingProvider] = None,
        *,
        similarity_weight: float = SIMILARITY_WEIGHT,
        importance_weight: float = IMPORTANCE_WEIGHT,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.store = store
        self.embedder = embedder or DefaultEmbeddingProvider()
        self.similarity_weight = similarity_weight
        self.importance_weight = importance_weight
        self._clock = clock or time.time

    def retrieve(
        self,
        query: str,
        session_id: str,
        top_k: int = DEFAULT_TOP_K,
        *,
        category: Any = None,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        include_global: bool = False,
    ) -> list[RetrievalResult]:
        """
        Ambil top_k fakta paling relevan untuk `query`.

        - Hanya record milik `session_id` (isolasi sesi). include_global=True
          menambahkan record GLOBAL_SESSION_ID (fakta lintas sesi).
        - category: batasi ke satu kategori.
        - Record dengan similarity <= 0 atau < min_similarity tidak dikembalikan.
        - Record tanpa embedding, atau dengan panjang vektor beda dari query
          (mis. provider diganti), dilewati.
        - Urutan: score menurun; seri diurai similarity, updated_at, lalu id
          (deterministik).
        - Query kosong / vektor query nol / top_k=0 / store kosong -> [].
        """
        session_id = _require_session(session_id)

        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k harus bilangan bulat >= 0.")

        if not isinstance(query, str):
            raise TypeError("query harus berupa string.")

        if top_k == 0 or not query.strip():
            return []

        query_vector = _query_vector(self.embedder, query)

        if not any(query_vector):
            return []

        candidates = self.store.list(session_id, category=category)

        if include_global and session_id != GLOBAL_SESSION_ID:
            candidates += self.store.list(GLOBAL_SESSION_ID, category=category)

        now = self._clock()
        results: list[RetrievalResult] = []
        skipped = 0

        for record in candidates:
            if not record.embedding or len(record.embedding) != len(query_vector):
                skipped += 1
                continue

            similarity = cosine_similarity(query_vector, record.embedding)

            if similarity <= 0.0 or similarity < min_similarity:
                continue

            importance = importance_score(record, now)

            results.append(RetrievalResult(
                record=record,
                similarity=similarity,
                importance=importance,
                score=combine_score(
                    similarity, importance,
                    similarity_weight=self.similarity_weight,
                    importance_weight=self.importance_weight,
                ),
            ))

        if skipped:
            logger.debug("RETRIEVE | %d record dilewati (tanpa embedding / dimensi beda).", skipped)

        results.sort(key=lambda r: (-r.score, -r.similarity, -r.record.updated_at, r.record.id))

        return results[:top_k]


# ============================================================ SemanticMemory

class SemanticMemory:
    """
    Fasad tunggal. Semua argumen opsional:
        SemanticMemory()                       -> database/semantic_memory.db + embedding bawaan
        SemanticMemory(db_path=tmp / "x.db")   -> database lain (untuk test)
        SemanticMemory(embedder=MyProvider())  -> provider embedding sendiri
    """

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        embedder: Optional[EmbeddingProvider] = None,
        retriever: Optional[MemoryRetriever] = None,
        *,
        db_path: Optional[Path] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        self._clock = clock or time.time

        self.store = store or (retriever.store if retriever else MemoryStore(db_path, clock=clock))
        self.embedder = embedder or (retriever.embedder if retriever else DefaultEmbeddingProvider())
        self.retriever = retriever or MemoryRetriever(self.store, self.embedder, clock=clock)

    # ------------------------------------------------------------------ write

    def remember(
        self,
        session_id: str,
        text: str,
        *,
        category: Any = MemoryCategory.KNOWLEDGE,
        importance: float = DEFAULT_IMPORTANCE,
        metadata: Optional[dict] = None,
    ) -> MemoryRecord:
        """Buat fakta baru: validasi -> embed -> simpan. Return record tersimpan."""
        record = MemoryRecord(
            session_id=session_id, text=text, category=category,
            importance=importance, metadata=metadata or {},
            created_at=self._clock(),
        )

        return self.add(record)

    def add(self, record: MemoryRecord) -> MemoryRecord:
        """Simpan record yang sudah dibuat; kalau belum punya embedding, di-embed dulu."""
        if not record.embedding:
            record = replace(record, embedding=self.embedder.embed(record.text))

        return self.store.add(record)

    def update(
        self,
        record_id: str,
        *,
        text: Optional[str] = None,
        category: Any = None,
        importance: Optional[float] = None,
        metadata: Optional[dict] = None,
        embedding: Optional[list] = None,
    ) -> Optional[MemoryRecord]:
        """Seperti MemoryStore.update, tapi `text` baru otomatis di-embed ulang."""
        if text is not None and embedding is None:
            embedding = self.embedder.embed(text.strip() if isinstance(text, str) else text)

        return self.store.update(
            record_id, text=text, category=category, importance=importance,
            metadata=metadata, embedding=embedding,
        )

    def delete(self, record_id: str) -> bool:
        return self.store.delete(record_id)

    def clear(self, session_id: Optional[str] = None) -> int:
        return self.store.clear(session_id)

    # ------------------------------------------------------------------- read

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        return self.store.get(record_id)

    def list(self, session_id: str, *, category: Any = None, limit: Optional[int] = None) -> "list[MemoryRecord]":
        return self.store.list(session_id, category=category, limit=limit)

    def search_by_category(
        self, category: Any, session_id: Optional[str] = None, *, limit: Optional[int] = None,
    ) -> "list[MemoryRecord]":
        return self.store.search_by_category(category, session_id, limit=limit)

    def count(self, session_id: Optional[str] = None) -> int:
        return self.store.count(session_id)

    def retrieve(
        self,
        query: str,
        session_id: str,
        top_k: int = DEFAULT_TOP_K,
        *,
        category: Any = None,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        include_global: bool = False,
    ) -> "list[RetrievalResult]":
        return self.retriever.retrieve(
            query, session_id, top_k,
            category=category, min_similarity=min_similarity, include_global=include_global,
        )


# ================================================================ SINGLETON

_singleton: Optional[SemanticMemory] = None
_singleton_lock = threading.Lock()


def get_semantic_memory() -> SemanticMemory:
    """Instance global (lazy): database baru dibuat saat PERTAMA dipanggil, bukan saat import."""
    global _singleton

    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = SemanticMemory()

    return _singleton
