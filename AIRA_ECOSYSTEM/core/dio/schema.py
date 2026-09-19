import logging
import time
from typing import Any, Optional

from core.events import event_bus
from core.dio.analyzer import DIOAnalyzer
from core.dio.builder import SchemaBuilder
from core.dio.validator import SchemaValidator
from core.dio.interaction_memory import InteractionMemory, get_interaction_memory
from core.dio.models import InteractionPlan, InteractionSchema, ValidationResult
from core.dio.constants import (
    EVENT_INTERACTION_STARTED,
    EVENT_INTERACTION_GENERATED,
    EVENT_INTERACTION_COMPLETED,
    EVENT_INTERACTION_CANCELLED,
)

logger = logging.getLogger("aira.dio")


class DIO:

    def __init__(
        self,
        analyzer: Optional[DIOAnalyzer] = None,
        builder: Optional[SchemaBuilder] = None,
        validator: Optional[SchemaValidator] = None,
        memory: Optional[InteractionMemory] = None,
    ):
        self.memory = memory or get_interaction_memory()
        self.analyzer = analyzer or DIOAnalyzer(memory=self.memory)
        self.builder = builder or SchemaBuilder()
        self.validator = validator or SchemaValidator()

    def analyze_and_generate(
        self,
        user_message: str,
        planner_output: dict,
        available_capability: Optional[dict] = None,
        context: Optional[dict] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> InteractionSchema:
        plan = self.analyzer.analyze(
            user_message=user_message,
            planner_output=planner_output,
            available_capability=available_capability,
            context=context,
        )
        return self.generate_schema(plan, title=title, description=description)

    def generate_schema(
        self,
        plan: InteractionPlan,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> InteractionSchema:
        self._publish(EVENT_INTERACTION_STARTED, plan)

        try:
            schema = self.builder.build_schema(plan, title=title, description=description)
            validation = self.validator.validate(schema)
        except Exception as exc:
            logger.exception("DIO generate_schema gagal, mengembalikan schema fallback.")
            schema = InteractionSchema(
                id=f"schema_error_{int(time.time())}",
                mode="display",
                title=title or "Terjadi kesalahan",
                sections=[],
                actions=[],
                metadata={"plan_id": plan.plan_id, "error": str(exc)},
            )
            validation = ValidationResult(is_valid=False, issues=[])

        schema.metadata["validation"] = validation.to_dict()

        self._publish(
            EVENT_INTERACTION_GENERATED, plan,
            extra={"mode": schema.mode, "schema_id": schema.id},
        )

        return schema

    def complete(self, schema: InteractionSchema, plan: InteractionPlan, result_values: dict) -> None:
        self._publish(EVENT_INTERACTION_COMPLETED, plan,
                       extra={"schema_id": schema.id, "values": result_values})

    def cancel(self, schema: InteractionSchema, plan: InteractionPlan, reason: str = "user_cancelled") -> None:
        self._publish(EVENT_INTERACTION_CANCELLED, plan,
                       extra={"schema_id": schema.id, "reason": reason})

    def _publish(self, event_name: str, plan: InteractionPlan, extra: Optional[dict] = None) -> None:
        data: dict[str, Any] = {
            "interaction_id": plan.plan_id,
            "mode": plan.suggested_mode,
            "intent": plan.intent,
            "timestamp": time.time(),
        }
        if extra:
            data.update(extra)

        try:
            event_bus.publish(event_name, agent="DIO", data=data)
        except Exception:
            logger.exception("Gagal publish event %s (diabaikan).", event_name)


_dio_singleton: Optional[DIO] = None


def get_dio() -> DIO:
    global _dio_singleton

    if _dio_singleton is None:
        _dio_singleton = DIO()

    return _dio_singleton