"""
core/model_store.py — pemilik database/model_router.db (Sprint 1).

Tabel (sesuai spec):
    models                (id, provider, model_id, display_name, label,
                           context_window, enabled, created_at)
    model_router_settings (task_label PK, default_model_id)
    model_policy          (id, fallback_model_id, retry_provider)   -> satu baris, id=1

"Migration" = init_db() yang idempotent (CREATE TABLE IF NOT EXISTS + seed
hanya kalau tabel models kosong). Aman dijalankan berkali-kali.

Seed pertama kali: kalau database/model_registry.db (Phase 1.2) ada, model di
sana diimpor (label=general, context_window=0); kalau tidak, 4 model bawaan
yang sama dengan seed lama. Semua label diarahkan ke model default lama.
API key TIDAK disimpan di sini - dibaca dari .env oleh provider_client.
"""

import logging
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.model_types import DEFAULT_LABEL, VALID_LABELS, VALID_PROVIDERS

logger = logging.getLogger("aira.model_store")

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DEFAULT_DB_FILE = DATABASE_DIR / "model_router.db"
LEGACY_DB_FILE = DATABASE_DIR / "model_registry.db"

RESERVED_IDS = {"routing", "policy", "route", "route_preview"}
_UPDATABLE = {
    "provider", "model_id", "display_name", "label", "context_window", "enabled",
    "publisher", "provider_id", "endpoint_id", "api_endpoint", "model_type",
    "max_output_tokens", "supports_streaming", "supports_tool_calling",
    "supports_structured_output", "supports_vision", "supports_audio", "supports_video",
    "capabilities_json", "supported_modalities_json", "supported_tasks_json",
    "classification_json", "availability_status", "health_status", "lifecycle_status",
    "priority", "verified_at",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT 'general',
    context_window INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    publisher TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL DEFAULT '',
    endpoint_id TEXT NOT NULL DEFAULT '',
    api_endpoint TEXT NOT NULL DEFAULT '',
    model_type TEXT NOT NULL DEFAULT 'dense',
    max_output_tokens INTEGER NOT NULL DEFAULT 4096,
    supports_streaming INTEGER NOT NULL DEFAULT 1,
    supports_tool_calling INTEGER NOT NULL DEFAULT 0,
    supports_structured_output INTEGER NOT NULL DEFAULT 1,
    supports_vision INTEGER NOT NULL DEFAULT 0,
    supports_audio INTEGER NOT NULL DEFAULT 0,
    supports_video INTEGER NOT NULL DEFAULT 0,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    supported_modalities_json TEXT NOT NULL DEFAULT '["text"]',
    supported_tasks_json TEXT NOT NULL DEFAULT '[]',
    classification_json TEXT NOT NULL DEFAULT '{}',
    availability_status TEXT NOT NULL DEFAULT 'ACTIVE',
    health_status TEXT NOT NULL DEFAULT 'HEALTHY',
    lifecycle_status TEXT NOT NULL DEFAULT 'ACTIVE',
    priority INTEGER NOT NULL DEFAULT 10,
    verified_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_models_label ON models(label);

CREATE TABLE IF NOT EXISTS model_router_settings (
    task_label TEXT PRIMARY KEY,
    default_model_id TEXT
);

CREATE TABLE IF NOT EXISTS model_policy (
    id INTEGER PRIMARY KEY,
    fallback_model_id TEXT,
    retry_provider INTEGER NOT NULL DEFAULT 0
);
"""

_BUILTIN_SEED = [
    # =========================================================================
    # CLASS A: GENERAL CHAT
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3.5-bolt-e4b",
        "display_name": "Nemotron 3.5 Bolt (Fast Agent)",
        "label": "general",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "structured_output"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["general_chat", "intent_routing", "quick_answer", "summarization", "agent_orchestration", "tool_selection_execution", "network_diagnostics", "voice_dialogue"]',
        "classification_json": '{"class": "A", "name": "General Chat", "category": "general_chat"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },
    {
        "provider": "nvidia",
        "model_id": "mistralai/mistral-large-4-1t-a52b",
        "display_name": "Mistral Large 4 (1T/52B MoE)",
        "label": "general",
        "publisher": "mistralai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 131072,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "structured_output"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["general_chat", "agent_orchestration", "complex_problem_solving"]',
        "classification_json": '{"class": "A", "name": "General Chat", "category": "general_chat"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "google/gemma-4-31b-it",
        "display_name": "Gemma 4 31B Instruct",
        "label": "general",
        "publisher": "google",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 131072,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["general_chat", "multilingual_translation"]',
        "classification_json": '{"class": "A", "name": "General Chat", "category": "general_chat"}',
        "priority": 3,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS B: REASONING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "openai/gpt-oss-20b",
        "display_name": "GPT OSS 20B (Math & Logic)",
        "label": "reasoning",
        "publisher": "openai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "math_logic"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["mathematical_reasoning", "formal_verification", "general_reasoning"]',
        "classification_json": '{"class": "B", "name": "Reasoning", "category": "mathematics"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "display_name": "Nemotron 3.5 Super (120B/12B MoE)",
        "label": "reasoning",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 131072,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "capabilities_json": '["chat", "streaming", "deep_reasoning"]',
        "supported_modalities_json": '["text", "vision"]',
        "supported_tasks_json": '["deep_reasoning", "complex_problem_solving", "root_cause_analysis", "policy_compliance_audit"]',
        "classification_json": '{"class": "B", "name": "Reasoning", "category": "general_reasoning"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },
    {
        "provider": "nvidia",
        "model_id": "z-ai/glm-5.3-flash",
        "display_name": "GLM 5.3 Flash (320B/18B MoE)",
        "label": "reasoning",
        "publisher": "z-ai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 131072,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "deep_reasoning"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["deep_reasoning", "multilingual_translation"]',
        "classification_json": '{"class": "B", "name": "Reasoning", "category": "general_reasoning"}',
        "priority": 3,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/cosmos-reason2-8b",
        "display_name": "Cosmos Reason2 8B",
        "label": "reasoning",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "capabilities_json": '["chat", "streaming", "physical_reasoning", "vision"]',
        "supported_modalities_json": '["text", "vision"]',
        "supported_tasks_json": '["physical_reasoning", "spatial_understanding"]',
        "classification_json": '{"class": "B", "name": "Reasoning", "category": "research"}',
        "priority": 4,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS C: CODING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "poolside/laguna-xs-2.1",
        "display_name": "Laguna XS 2.1 (Terminal & Agentic)",
        "label": "coding",
        "publisher": "poolside",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 65536,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "code_generation"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["code_generation", "code_review_refactoring", "scripting_shell_python", "regex_pattern_generation", "tool_selection_execution", "terminal_agentic"]',
        "classification_json": '{"class": "C", "name": "Coding", "category": "coding"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },
    {
        "provider": "nvidia",
        "model_id": "moonshotai/kimi-k2.6",
        "display_name": "Kimi K2.6 (1M Context Coding)",
        "label": "coding",
        "publisher": "moonshotai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 1048576,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "code_generation", "long_context"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["code_generation", "code_review_refactoring", "scripting_shell_python", "regex_pattern_generation"]',
        "classification_json": '{"class": "C", "name": "Coding", "category": "programming"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "minimaxai/minimax-m3.1-flash",
        "display_name": "MiniMax M3.1 Flash (Cyber & Code)",
        "label": "coding",
        "publisher": "minimaxai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 131072,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "code_generation"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["code_generation", "code_review_refactoring", "scripting_shell_python"]',
        "classification_json": '{"class": "C", "name": "Coding", "category": "devops"}',
        "priority": 3,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "deepseek-ai/deepseek-coder-6.7b-instruct",
        "display_name": "DeepSeek Coder 6.7B Instruct",
        "label": "coding",
        "publisher": "deepseek-ai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 16384,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "code_generation"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["code_generation", "linux_administration", "terminal_operations"]',
        "classification_json": '{"class": "C", "name": "Coding", "category": "terminal_operations"}',
        "priority": 4,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS D: NETWORK ENGINEERING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3-ultra-550b-a55b",
        "display_name": "Nemotron 3 Ultra (550B Network & Plan)",
        "label": "networking",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 1048576,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "network_planning", "long_context"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["network_topology_analysis", "network_planning_capacity", "protocol_debugging", "multi_step_planning"]',
        "classification_json": '{"class": "D", "name": "Network Engineering", "category": "network_engineering"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "display_name": "Nemotron 3.5 Lightning (30B Domain)",
        "label": "networking",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 65536,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "network_diagnostics"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["network_diagnostics", "configuration_synthesis", "alert_correlation", "network_troubleshooting", "routing_protocols", "subnetting"]',
        "classification_json": '{"class": "D", "name": "Network Engineering", "category": "network_troubleshooting"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },

    # =========================================================================
    # CLASS E: AGENTIC / TOOL CALLING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "poolside/laguna-xs-2.1",
        "display_name": "Laguna XS 2.1 (Execution Agent)",
        "label": "automation",
        "publisher": "poolside",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 65536,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "automation"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["workflow_automation_dag", "tool_selection_execution", "configuration_synthesis"]',
        "classification_json": '{"class": "E", "name": "Agentic / Tool Calling", "category": "automation"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },
    {
        "provider": "nvidia",
        "model_id": "moonshotai/kimi-k2.6",
        "display_name": "Kimi K2.6 (Ansible Playbooks)",
        "label": "automation",
        "publisher": "moonshotai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 1048576,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "tool_calling", "automation", "long_context"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["workflow_automation_dag", "configuration_synthesis"]',
        "classification_json": '{"class": "E", "name": "Agentic / Tool Calling", "category": "automation"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS F: LONG-CONTEXT / RAG
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "stepfun-ai/step-5-preview",
        "display_name": "Step 5 Preview (1M Long-Context RAG)",
        "label": "retrieval",
        "publisher": "stepfun-ai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 1048576,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "long_context"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["knowledge_retrieval_rag", "document_qa", "incident_rca_synthesis", "long_context_analysis"]',
        "classification_json": '{"class": "F", "name": "Long-Context / RAG", "category": "long_context_analysis"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "display_name": "Nemotron 3.5 Lightning (Fast RAG)",
        "label": "retrieval",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 65536,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "retrieval", "tool_calling"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["knowledge_retrieval_rag", "document_qa", "incident_rca_synthesis"]',
        "classification_json": '{"class": "F", "name": "Long-Context / RAG", "category": "retrieval"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },

    # =========================================================================
    # CLASS G: VISION / MULTIMODAL
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "meta/llama-3.2-90b-vision-instruct",
        "display_name": "Llama 3.2 90B Vision",
        "label": "vision",
        "publisher": "meta",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 131072,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "capabilities_json": '["chat", "streaming", "vision", "tool_calling"]',
        "supported_modalities_json": '["text", "vision"]',
        "supported_tasks_json": '["multimodal_vision_diagram", "topology_rendering", "chart_table_understanding", "vision_analysis"]',
        "classification_json": '{"class": "G", "name": "Vision / Multimodal", "category": "vision_analysis"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "deepseek-ai/deepseek-v4.1-flash",
        "display_name": "DeepSeek V4.1 Flash (Multimodal)",
        "label": "vision",
        "publisher": "deepseek-ai",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "moe",
        "context_window": 131072,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "capabilities_json": '["chat", "streaming", "vision"]',
        "supported_modalities_json": '["text", "vision"]',
        "supported_tasks_json": '["multimodal_vision_diagram", "chart_table_understanding", "image_understanding"]',
        "classification_json": '{"class": "G", "name": "Vision / Multimodal", "category": "image_understanding"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "meta/muse-glimmer-30b",
        "display_name": "Muse Glimmer 30B (Vision Reasoning)",
        "label": "vision",
        "publisher": "meta",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 65536,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "capabilities_json": '["chat", "streaming", "vision"]',
        "supported_modalities_json": '["text", "vision"]',
        "supported_tasks_json": '["multimodal_vision_diagram"]',
        "classification_json": '{"class": "G", "name": "Vision / Multimodal", "category": "vision_analysis"}',
        "priority": 3,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS H: IMAGE AND DOCUMENT UNDERSTANDING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-parse-2.0",
        "display_name": "Nemotron Parse 2.0 (Document & OCR)",
        "label": "automation",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "capabilities_json": '["document_processing", "ocr_extraction"]',
        "supported_modalities_json": '["text", "vision"]',
        "supported_tasks_json": '["document_processing", "ocr_extraction"]',
        "classification_json": '{"class": "H", "name": "Image and Document Understanding", "category": "document_processing"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "google/deplot",
        "display_name": "DePlot (Visual Table & Plot Extraction)",
        "label": "vision",
        "publisher": "google",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 8192,
        "max_output_tokens": 2048,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "capabilities_json": '["plot_understanding", "table_extraction"]',
        "supported_modalities_json": '["text", "vision"]',
        "supported_tasks_json": '["chart_table_understanding", "image_understanding"]',
        "classification_json": '{"class": "H", "name": "Image and Document Understanding", "category": "image_understanding"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS I: EMBEDDING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3-embed-1b",
        "display_name": "Nemotron 3 Embed 1B (2048-dim)",
        "label": "retrieval",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "embedding",
        "context_window": 8192,
        "max_output_tokens": 0,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 0,
        "supports_vision": 0,
        "capabilities_json": '["embedding"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["embedding", "knowledge_retrieval_rag"]',
        "classification_json": '{"class": "I", "name": "Embedding", "category": "embedding"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3.5-embed-1b",
        "display_name": "Nemotron 3.5 Embed 1B",
        "label": "retrieval",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "embedding",
        "context_window": 8192,
        "max_output_tokens": 0,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 0,
        "supports_vision": 0,
        "capabilities_json": '["embedding"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["embedding"]',
        "classification_json": '{"class": "I", "name": "Embedding", "category": "embedding"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "snowflake/arctic-embed-l",
        "display_name": "Arctic Embed Large (1024-dim)",
        "label": "retrieval",
        "publisher": "snowflake",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "embedding",
        "context_window": 8192,
        "max_output_tokens": 0,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 0,
        "supports_vision": 0,
        "capabilities_json": '["embedding"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["embedding"]',
        "classification_json": '{"class": "I", "name": "Embedding", "category": "embedding"}',
        "priority": 3,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/embed-qa-4",
        "display_name": "Embed QA 4",
        "label": "retrieval",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "embedding",
        "context_window": 8192,
        "max_output_tokens": 0,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 0,
        "supports_vision": 0,
        "capabilities_json": '["embedding"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["embedding"]',
        "classification_json": '{"class": "I", "name": "Embedding", "category": "embedding"}',
        "priority": 4,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS J: RERANKING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-4-340b-reward",
        "display_name": "Nemotron 4 340B (Rerank & Reward)",
        "label": "retrieval",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 4096,
        "max_output_tokens": 1024,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["reranking", "scoring"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["reranking"]',
        "classification_json": '{"class": "J", "name": "Reranking", "category": "reranking"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS K: SPEECH / AUDIO
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3.5-bolt-e4b",
        "display_name": "Nemotron 3.5 Bolt (Voice Dialogue)",
        "label": "voice",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 1,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["chat", "streaming", "voice_dialogue"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["voice_dialogue", "audio_processing", "voice_generation"]',
        "classification_json": '{"class": "K", "name": "Speech / Audio", "category": "voice_generation"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
        "verified_at": "2026-11-10T06:55:00Z",
    },

    # =========================================================================
    # CLASS L: TRANSLATION
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/riva-translate-4b-instruct-v2",
        "display_name": "Riva Translate 4B v2 (Multilingual)",
        "label": "general",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 16384,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["translation"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["translation", "multilingual_translation"]',
        "classification_json": '{"class": "L", "name": "Translation", "category": "translation"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/riva-translate-4b-instruct",
        "display_name": "Riva Translate 4B (Instruct)",
        "label": "general",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 16384,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["translation"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["translation"]',
        "classification_json": '{"class": "L", "name": "Translation", "category": "translation"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS M: CONTENT SAFETY
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3.5-content-safety",
        "display_name": "Nemotron 3.5 Content Safety",
        "label": "networking",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 8192,
        "max_output_tokens": 1024,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["content_safety", "moderation"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["content_safety", "cybersecurity"]',
        "classification_json": '{"class": "M", "name": "Content Safety", "category": "content_safety"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "nvidia/llama-3.1-nemoguard-8b-content-safety",
        "display_name": "NeMo Guard 8B Safety",
        "label": "networking",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 8192,
        "max_output_tokens": 1024,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["content_safety"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["content_safety"]',
        "classification_json": '{"class": "M", "name": "Content Safety", "category": "content_safety"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS N: VIDEO UNDERSTANDING
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/ai-synthetic-video-detector",
        "display_name": "Synthetic Video & Media Detector",
        "label": "vision",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 16384,
        "max_output_tokens": 2048,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 1,
        "supports_video": 1,
        "capabilities_json": '["video_analysis", "media_detection"]',
        "supported_modalities_json": '["video", "vision", "text"]',
        "supported_tasks_json": '["video_understanding", "vision_analysis"]',
        "classification_json": '{"class": "N", "name": "Video Understanding", "category": "vision_analysis"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },

    # =========================================================================
    # CLASS O: SPECIALIZED DOMAIN MODELS
    # =========================================================================
    {
        "provider": "nvidia",
        "model_id": "nvidia/ising-calibration-1.5-31b",
        "display_name": "Ising Calibration 1.5 31B (Optimization & Physics)",
        "label": "reasoning",
        "publisher": "nvidia",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["domain_optimization", "physics_reasoning"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["specialized_domain", "research"]',
        "classification_json": '{"class": "O", "name": "Specialized Domain Models", "category": "research"}',
        "priority": 1,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "nvidia",
        "model_id": "writer/palmyra-fin-70b-32k",
        "display_name": "Palmyra Fin 70B (Financial Domain)",
        "label": "reasoning",
        "publisher": "writer",
        "api_endpoint": "https://integrate.api.nvidia.com/v1",
        "model_type": "dense",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "supports_streaming": 1,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["financial_domain", "compliance"]',
        "supported_modalities_json": '["text"]',
        "supported_tasks_json": '["financial_domain", "documentation"]',
        "classification_json": '{"class": "O", "name": "Specialized Domain Models", "category": "documentation"}',
        "priority": 2,
        "availability_status": "ACTIVE",
        "lifecycle_status": "ACTIVE",
    },
    {
        "provider": "kumo",
        "model_id": "kumo/kumo-tabular",
        "display_name": "Kumo Tabular (Offline / Downloadable Only)",
        "label": "automation",
        "publisher": "kumo",
        "api_endpoint": "local://offline",
        "model_type": "gnn",
        "context_window": 8192,
        "max_output_tokens": 0,
        "supports_streaming": 0,
        "supports_tool_calling": 0,
        "supports_structured_output": 1,
        "supports_vision": 0,
        "capabilities_json": '["graph_neural_networks", "tabular_learning"]',
        "supported_modalities_json": '["tabular"]',
        "supported_tasks_json": '["tabular_learning"]',
        "classification_json": '{"class": "O", "name": "Specialized Domain Models", "category": "automation"}',
        "priority": 10,
        "enabled": 0,
        "availability_status": "UNAVAILABLE",
        "lifecycle_status": "DOWNLOADABLE_ONLY",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_") or "model"


def _unique_id(conn: sqlite3.Connection, base: str) -> str:
    base = f"{base}_model" if base in RESERVED_IDS else base
    candidate, n = base, 2
    while conn.execute("SELECT 1 FROM models WHERE id = ?", (candidate,)).fetchone():
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def _validate_fields(fields: dict, partial: bool) -> tuple[Optional[dict], Optional[str]]:
    """Return (clean, error). partial=True -> hanya field yang ada divalidasi."""
    clean: dict = {}

    if "provider" in fields or not partial:
        provider = str(fields.get("provider") or "").strip().lower()
        if provider not in VALID_PROVIDERS:
            return None, f"Provider '{provider}' tidak valid. Pilihan: {', '.join(VALID_PROVIDERS)}."
        clean["provider"] = provider

    for key, human in (("model_id", "Model ID"), ("display_name", "Display name")):
        if key in fields or not partial:
            value = str(fields.get(key) or "").strip()
            if not value:
                return None, f"{human} wajib diisi."
            clean[key] = value

    if "label" in fields or not partial:
        label = str(fields.get("label") or DEFAULT_LABEL).strip().lower()
        if label not in VALID_LABELS:
            return None, f"Label '{label}' tidak valid. Pilihan: {', '.join(VALID_LABELS)}."
        clean["label"] = label

    if "context_window" in fields or not partial:
        try:
            window = int(fields.get("context_window") or 0)
        except (TypeError, ValueError):
            return None, "Context window harus berupa angka."
        if window < 0:
            return None, "Context window tidak boleh negatif."
        clean["context_window"] = window

    if "enabled" in fields or not partial:
        clean["enabled"] = 1 if fields.get("enabled", True) else 0

    for field in ("publisher", "api_endpoint", "model_type", "availability_status", "lifecycle_status", "health_status", "verified_at"):
        if field in fields:
            clean[field] = str(fields[field] or "").strip()

    for field in ("max_output_tokens", "priority"):
        if field in fields:
            try:
                clean[field] = int(fields[field] or 0)
            except (TypeError, ValueError):
                pass

    for field in ("supports_streaming", "supports_tool_calling", "supports_structured_output", "supports_vision", "supports_audio", "supports_video"):
        if field in fields:
            clean[field] = 1 if fields[field] else 0

    for field in ("capabilities_json", "supported_modalities_json", "supported_tasks_json", "classification_json"):
        if field in fields:
            val = fields[field]
            if isinstance(val, (dict, list)):
                import json
                clean[field] = json.dumps(val)
            else:
                clean[field] = str(val or "")

    return clean, None


class ModelStore:

    def __init__(self, db_path: Optional[Path] = None, seed: bool = True):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._seed = seed
        self._lock = threading.RLock()
        self._last_sync_info = {
            "provider": "nvidia",
            "synced_at": "",
            "remote_count": 0,
            "updated_count": 0,
            "status": "INITIALIZED",
        }
        self.init_db()

    # ------------------------------------------------------------ infra

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["enabled"] = bool(data.get("enabled", 1))
        for flag in (
            "supports_streaming", "supports_tool_calling", "supports_structured_output",
            "supports_vision", "supports_audio", "supports_video",
        ):
            if flag in data:
                data[flag] = bool(data[flag])
        import json
        for json_field, target_key in (
            ("capabilities_json", "capabilities"),
            ("supported_modalities_json", "supported_modalities"),
            ("supported_tasks_json", "supported_tasks"),
            ("classification_json", "classification"),
        ):
            if json_field in data and data[json_field]:
                try:
                    data[target_key] = json.loads(data[json_field])
                except Exception:
                    data[target_key] = [] if target_key != "classification" else {}
            elif target_key not in data:
                data[target_key] = [] if target_key != "classification" else {}
        return data

    def init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(SCHEMA_SQL)
            # Schema migration: check missing columns
            existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(models)").fetchall()}
            new_columns = {
                "publisher": "TEXT NOT NULL DEFAULT ''",
                "provider_id": "TEXT NOT NULL DEFAULT ''",
                "endpoint_id": "TEXT NOT NULL DEFAULT ''",
                "api_endpoint": "TEXT NOT NULL DEFAULT ''",
                "model_type": "TEXT NOT NULL DEFAULT 'dense'",
                "max_output_tokens": "INTEGER NOT NULL DEFAULT 4096",
                "supports_streaming": "INTEGER NOT NULL DEFAULT 1",
                "supports_tool_calling": "INTEGER NOT NULL DEFAULT 0",
                "supports_structured_output": "INTEGER NOT NULL DEFAULT 1",
                "supports_vision": "INTEGER NOT NULL DEFAULT 0",
                "supports_audio": "INTEGER NOT NULL DEFAULT 0",
                "supports_video": "INTEGER NOT NULL DEFAULT 0",
                "capabilities_json": "TEXT NOT NULL DEFAULT '[]'",
                "supported_modalities_json": "TEXT NOT NULL DEFAULT '[\"text\"]'",
                "supported_tasks_json": "TEXT NOT NULL DEFAULT '[]'",
                "classification_json": "TEXT NOT NULL DEFAULT '{}'",
                "availability_status": "TEXT NOT NULL DEFAULT 'ACTIVE'",
                "health_status": "TEXT NOT NULL DEFAULT 'HEALTHY'",
                "lifecycle_status": "TEXT NOT NULL DEFAULT 'ACTIVE'",
                "priority": "INTEGER NOT NULL DEFAULT 10",
                "verified_at": "TEXT NOT NULL DEFAULT ''",
            }
            for col, col_type in new_columns.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE models ADD COLUMN {col} {col_type}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_models_lifecycle ON models(lifecycle_status)")
            conn.commit()

        if self._seed:
            self._seed_if_empty()
            self._sync_seed_metadata()

        with self._lock, closing(self._connect()) as conn:
            for label in VALID_LABELS:
                conn.execute(
                    "INSERT OR IGNORE INTO model_router_settings (task_label, default_model_id) "
                    "VALUES (?, NULL)", (label,),
                )
            conn.execute(
                "INSERT OR IGNORE INTO model_policy (id, fallback_model_id, retry_provider) "
                "VALUES (1, NULL, 1)"
            )
            conn.commit()

    def _sync_seed_metadata(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            # Fix typos if present
            conn.execute("UPDATE models SET model_id = 'z-ai/glm-5.3-flash' WHERE model_id = 'z-ai/glm-5-3-flash'")
            
            # Insert any missing seed models
            existing_pairs = {(r["model_id"], r["label"]) for r in conn.execute("SELECT model_id, label FROM models").fetchall()}
            for spec in _BUILTIN_SEED:
                pair = (spec["model_id"], spec.get("label", DEFAULT_LABEL))
                if pair not in existing_pairs:
                    new_id = _unique_id(conn, _slugify(spec["display_name"]))
                    conn.execute(
                        "INSERT INTO models ("
                        "id, provider, model_id, display_name, label, context_window, enabled, created_at, "
                        "publisher, api_endpoint, model_type, max_output_tokens, supports_streaming, "
                        "supports_tool_calling, supports_structured_output, supports_vision, "
                        "capabilities_json, supported_modalities_json, supported_tasks_json, classification_json, "
                        "availability_status, health_status, lifecycle_status, priority, verified_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            new_id, spec["provider"], spec["model_id"], spec["display_name"],
                            spec.get("label", DEFAULT_LABEL), int(spec.get("context_window", 0)),
                            1 if spec.get("enabled", True) else 0, _now_iso(),
                            spec.get("publisher", ""), spec.get("api_endpoint", ""),
                            spec.get("model_type", "dense"), int(spec.get("max_output_tokens", 4096)),
                            int(spec.get("supports_streaming", 1)), int(spec.get("supports_tool_calling", 0)),
                            int(spec.get("supports_structured_output", 1)), int(spec.get("supports_vision", 0)),
                            spec.get("capabilities_json", "[]"), spec.get("supported_modalities_json", '["text"]'),
                            spec.get("supported_tasks_json", "[]"), spec.get("classification_json", "{}"),
                            spec.get("availability_status", "ACTIVE"), "HEALTHY",
                            spec.get("lifecycle_status", "ACTIVE"), int(spec.get("priority", 10)),
                            spec.get("verified_at", ""),
                        ),
                    )
                    existing_pairs.add(pair)

            for spec in _BUILTIN_SEED:
                conn.execute("""
                    UPDATE models SET
                        publisher = CASE WHEN publisher = '' THEN ? ELSE publisher END,
                        api_endpoint = CASE WHEN api_endpoint = '' THEN ? ELSE api_endpoint END,
                        model_type = CASE WHEN model_type = 'dense' AND ? != 'dense' THEN ? ELSE model_type END,
                        classification_json = CASE WHEN classification_json = '{}' OR classification_json = '' THEN ? ELSE classification_json END,
                        supports_streaming = ?,
                        supports_tool_calling = ?,
                        supports_vision = ?,
                        capabilities_json = CASE WHEN capabilities_json = '[]' THEN ? ELSE capabilities_json END,
                        supported_modalities_json = CASE WHEN supported_modalities_json = '["text"]' THEN ? ELSE supported_modalities_json END,
                        supported_tasks_json = CASE WHEN supported_tasks_json = '[]' THEN ? ELSE supported_tasks_json END,
                        priority = ?,
                        verified_at = CASE WHEN verified_at = '' THEN ? ELSE verified_at END
                    WHERE model_id = ? AND label = ?
                """, (
                    spec.get("publisher", ""),
                    spec.get("api_endpoint", ""),
                    spec.get("model_type", "dense"),
                    spec.get("model_type", "dense"),
                    spec.get("classification_json", "{}"),
                    spec.get("supports_streaming", 1),
                    spec.get("supports_tool_calling", 0),
                    spec.get("supports_vision", 0),
                    spec.get("capabilities_json", "[]"),
                    spec.get("supported_modalities_json", '["text"]'),
                    spec.get("supported_tasks_json", "[]"),
                    spec.get("priority", 10),
                    spec.get("verified_at", ""),
                    spec["model_id"],
                    spec.get("label", DEFAULT_LABEL),
                ))

            # Auto-route general to nemotron-3.5-bolt-e4b if currently mistral (which experiences read timeouts)
            bolt_row = conn.execute("SELECT id FROM models WHERE model_id = 'nvidia/nemotron-3.5-bolt-e4b' AND enabled = 1").fetchone()
            if bolt_row:
                gen_setting = conn.execute("SELECT default_model_id FROM model_router_settings WHERE task_label = 'general'").fetchone()
                if gen_setting and "mistral" in (gen_setting["default_model_id"] or "").lower():
                    conn.execute("UPDATE model_router_settings SET default_model_id = ? WHERE task_label = 'general'", (bolt_row["id"],))

            # Gemini models tool-calling, streaming, and vision capability assurance
            conn.execute("UPDATE models SET supports_tool_calling = 1, supports_streaming = 1, supports_structured_output = 1, supports_vision = 1 WHERE provider = 'gemini'")
            # If gemini_2_0_flash is pointed to gemini-3.8-flash (temporarily 503 on Google) or older 2.0, point to gemini-3.5-flash
            conn.execute("UPDATE models SET model_id = 'gemini-3.5-flash', display_name = 'Gemini 3.5 Flash' WHERE id = 'gemini_2_0_flash' AND model_id IN ('gemini-2.0-flash', 'gemini-3.8-flash')")

            conn.commit()

    # ------------------------------------------------------------- seed

    def _read_legacy(self) -> list[dict]:
        if not LEGACY_DB_FILE.exists():
            return []
        try:
            from core.model_registry import list_models as legacy_list_models
            rows = legacy_list_models(mask_api_key=True)
        except Exception:
            logger.exception("Gagal membaca registry lama (diabaikan, pakai seed bawaan).")
            return []

        return [{
            "provider": r["provider"], "model_id": r["model_id"],
            "display_name": r["nickname"], "label": DEFAULT_LABEL,
            "context_window": 0, "enabled": r["enabled"],
            "is_default": r["is_default"], "is_fallback": r["is_fallback"],
        } for r in rows]

    def _seed_if_empty(self) -> None:
        with closing(self._connect()) as conn:
            if conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()["c"]:
                return

        specs, default_idx, fallback_idx, source = list(_BUILTIN_SEED), 0, 1, "seed bawaan"

        with self._lock, closing(self._connect()) as conn:
            ids = []
            for spec in specs:
                new_id = _unique_id(conn, _slugify(spec["display_name"]))
                conn.execute(
                    "INSERT INTO models ("
                    "id, provider, model_id, display_name, label, context_window, enabled, created_at, "
                    "publisher, api_endpoint, model_type, max_output_tokens, supports_streaming, "
                    "supports_tool_calling, supports_structured_output, supports_vision, "
                    "capabilities_json, supported_modalities_json, supported_tasks_json, classification_json, "
                    "availability_status, health_status, lifecycle_status, priority, verified_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id, spec["provider"], spec["model_id"], spec["display_name"],
                        spec.get("label", DEFAULT_LABEL), int(spec.get("context_window", 0)),
                        1 if spec.get("enabled", True) else 0, _now_iso(),
                        spec.get("publisher", ""), spec.get("api_endpoint", ""),
                        spec.get("model_type", "dense"), int(spec.get("max_output_tokens", 4096)),
                        int(spec.get("supports_streaming", 1)), int(spec.get("supports_tool_calling", 0)),
                        int(spec.get("supports_structured_output", 1)), int(spec.get("supports_vision", 0)),
                        spec.get("capabilities_json", "[]"), spec.get("supported_modalities_json", '["text"]'),
                        spec.get("supported_tasks_json", "[]"), spec.get("classification_json", "{}"),
                        spec.get("availability_status", "ACTIVE"),
                        spec.get("health_status", "HEALTHY"), spec.get("lifecycle_status", "ACTIVE"),
                        int(spec.get("priority", 10)), spec.get("verified_at", ""),
                    ),
                )
                ids.append(new_id)

            label_to_id = {}
            for new_id, spec in zip(ids, specs):
                lbl = spec.get("label", DEFAULT_LABEL)
                if lbl not in label_to_id:
                    label_to_id[lbl] = new_id

            for label in VALID_LABELS:
                default_model = label_to_id.get(label) or ids[default_idx]
                conn.execute(
                    "INSERT OR REPLACE INTO model_router_settings (task_label, default_model_id) "
                    "VALUES (?, ?)", (label, default_model),
                )
            conn.execute(
                "INSERT OR REPLACE INTO model_policy (id, fallback_model_id, retry_provider) "
                "VALUES (1, ?, 2)", (ids[fallback_idx],),
            )
            conn.commit()

        logger.info("MODEL STORE | seed dari %s (%d model).", source, len(specs))

    # ----------------------------------------------------------- models

    def list_models(self, label: Optional[str] = None, search: Optional[str] = None,
                    enabled_only: bool = False) -> list[dict]:
        conditions, params = [], []

        if label and label != "all":
            conditions.append("label = ?")
            params.append(label)
        if enabled_only:
            conditions.append("enabled = 1")
        if search:
            like = f"%{search.strip().lower()}%"
            conditions.append("(LOWER(display_name) LIKE ? OR LOWER(model_id) LIKE ?)")
            params += [like, like]

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with closing(self._connect()) as conn:
            rows = conn.execute(f"SELECT * FROM models {where} ORDER BY rowid ASC", params).fetchall()

        return [self._to_dict(r) for r in rows]

    def get_model(self, record_id: Optional[str]) -> Optional[dict]:
        if not record_id:
            return None
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM models WHERE id = ?", (record_id,)).fetchone()
        return self._to_dict(row) if row else None

    def create_model(self, provider: str, model_id: str, display_name: str,
                     label: str = DEFAULT_LABEL, context_window: int = 0,
                     enabled: bool = True, custom_id: Optional[str] = None, **extra_fields) -> dict:
        fields = {
            "provider": provider, "model_id": model_id, "display_name": display_name,
            "label": label, "context_window": context_window, "enabled": enabled,
        }
        fields.update(extra_fields)
        clean, error = _validate_fields(fields, partial=False)
        if error:
            return {"success": False, "error": error}

        with self._lock, closing(self._connect()) as conn:
            if custom_id:
                new_id = _slugify(custom_id)
                if new_id in RESERVED_IDS or conn.execute(
                    "SELECT 1 FROM models WHERE id = ?", (new_id,)
                ).fetchone():
                    return {"success": False, "error": f"ID '{new_id}' sudah dipakai."}
            else:
                new_id = _unique_id(conn, _slugify(clean["display_name"]))

            cols = ["id", "created_at"] + list(clean.keys())
            placeholders = ["?"] * len(cols)
            vals = [new_id, _now_iso()] + list(clean.values())

            conn.execute(
                f"INSERT INTO models ({', '.join(cols)}) VALUES ({', '.join(placeholders)})",
                vals,
            )
            conn.commit()

        logger.info("MODEL CREATE | id=%s provider=%s label=%s", new_id, clean["provider"], clean["label"])
        return {"success": True, "model": self.get_model(new_id)}

    def find_models(
        self,
        capability: Optional[str] = None,
        modality: Optional[str] = None,
        task: Optional[str] = None,
        label: Optional[str] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        lifecycle: Optional[str] = None,
        availability: Optional[str] = None,
        search: Optional[str] = None,
        enabled_only: bool = True,
    ) -> list[dict]:
        """
        Capability-aware multi-attribute model query (Section 3).
        """
        models = self.list_models(label=label, search=search, enabled_only=enabled_only)
        filtered = []
        for m in models:
            if provider and m.get("provider") != provider:
                continue
            if status and m.get("availability_status") != status and m.get("lifecycle_status") != status and m.get("health_status") != status:
                continue
            if lifecycle and m.get("lifecycle_status") != lifecycle:
                continue
            if availability and m.get("availability_status") != availability:
                continue
            if capability:
                caps = m.get("capabilities", [])
                if capability == "tool_calling" and not (m.get("supports_tool_calling") or "tool_calling" in caps):
                    continue
                elif capability == "streaming" and not (m.get("supports_streaming") or "streaming" in caps):
                    continue
                elif capability == "vision" and not (m.get("supports_vision") or "vision" in caps):
                    continue
                elif capability not in caps and not m.get(f"supports_{capability}"):
                    continue
            if modality:
                mods = m.get("supported_modalities", ["text"])
                if modality not in mods:
                    continue
            if task:
                tasks = m.get("supported_tasks", [])
                if task not in tasks and m.get("label") != task:
                    continue
            filtered.append(m)

        filtered.sort(key=lambda x: int(x.get("priority") or 10))
        return filtered

    def update_model_health(self, record_id: str, status: str, verified: bool = False) -> dict:
        updates = {"health_status": status}
        if verified:
            updates["verified_at"] = _now_iso()
            updates["availability_status"] = "ACTIVE"
        return self.update_model(record_id, **updates)

    def get_sync_status(self) -> dict:
        with self._lock:
            models = self.list_models()
            nvidia_models = [m for m in models if m.get("provider") == "nvidia"]
            status_copy = dict(self._last_sync_info)
            status_copy["registered_models_count"] = len(models)
            status_copy["nvidia_models_count"] = len(nvidia_models)
            return status_copy

    def sync_from_remote_catalog(self, provider: str = "nvidia", api_key: Optional[str] = None) -> dict:
        """
        Discovers remote models from upstream provider API (e.g. NVIDIA NIM GET /v1/models)
        and updates local registry availability and lifecycle status.
        """
        import os
        import requests
        if provider != "nvidia":
            return {"success": False, "error": f"Provider '{provider}' discovery not supported"}

        key = api_key or os.getenv("NVIDIA_API_KEY")
        if not key:
            return {"success": False, "error": "NVIDIA_API_KEY is not configured"}

        url = "https://integrate.api.nvidia.com/v1/models"
        try:
            resp = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            remote_models = {m["id"]: m for m in data.get("data", [])}
        except Exception as exc:
            logger.error("Failed to sync remote catalog from %s: %s", url, exc)
            return {"success": False, "error": str(exc)}

        registered = self.list_models()
        updated_count = 0
        now_ts = _now_iso()

        for model in registered:
            if model.get("provider") != "nvidia":
                continue
            mid = model.get("model_id")
            if mid in remote_models:
                if model.get("lifecycle_status") != "ACTIVE":
                    self.update_model(model["id"], lifecycle_status="ACTIVE", health_status="HEALTHY")
                    updated_count += 1
            else:
                if model.get("lifecycle_status") == "ACTIVE":
                    self.update_model(model["id"], lifecycle_status="DEPRECATED_PENDING", health_status="UNAVAILABLE")
                    updated_count += 1

        res = {
            "success": True,
            "provider": provider,
            "remote_count": len(remote_models),
            "updated_count": updated_count,
            "synced_at": now_ts,
            "status": "SYNCED",
        }
        with self._lock:
            self._last_sync_info.update(res)
        return res

    def update_model(self, record_id: str, **fields) -> dict:
        if not self.get_model(record_id):
            return {"success": False, "not_found": True, "error": f"Model '{record_id}' tidak ditemukan."}

        fields = {k: v for k, v in fields.items() if k in _UPDATABLE and v is not None}
        clean, error = _validate_fields(fields, partial=True)
        if error:
            return {"success": False, "error": error}
        if not clean:
            return {"success": True, "model": self.get_model(record_id)}

        set_sql = ", ".join(f"{key} = ?" for key in clean)  # key hanya dari _validate_fields

        with self._lock, closing(self._connect()) as conn:
            conn.execute(f"UPDATE models SET {set_sql} WHERE id = ?", [*clean.values(), record_id])
            conn.commit()

        logger.info("MODEL UPDATE | id=%s fields=%s", record_id, list(clean))
        return {"success": True, "model": self.get_model(record_id)}

    def usage_of(self, record_id: str) -> dict:
        with closing(self._connect()) as conn:
            labels = [r["task_label"] for r in conn.execute(
                "SELECT task_label FROM model_router_settings WHERE default_model_id = ?", (record_id,)
            ).fetchall()]
            policy = conn.execute("SELECT fallback_model_id FROM model_policy WHERE id = 1").fetchone()

        return {
            "default_for": labels,
            "is_fallback": bool(policy and policy["fallback_model_id"] == record_id),
        }

    def delete_model(self, record_id: str) -> dict:
        if not self.get_model(record_id):
            return {"success": False, "not_found": True, "error": f"Model '{record_id}' tidak ditemukan."}

        usage = self.usage_of(record_id)
        if usage["default_for"] or usage["is_fallback"]:
            parts = []
            if usage["default_for"]:
                parts.append("default untuk " + ", ".join(usage["default_for"]))
            if usage["is_fallback"]:
                parts.append("model fallback")
            return {
                "success": False, "in_use": True,
                "error": "Model masih dipakai sebagai " + " dan ".join(parts)
                         + ". Ganti dulu di Default Routing.",
            }

        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM models WHERE id = ?", (record_id,))
            conn.commit()

        logger.info("MODEL DELETE | id=%s", record_id)
        return {"success": True, "id": record_id}

    # ---------------------------------------------------------- routing

    def get_routing(self) -> dict[str, Optional[str]]:
        routing: dict[str, Optional[str]] = {label: None for label in VALID_LABELS}
        with closing(self._connect()) as conn:
            for row in conn.execute("SELECT task_label, default_model_id FROM model_router_settings"):
                if row["task_label"] in routing:
                    routing[row["task_label"]] = row["default_model_id"]
        return routing

    def set_default_model(self, task_label: str, model_id: str) -> dict:
        label = (task_label or "").strip().lower()
        if label not in VALID_LABELS:
            return {"success": False, "error": f"Label '{label}' tidak valid."}

        model = self.get_model(model_id)
        if not model:
            return {"success": False, "error": f"Model '{model_id}' tidak ditemukan."}
        if not model["enabled"]:
            return {"success": False, "error": "Model dinonaktifkan. Aktifkan dulu sebelum dijadikan default."}

        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO model_router_settings (task_label, default_model_id) VALUES (?, ?) "
                "ON CONFLICT(task_label) DO UPDATE SET default_model_id = excluded.default_model_id",
                (label, model_id),
            )
            conn.commit()

        logger.info("ROUTING SET | label=%s -> %s", label, model_id)
        return {"success": True, "task_label": label, "default_model_id": model_id}

    # ----------------------------------------------------------- policy

    def get_policy(self) -> dict:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT fallback_model_id, retry_provider FROM model_policy WHERE id = 1"
            ).fetchone()
        return dict(row) if row else {"fallback_model_id": None, "retry_provider": 0}

    def set_policy(self, **fields) -> dict:
        updates: dict = {}

        if "fallback_model_id" in fields:
            fallback_id = fields["fallback_model_id"] or None
            if fallback_id:
                model = self.get_model(fallback_id)
                if not model:
                    return {"success": False, "error": f"Model '{fallback_id}' tidak ditemukan."}
                if not model["enabled"]:
                    return {"success": False, "error": "Model fallback harus dalam keadaan enabled."}
            updates["fallback_model_id"] = fallback_id

        if fields.get("retry_provider") is not None:
            try:
                retries = int(fields["retry_provider"])
            except (TypeError, ValueError):
                return {"success": False, "error": "retry_provider harus berupa angka."}
            if not 0 <= retries <= 5:
                return {"success": False, "error": "retry_provider harus antara 0 sampai 5."}
            updates["retry_provider"] = retries

        if updates:
            set_sql = ", ".join(f"{key} = ?" for key in updates)
            with self._lock, closing(self._connect()) as conn:
                conn.execute(f"UPDATE model_policy SET {set_sql} WHERE id = 1", list(updates.values()))
                conn.commit()
            logger.info("POLICY UPDATE | %s", updates)

        return {"success": True, "policy": self.get_policy()}


_store_singleton: Optional[ModelStore] = None
_store_lock = threading.Lock()


def get_model_store() -> ModelStore:
    global _store_singleton
    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = ModelStore()
    return _store_singleton