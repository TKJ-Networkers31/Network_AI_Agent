"""
core/vae — VERA Adaptive Experience Protocol & Runtime Package.
"""

from core.vae.models import VaeBlock, VaeBlockType, VaePayload
from core.vae.protocol import validate_vae_block, validate_vae_payload, SUPPORTED_BLOCK_TYPES
from core.vae.planner import ExperiencePlanner, ExperiencePlan, VaeIntent, PlannedBlock
from core.vae.composer import ExperienceComposer
from core.vae.adapter import brain_response_to_vae_payload
from core.vae.interaction import InteractionState, ErrorTaxonomy, classify_operational_error, InteractionStateMachine
from core.vae.recovery import RecoveryPlan, RecoveryAction, UniversalRecoveryPlanner, get_recovery_planner

__all__ = [
    "VaeBlock",
    "VaeBlockType",
    "VaePayload",
    "validate_vae_block",
    "validate_vae_payload",
    "SUPPORTED_BLOCK_TYPES",
    "ExperiencePlanner",
    "ExperiencePlan",
    "VaeIntent",
    "PlannedBlock",
    "ExperienceComposer",
    "brain_response_to_vae_payload",
    "InteractionState",
    "ErrorTaxonomy",
    "classify_operational_error",
    "InteractionStateMachine",
    "RecoveryPlan",
    "RecoveryAction",
    "UniversalRecoveryPlanner",
    "get_recovery_planner",
]
