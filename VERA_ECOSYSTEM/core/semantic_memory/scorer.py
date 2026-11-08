"""
core/semantic_memory/scorer.py — fungsi skor murni Semantic Memory (Sprint 2.4).

  cosine_similarity  - implementasi sendiri (tanpa numpy)
  recency_score      - peluruhan eksponensial (half-life)
  category_weight    - bobot per kategori
  importance_score   - gabungan manual + kategori + recency, hasil 0..1
  combine_score      - skor akhir untuk ranking (similarity + importance)

Semua fungsi murni & deterministik: tanpa I/O, tanpa AI. Waktu "sekarang"
selalu bisa disuntik lewat parameter `now` supaya mudah diuji.
"""

from __future__ import annotations

import math
import time
from typing import Mapping, Optional, Sequence

from core.semantic_memory.defaults import (
    CATEGORY_WEIGHTS,
    DEFAULT_CATEGORY_WEIGHT,
    IMPORTANCE_FACTOR_WEIGHTS,
    IMPORTANCE_WEIGHT,
    RECENCY_HALF_LIFE_DAYS,
    SIMILARITY_WEIGHT,
)
from core.semantic_memory.models import MemoryCategory, MemoryRecord

SECONDS_PER_DAY = 86400.0


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """
    Cosine similarity a·b / (|a||b|), hasil -1..1.

    - Panjang berbeda -> ValueError.
    - Salah satu vektor nol (atau kosong) -> 0.0 (tidak ada arah = tidak mirip).
    """
    if len(a) != len(b):
        raise ValueError(f"Panjang vektor berbeda ({len(a)} vs {len(b)}).")

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0

    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    similarity = dot / (math.sqrt(norm_a) * math.sqrt(norm_b))

    return max(-1.0, min(1.0, similarity))  # buang drift floating point


def recency_score(
    updated_at: float,
    now: Optional[float] = None,
    half_life_days: float = RECENCY_HALF_LIFE_DAYS,
) -> float:
    """1.0 untuk yang baru, 0.5 setelah satu half-life, mendekati 0 untuk yang lama."""
    if half_life_days <= 0:
        raise ValueError("half_life_days harus > 0.")

    now = time.time() if now is None else now
    age_days = max(0.0, (now - updated_at) / SECONDS_PER_DAY)  # timestamp masa depan = baru

    return 0.5 ** (age_days / half_life_days)


def category_weight(category: MemoryCategory | str) -> float:
    """Bobot kategori 0..1; kategori tak terdaftar memakai bobot bawaan."""
    key = category.value if isinstance(category, MemoryCategory) else str(category).strip().lower()

    return CATEGORY_WEIGHTS.get(key, DEFAULT_CATEGORY_WEIGHT)


def importance_score(
    record: MemoryRecord,
    now: Optional[float] = None,
    *,
    half_life_days: float = RECENCY_HALF_LIFE_DAYS,
    factor_weights: Optional[Mapping[str, float]] = None,
) -> float:
    """
    Importance 0..1 = rata-rata berbobot dari tiga faktor:
      manual   - record.importance
      category - bobot kategori
      recency  - peluruhan dari updated_at
    """
    weights = factor_weights or IMPORTANCE_FACTOR_WEIGHTS

    total_weight = sum(weights.get(name, 0.0) for name in ("manual", "category", "recency"))

    if total_weight <= 0:
        return 0.0

    weighted = (
        weights.get("manual", 0.0) * record.importance
        + weights.get("category", 0.0) * category_weight(record.category)
        + weights.get("recency", 0.0) * recency_score(record.updated_at, now, half_life_days)
    )

    return max(0.0, min(1.0, weighted / total_weight))


def combine_score(
    similarity: float,
    importance: float,
    *,
    similarity_weight: float = SIMILARITY_WEIGHT,
    importance_weight: float = IMPORTANCE_WEIGHT,
) -> float:
    """
    Skor ranking akhir. Similarity negatif dihitung 0 (arah berlawanan tidak
    boleh "mengurangi" record lain lewat importance). Dengan bobot default
    (jumlah 1.0) hasilnya tetap 0..1.
    """
    return similarity_weight * max(0.0, similarity) + importance_weight * importance
