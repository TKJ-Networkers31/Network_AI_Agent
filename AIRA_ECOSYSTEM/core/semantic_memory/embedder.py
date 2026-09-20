"""
core/semantic_memory/embedder.py — antarmuka embedding + implementasi bawaan
(Sprint 2.4).

EmbeddingProvider adalah kontrak abstrak: Semantic Memory TIDAK tahu provider
mana yang dipakai (tidak ada NVIDIA/OpenAI/Ollama yang di-hardcode di sini).
Worker berikutnya cukup membuat subclass baru dan menyuntikkannya ke
SemanticMemory / MemoryRetriever.

DefaultEmbeddingProvider = embedding PALSU tapi DETERMINISTIK berbasis hashing
(feature hashing): tanpa internet, tanpa dependency ML, tanpa numpy. Bukan
embedding semantik sungguhan - ia menangkap kemiripan LEKSIKAL (kata yang sama
dan potongan karakter yang sama), cukup untuk uji offline dan sebagai fallback.

Deterministik lintas proses: memakai hashlib.blake2b (BUKAN hash() bawaan
Python yang di-salt per proses lewat PYTHONHASHSEED).
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from core.semantic_memory.defaults import (
    EMBEDDING_DIMENSION,
    NGRAM_FEATURE_WEIGHT,
    NGRAM_SIZE,
    WORD_FEATURE_WEIGHT,
)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class EmbeddingProvider(ABC):
    """Kontrak provider embedding: teks -> vektor float."""

    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Ubah `text` menjadi vektor. Panjang vektor harus konsisten per provider."""

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class DefaultEmbeddingProvider(EmbeddingProvider):
    """
    Feature hashing deterministik.

    Tiap teks: huruf kecil -> token kata -> fitur "kata utuh" (bobot 1.0) +
    fitur character n-gram dari kata berbingkai "#kata#" (bobot 0.5). Setiap
    fitur di-hash ke satu indeks + tanda (+1/-1), dijumlahkan, lalu vektor
    dinormalisasi L2 (panjang 1). Teks tanpa token -> vektor nol.
    """

    def __init__(
        self,
        dimension: int = EMBEDDING_DIMENSION,
        ngram_size: int = NGRAM_SIZE,
    ):
        if not isinstance(dimension, int) or isinstance(dimension, bool) or dimension < 8:
            raise ValueError("dimension harus bilangan bulat >= 8.")

        if not isinstance(ngram_size, int) or isinstance(ngram_size, bool) or ngram_size < 1:
            raise ValueError("ngram_size harus bilangan bulat >= 1.")

        self._dimension = dimension
        self._ngram_size = ngram_size

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("text harus berupa string.")

        vector = [0.0] * self._dimension

        for token in _TOKEN_RE.findall(text.lower()):
            self._add(vector, "w:" + token, WORD_FEATURE_WEIGHT)

            padded = f"#{token}#"
            size = self._ngram_size

            for start in range(max(1, len(padded) - size + 1)):
                self._add(vector, "g:" + padded[start:start + size], NGRAM_FEATURE_WEIGHT)

        norm = math.sqrt(sum(value * value for value in vector))

        if norm == 0.0:
            return vector

        return [value / norm for value in vector]

    def _add(self, vector: list[float], feature: str, weight: float) -> None:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        number = int.from_bytes(digest, "big")

        index = number % self._dimension
        sign = 1.0 if (number >> 40) & 1 else -1.0

        vector[index] += sign * weight
