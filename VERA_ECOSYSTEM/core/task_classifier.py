"""
core/task_classifier.py — klasifikasi intent dengan LLM / heuristik deterministik untuk VERA.

Model classifier = model default label "general" atau model spesifik yang diatur
lewat VERA_CLASSIFIER_MODEL di .env. Mendukung 28 kategori tugas cerdas.

classify() TIDAK PERNAH raise: gagal apa pun -> fallback heuristik aman.
"""

import json
import logging
import os
import re
from typing import Optional

from agents.rei.provider_client import ProviderClient
from core.events import event_bus
from core.model_router import ModelRouter, get_model_router
from core.model_types import (
    CATEGORY_TO_LABEL_MAP,
    DEFAULT_LABEL,
    EVENT_TASK_CLASSIFIED,
    SelectedModel,
    TASK_CLASSIFICATION_CATEGORIES,
    TaskClassification,
    VALID_LABELS,
)

logger = logging.getLogger("vera.task_classifier")

CLASSIFIER_SYSTEM_PROMPT = """You are VERA Enterprise Task Classifier.

Your only job is to classify the user's request.
Return ONLY a valid JSON object.
Do not include any explanation or extra text.

Output schema:
{
  "task_category": "string",
  "primary_label": "string",
  "confidence": 0.00,
  "requires_tools": false,
  "requires_vision": false,
  "requires_voice": false,
  "required_capabilities": ["conversation"]
}"""

LABEL_GUIDE = """Valid task categories:
- general_chat, documentation
- general_reasoning, mathematics, research, long_context_analysis
- network_engineering, network_troubleshooting, network_configuration, network_topology, routing_protocols, subnetting, cybersecurity
- coding, programming, terminal_operations, devops, linux_administration
- vision_analysis, image_understanding
- document_processing, automation
- translation
- audio_processing, voice_generation
- embedding, retrieval, reranking
- content_safety

User request:
"""

MAX_PROMPT_CHARS = 1500
CLASSIFIER_TIMEOUT = 6.0  # Bounded classifier timeout (6.0s) to eliminate turn latency bottlenecks
CLASSIFIER_MAX_TOKENS = 150

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def parse_classification(raw: Optional[str]) -> TaskClassification:
    """Parse output LLM. Tidak pernah raise."""
    if not raw:
        return TaskClassification.fallback()

    text = _THINK_RE.sub("", raw)
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return TaskClassification.fallback()

    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return TaskClassification.fallback()

    if not isinstance(data, dict):
        return TaskClassification.fallback()

    category = str(data.get("task_category") or "").strip().lower()
    label = str(data.get("primary_label") or "").strip().lower()

    if category in CATEGORY_TO_LABEL_MAP:
        if label not in VALID_LABELS:
            label = CATEGORY_TO_LABEL_MAP[category]
    elif label in VALID_LABELS:
        category = label
    else:
        return TaskClassification.fallback()

    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    req_caps = data.get("required_capabilities") or []
    if not isinstance(req_caps, list):
        req_caps = []

    return TaskClassification(
        primary_label=label,
        confidence=round(confidence, 2),
        requires_tools=_to_bool(data.get("requires_tools", False)),
        requires_vision=_to_bool(data.get("requires_vision", False)),
        requires_voice=_to_bool(data.get("requires_voice", False)),
        task_category=category,
        required_capabilities=req_caps,
        rationale=f"LLM classifier selected category '{category}' with confidence {confidence:.2f}",
    )


