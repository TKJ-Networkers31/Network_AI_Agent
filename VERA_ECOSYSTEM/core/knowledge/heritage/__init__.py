"""
core/knowledge/heritage/__init__.py — Heritage Knowledge Package for VERA.
"""

from core.knowledge.heritage.service import (
    HeritageService,
    get_heritage_service,
)

__all__ = ["HeritageService", "get_heritage_service"]
