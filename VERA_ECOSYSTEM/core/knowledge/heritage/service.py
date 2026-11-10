"""
core/knowledge/heritage/service.py — VERA Historical Knowledge & Heritage Service.

Provides deterministic, grounded access to the historical provenance, architectural decisions,
remediation stages, and evolutionary heritage of the platform (from AIRA OS origins to VERA).

This service ensures VERA possesses complete self-awareness of its engineering lineage
without confusing historical knowledge with active product identity.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vera.heritage")

HERITAGE_FILE = Path(__file__).parent / "heritage_records.json"

# Key concept mappings for deterministic scoring
CONCEPT_TRIGGERS: Dict[str, List[str]] = {
    "HERITAGE-01-ORIGIN": [
        "aira", "asal usul", "origin", "sejarah", "history", "genesis",
        "mengapa aira", "adaptive intelligent reasoning assistant", "fondasi awal", "background"
    ],
    "HERITAGE-02-EVOLUTION": [
        "networking", "rca", "14-step", "the dude", "nms", "telemetri", "topology fabric",
        "route snapshot", "mndp", "cdp", "lldp", "bounding", "routeros"
    ],
    "HERITAGE-03-REMEDIATION-STAGES": [
        "stage", "tahap", "stage 14", "stage 00", "stage 01", "stage 02", "stage 03", "stage 04",
        "stage 05", "stage 06", "stage 07", "stage 08", "stage 09", "stage 10", "stage 11",
        "stage 12", "stage 13", "remediasi", "remediation", "audit report", "consolidation"
    ],
    "HERITAGE-04-BILLING-REMOVAL": [
        "billing", "kuota", "token", "quota", "stripe", "langganan", "subscription",
        "komersialisasi", "pembayaran", "payment", "unlimited", "enterprise on-premise"
    ],
    "HERITAGE-05-VERA-EMERGENCE": [
        "vera", "transformasi", "transformation", "perubahan nama", "renaming", "rebranding",
        "transisi", "transition", "mengapa vera", "why vera", "visionary enterprise network",
        "enterprise network intelligence platform"
    ],
    "HERITAGE-06-VAE-ARCHITECTURE": [
        "vae", "adaptive experience", "dynamic interaction", "dio", "generative ui",
        "adaptive panel", "ui stream", "protocol specification", "component catalog"
    ],
    "HERITAGE-07-DESIGN-SYSTEM-RESTORATION": [
        "design system", "jet black", "cyber glass", "oled", "navy", "regresi desain",
        "38bdf8", "000000", "04060c", "cyan", "palet", "theme", "dark mode"
    ],
}


class HeritageService:
    """Historical Knowledge Service for querying platform lineage and architectural history."""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self.data_path = data_path or HERITAGE_FILE
        self._records: List[Dict[str, Any]] = []
        self._records_by_id: Dict[str, Dict[str, Any]] = {}
        self._load_records()

    def _load_records(self) -> None:
        if not self.data_path.exists():
            logger.warning(f"Heritage data file not found at: {self.data_path}")
            return

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._records = data
                    self._records_by_id = {r["record_id"]: r for r in data if "record_id" in r}
                    logger.info(f"Loaded {len(self._records)} heritage records successfully.")
        except Exception as e:
            logger.error(f"Failed to load heritage data: {e}", exc_info=True)

    def list_records(self) -> List[Dict[str, Any]]:
        """Return all heritage records."""
        return list(self._records)

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by its unique ID."""
        return self._records_by_id.get(record_id)

    def query_heritage(
        self, query: str, limit: int = 3, min_score: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        Query heritage records using token match, semantic trigger matching, and field relevance.
        Only returns records exceeding min_score threshold to avoid false positives on common words.
        """
        if not query or not self._records:
            return []

        query_normalized = query.lower()
        scored_records: List[tuple[float, Dict[str, Any]]] = []

        for record in self._records:
            rec_id = record.get("record_id", "")
            score = 0.0

            # 1. Concept Triggers match (high weight)
            triggers = CONCEPT_TRIGGERS.get(rec_id, [])
            for trigger in triggers:
                if trigger in query_normalized:
                    score += 5.0
                    # Exact word boundary match gets extra weight
                    if re.search(r"\b" + re.escape(trigger) + r"\b", query_normalized):
                        score += 5.0

            # 2. Record ID match
            if rec_id.lower() in query_normalized:
                score += 15.0

            # 3. Title match
            title = record.get("title", "").lower()
            title_en = record.get("title_en", "").lower()
            if any(term in title or term in title_en for term in query_normalized.split() if len(term) > 3):
                score += 3.0

            # 4. Description and Key Takeaways match (secondary support)
            desc = record.get("description", "").lower()
            takeaway = record.get("key_takeaways", "").lower()
            words = [w for w in re.findall(r"\w+", query_normalized) if len(w) > 4]
            for w in words:
                if w in desc:
                    score += 1.0
                if w in takeaway:
                    score += 1.5

            if score >= min_score:
                scored_records.append((score, record))

        # Sort descending by score
        scored_records.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored_records[:limit]]

    def format_heritage_snippet(self, records: List[Dict[str, Any]]) -> str:
        """Format matching heritage records into a clear context prompt block."""
        if not records:
            return ""

        lines = [
            "=== HISTORICAL ENGINEERING HERITAGE (AIRA -> VERA) ===",
            "NOTE: This is verified historical provenance. The active product is VERA.",
            ""
        ]

        for r in records:
            lines.append(f"[{r.get('record_id')}] {r.get('title')} ({r.get('title_en', '')})")
            lines.append(f"Historical Era: {r.get('historical_identity')} | Status: {r.get('current_status')}")
            lines.append(f"Description: {r.get('description')}")
            if r.get("architectural_decisions"):
                lines.append("Key Architectural Decisions:")
                for dec in r["architectural_decisions"]:
                    lines.append(f"  - {dec}")
            if r.get("key_takeaways"):
                lines.append(f"Engineering Takeaway: {r['key_takeaways']}")
            lines.append("")

        lines.append("=== END HISTORICAL HERITAGE ===")
        return "\n".join(lines)

    def answer_heritage_query(self, query: str) -> Dict[str, Any]:
        """Callable tool format for LLM or agent tool invocations."""
        results = self.query_heritage(query, limit=3)
        formatted = self.format_heritage_snippet(results)
        return {
            "success": True,
            "tool": "recall_heritage",
            "query": query,
            "count": len(results),
            "records": results,
            "context_block": formatted,
        }


_global_service: Optional[HeritageService] = None


def get_heritage_service() -> HeritageService:
    """Return the global singleton HeritageService."""
    global _global_service
    if _global_service is None:
        _global_service = HeritageService()
    return _global_service