class TaskClassifier:

    def __init__(self, router: Optional[ModelRouter] = None, client=None):
        self._router = router
        self._client = client or ProviderClient

    @property
    def router(self) -> ModelRouter:
        return self._router or get_model_router()

    def classify(self, prompt: str) -> TaskClassification:
        prompt = (prompt or "").strip()

        try:
            result = self._classify_with_llm(prompt) if prompt else TaskClassification.fallback()
        except Exception:
            logger.exception("Classifier gagal tak terduga - pakai fallback heuristik.")
            result = self._heuristic_classify(prompt) if prompt else TaskClassification.fallback()

        logger.info("CLASSIFIER | label=%s category=%s confidence=%.2f",
                    result.primary_label, result.task_category, result.confidence)

        try:
            event_bus.publish(
                EVENT_TASK_CLASSIFIED,
                agent="CLASSIFIER",
                data={
                    "label": result.primary_label,
                    "confidence": result.confidence,
                },
            )
        except Exception:
            logger.exception("Gagal publish task.classified (diabaikan).")

        return result

    def _pick_model(self) -> Optional[SelectedModel]:
        """Pilih model classifier dari env VERA_CLASSIFIER_MODEL / AIRA_CLASSIFIER_MODEL atau default."""
        override = (os.getenv("VERA_CLASSIFIER_MODEL") or os.getenv("AIRA_CLASSIFIER_MODEL", "")).strip()

        if override:
            row = self.router.store.get_model(override)
            if not row:
                for m in self.router.store.list_models(enabled_only=True):
                    if m.get("model_id") == override:
                        row = m
                        break
            if row and row["enabled"]:
                return SelectedModel.from_row(row)

            logger.info("CLASSIFIER | override '%s' tidak ditemukan di store - pakai model general default.", override)

        return self.router.select_for_label(DEFAULT_LABEL, publish=False)

    def _classify_with_llm(self, prompt: str) -> TaskClassification:
        model = self._pick_model()
        if model is None:
            logger.info("Classifier: tidak ada model general - pakai fallback heuristik.")
            return self._heuristic_classify(prompt)

        try:
            from core.provider_health import get_provider_health_manager
            health_mgr = get_provider_health_manager()
            if not health_mgr.is_provider_available(model.provider):
                logger.info("Classifier: Provider '%s' circuit is OPEN - fast-failing to heuristic classification.", model.provider)
                return self._heuristic_classify(prompt)
        except Exception:
            pass

        response = self._client.chat(
            provider=model.provider,
            model=model.model_id,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": LABEL_GUIDE + prompt[:MAX_PROMPT_CHARS]},
            ],
            tools=None,
            temperature=0,
            max_tokens=CLASSIFIER_MAX_TOKENS,
            think=False,
            timeout=CLASSIFIER_TIMEOUT,
            record_telemetry=False,
        )

        if "error" in response:
            logger.info("Classifier: provider issue (%s) - pakai fallback heuristik.", response.get("error_type", "error"))
            return self._heuristic_classify(prompt)

        parsed = parse_classification((response.get("message") or {}).get("content"))
        if parsed.primary_label == DEFAULT_LABEL and parsed.confidence <= 0.5:
            heuristic = self._heuristic_classify(prompt)
            if heuristic.primary_label != DEFAULT_LABEL:
                return heuristic
        return parsed

    @staticmethod
    def _heuristic_classify(prompt: str) -> TaskClassification:
        """Deterministic heuristic fallback classifier covering all 28 categories."""
        p = prompt.lower()

        # 0. Content Safety
        if any(re.search(pat, p) for pat in [r"\b(exploit|payload|inject|malware|ransomware|bypass auth)\b"]):
            return TaskClassification(
                primary_label="networking",
                task_category="content_safety",
                confidence=0.90,
                requires_tools=False,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "content_safety"],
                rationale="Heuristic detected cybersecurity and content safety concern",
            )

        # 0.1 Vision & Image Understanding (Priority: Modality requires vision model)
        if any(re.search(pat, p) for pat in [r"\b(gambar|foto|image|screenshot|diagram|kamera|ocr|lihat gambar|schematic)\b"]):
            return TaskClassification(
                primary_label="vision",
                task_category="vision_analysis",
                confidence=0.88,
                requires_tools=False,
                requires_vision=True,
                requires_voice=False,
                required_capabilities=["conversation", "vision"],
                required_modalities=["text", "image"],
                rationale="Heuristic matched visual and image analysis keywords",
            )

        # 1. Network Subnetting
        if any(re.search(pat, p) for pat in [r"\b(subnet|cidr|vlsm|netmask|ip address|ipv4|ipv6|slash 24|slash 30|/24|/28|/30)\b"]):
            return TaskClassification(
                primary_label="networking",
                task_category="subnetting",
                confidence=0.88,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "network_engineering"],
                rationale="Heuristic matched IP subnetting and addressing keywords",
            )

        # 2. Routing Protocols
        if any(re.search(pat, p) for pat in [r"\b(bgp|ospf|vrrp|rip|mpls|l3vpn|l2vpn|ebgp|ibgp|as-path|area 0|route reflector)\b"]):
            return TaskClassification(
                primary_label="networking",
                task_category="routing_protocols",
                confidence=0.92,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "network_engineering", "tool_calling"],
                rationale="Heuristic matched dynamic routing protocol keywords (BGP/OSPF/MPLS)",
            )

        # 3. Network Configuration & RouterOS / MikroTik
        if any(re.search(pat, p) for pat in [
            r"\b(mikrotik|routeros|cisco|vyos|winbox|the dude|bridge|ether\d+|wlan\d+|wireguard|ipsec|vpn)\b",
            r"\b(firewall|nat|mangle|ip route|default route|dhcp-server|vlan id|pvid|trunk)\b",
        ]):
            return TaskClassification(
                primary_label="networking",
                task_category="network_configuration",
                confidence=0.89,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "network_engineering", "tool_calling"],
                rationale="Heuristic matched RouterOS / device configuration patterns",
            )

        # 4. Network Troubleshooting & Diagnostics
        if any(re.search(pat, p) for pat in [
            r"\b(ping|traceroute|snmp|bandwidth|latency|packet loss|rtt|jitter|unreachable|down|flap)\b",
            r"\b(rca|root cause|diagnosa|gangguan|mati|lambat|putus)\b",
        ]):
            return TaskClassification(
                primary_label="networking",
                task_category="network_troubleshooting",
                confidence=0.88,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "network_engineering", "tool_calling"],
                rationale="Heuristic matched network incident / troubleshooting keywords",
            )

        # 5. Network Topology
        if any(re.search(pat, p) for pat in [r"\b(topologi|topology|lldp|cdp|mac table|arp table|neighbor|discovery)\b"]):
            return TaskClassification(
                primary_label="networking",
                task_category="network_topology",
                confidence=0.87,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "network_engineering", "tool_calling"],
                rationale="Heuristic matched network topology and discovery terms",
            )

        # 6. Terminal Operations / Linux Administration / DevOps
        if any(re.search(pat, p) for pat in [
            r"\b(terminal|bash|ssh|systemctl|journalctl|grep|awk|sed|curl|iptables|nftables)\b",
            r"\b(linux|ubuntu|debian|alpine|centos|rocky|kernel|process|top|htop)\b",
        ]):
            return TaskClassification(
                primary_label="coding",
                task_category="terminal_operations",
                confidence=0.85,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "coding", "terminal_operations"],
                rationale="Heuristic matched Linux terminal and system administration keywords",
            )

        # 7. DevOps & Containers
        if any(re.search(pat, p) for pat in [r"\b(docker|docker-compose|kubernetes|k8s|ansible|terraform|ci/cd|pipeline)\b"]):
            return TaskClassification(
                primary_label="coding",
                task_category="devops",
                confidence=0.86,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "coding", "devops"],
                rationale="Heuristic matched DevOps infrastructure automation keywords",
            )

        # 8. Coding / Software Engineering / Programming
        if any(re.search(pat, p) for pat in [
            r"\b(def\s+\w+|class\s+\w+|import\s+\w+|function\s+\w+|const\s+\w+|let\s+\w+)\b",
            r"\b(python|javascript|typescript|golang|rust|c\+\+|sql|react|vite|fastapi)\b",
            r"\b(code|coding|refactor|debugging|unit test|pytest|syntax|compile|bug)\b",
        ]):
            return TaskClassification(
                primary_label="coding",
                task_category="coding",
                confidence=0.85,
                requires_tools=False,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "coding"],
                rationale="Heuristic matched programming and code development keywords",
            )

        # 9. Vision & Image Understanding
        if any(re.search(pat, p) for pat in [r"\b(gambar|foto|image|screenshot|diagram|kamera|ocr|lihat gambar|schematic)\b"]):
            return TaskClassification(
                primary_label="vision",
                task_category="vision_analysis",
                confidence=0.85,
                requires_tools=False,
                requires_vision=True,
                requires_voice=False,
                required_capabilities=["conversation", "vision"],
                required_modalities=["text", "image"],
                rationale="Heuristic matched visual and image analysis keywords",
            )

        # 10. Voice & Audio
        if any(re.search(pat, p) for pat in [r"\b(suara|bicara|dengar|audio|voice|speech|stt|tts|rekam|pelafalan)\b"]):
            return TaskClassification(
                primary_label="voice",
                task_category="voice_generation",
                confidence=0.85,
                requires_tools=False,
                requires_vision=False,
                requires_voice=True,
                required_capabilities=["conversation", "voice"],
                required_modalities=["text", "audio"],
                rationale="Heuristic matched voice synthesis and audio processing keywords",
            )

        # 11. Automation & Scheduling
        if any(re.search(pat, p) for pat in [r"\b(jadwal|jadwalkan|cron|otomatisasi|schedule|recurring|periodic|backup berkala)\b"]):
            return TaskClassification(
                primary_label="automation",
                task_category="automation",
                confidence=0.85,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "tool_calling", "automation"],
                rationale="Heuristic matched scheduled job and automation keywords",
            )

        # 12. Mathematics & Formal Logic
        if any(re.search(pat, p) for pat in [r"\b(hitung|kalkulasi|persamaan|aljabar|matematika|probabilitas|integral|rumus)\b"]):
            return TaskClassification(
                primary_label="reasoning",
                task_category="mathematics",
                confidence=0.82,
                requires_tools=False,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "reasoning"],
                rationale="Heuristic matched mathematics and calculation keywords",
            )

        # 13. Complex Reasoning & Proof
        if any(re.search(pat, p) for pat in [r"\b(analisis mendalam|buktikan|logika|mengapa|kenapa|step by step|evaluasi perbandingan)\b"]):
            return TaskClassification(
                primary_label="reasoning",
                task_category="general_reasoning",
                confidence=0.80,
                requires_tools=False,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "reasoning"],
                rationale="Heuristic matched multi-step analytical reasoning keywords",
            )

        # 14. Information Retrieval & Fact Search
        if any(re.search(pat, p) for pat in [r"\b(cari|search|berita terbaru|informasi terkini|fakta tentang|siapa itu|referensi)\b"]):
            return TaskClassification(
                primary_label="retrieval",
                task_category="retrieval",
                confidence=0.80,
                requires_tools=True,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "retrieval", "tool_calling"],
                rationale="Heuristic matched web search / information retrieval keywords",
            )

        # 15. Translation
        if any(re.search(pat, p) for pat in [r"\b(terjemahkan|translate|artikan|bahasa inggris|bahasa indonesia)\b"]):
            return TaskClassification(
                primary_label="general",
                task_category="translation",
                confidence=0.82,
                requires_tools=False,
                requires_vision=False,
                requires_voice=False,
                required_capabilities=["conversation", "translation"],
                rationale="Heuristic matched language translation keywords",
            )

        # Default general fallback
        return TaskClassification(
            primary_label=DEFAULT_LABEL,
            confidence=0.50,
            requires_tools=False,
            requires_vision=False,
            requires_voice=False,
            task_category="general_chat",
            required_capabilities=["conversation"],
            rationale="Default general chat classification",
        )


_classifier_singleton: Optional[TaskClassifier] = None


def get_task_classifier() -> TaskClassifier:
    global _classifier_singleton
    if _classifier_singleton is None:
        _classifier_singleton = TaskClassifier()
    return _classifier_singleton


def classify(prompt: str) -> TaskClassification:
    return get_task_classifier().classify(prompt)


_classifier_singleton: Optional[TaskClassifier] = None


def get_task_classifier() -> TaskClassifier:
    global _classifier_singleton
    if _classifier_singleton is None:
        _classifier_singleton = TaskClassifier()
    return _classifier_singleton


def classify(prompt: str) -> TaskClassification:
    return get_task_classifier().classify(prompt)
