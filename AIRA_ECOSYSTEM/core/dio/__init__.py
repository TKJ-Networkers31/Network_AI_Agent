"""
core/dio/ — Dynamic Interaction Orchestrator (DIO), Phase 2.0.

Public API:
    from core.dio import DIO, get_dio, DIOAnalyzer, SchemaBuilder, SchemaValidator, InteractionMemory
"""

from core.dio.analyzer import DIOAnalyzer
from core.dio.builder import SchemaBuilder
from core.dio.validator import SchemaValidator
from core.dio.interaction_memory import InteractionMemory, get_interaction_memory
from core.dio.schema import DIO, get_dio
from core.dio.models import (
    InteractionPlan, InteractionSchema, MissingField, ChoiceOption,
    Field, Section, Action, ValidationIssue, ValidationResult,
)

__all__ = [
    "DIO", "get_dio",
    "DIOAnalyzer", "SchemaBuilder", "SchemaValidator",
    "InteractionMemory", "get_interaction_memory",
    "InteractionPlan", "InteractionSchema", "MissingField", "ChoiceOption",
    "Field", "Section", "Action", "ValidationIssue", "ValidationResult",
]