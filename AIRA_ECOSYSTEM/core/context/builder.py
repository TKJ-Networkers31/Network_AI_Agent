"""
core/context/builder.py — Context Builder (Sprint 2 / Worker 1).

Pipeline:

    User Input
      -> ContextBuilder.build()
      -> AIRAContext (Final Context)
      -> Brain -> Orchestrator -> Planner (REI) -> provider

Builder ini HANYA MENGGABUNGKAN konteks yang sudah disediakan modul lain:

    identity, persona -> PersonaEngine.get_state()      (core/persona)
    runtime_state     -> time_context_block()           (core/time_utils)
                         + snapshot Runtime State Engine (core/runtime_state,
                           Sprint 2 / Worker 3) sebagai DATA saja
    memory            -> SATU section, DUA sumber (keduanya dipertahankan):
                         build_context_snippet() (core/memory, long-term) lalu
                         SemanticMemory.retrieve() (core/semantic_memory, Top-K
                         per sesi). Gagal/kosong di salah satu sumber tidak
                         menghilangkan sumber lainnya.
    location          -> build_location_context(sid)    (core/location)
    tool_context      -> ringkasan tool dari pemanggil  (Brain)
    task              -> hasil klasifikasi dari pemanggil (Brain)
    system_prompt     -> PersonaEngine.build(extra_context)

Yang TIDAK dilakukan (batas keras):
  - tidak melakukan reasoning / memutuskan hasil task
  - tidak memilih model (itu core/model_router.py)
  - tidak mengeksekusi tool (itu Orchestrator)
  - tidak menyimpan/menulis memory, tidak menyusun teks persona sendiri
    (PersonaEngine tetap SATU-SATUNYA penyusun system prompt)
  - tidak mengakses database apa pun secara langsung (Semantic Memory hanya
    dipanggil lewat API publiknya: retrieve())
  - tidak punya event system sendiri (hanya logging)

Semua sumber konteks disuntik lewat konstruktor (Dependency Injection), jadi
builder bisa dites tanpa database/jaringan. Default-nya di-import LAZY di dalam
fungsi, sehingga mengimpor modul ini murah dan bebas efek samping.

Penanganan konteks hilang: sumber yang None, kosong, atau raise -> section
dilewati (None), tidak pernah menjatuhkan giliran. Yang raise dicatat di
AIRAContext.warnings (hanya nama + tipe error, tanpa pesan error).

Runtime State (Worker 3): snapshot state runtime (IDLE/LISTENING/THINKING/SPEAKING)
dimasukkan ke ContextSection runtime_state.data["engine"]. HANYA data - teksnya
tidak pernah masuk system prompt (state itu untuk konsumen non-prompt seperti
UI/suara), jadi Runtime State tidak ikut "bernalar". Seperti tool_summary,
provider ini TIDAK punya default di konstruktor (None = tanpa data state);
Brain dan get_context_builder() yang menyuntikkannya.

Semantic Memory: hanya kalau ada session_id (isolasi sesi) dan input tidak kosong.
Top-K default 3, tiap item maksimal 240 karakter, tanpa id/embedding/skor di
teks. Hasilnya digabung DI BELAKANG memory long-term (legacy) dalam SATU
ContextSection - keduanya dipertahankan.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from core.context.models import (
    AIRAContext,
    ContextSection,
    SECTION_IDENTITY,
    SECTION_LOCATION,
    SECTION_MEMORY,
    SECTION_PERSONA,
    SECTION_RUNTIME_STATE,
    SECTION_TOOL_CONTEXT,
    _json_dict,
)

logger = logging.getLogger("aira.context")

_IDENTITY_KEYS = ("assistant_name", "user_name", "language", "timezone")

DEFAULT_SEMANTIC_TOP_K = 3
MAX_MEMORY_ITEM_CHARS = 240
SEMANTIC_MEMORY_HEADER = "=== RELEVANT MEMORIES ==="


# ============================================================
# DEFAULT PROVIDERS (lazy import - hanya dipakai kalau tidak di-inject)
# ============================================================

def _default_persona_state() -> Optional[dict]:
    from core.persona import get_engine
    return get_engine().get_state()


def _default_prompt_composer(extra_context: str) -> str:
    from core.persona import get_engine
    return get_engine().build(extra_context)


def _default_memory_text() -> Optional[str]:
    from core.memory import build_context_snippet
    return build_context_snippet()


def _default_runtime_text() -> Optional[str]:
    from core.time_utils import time_context_block
    return time_context_block()


def _default_location_text(session_id: Optional[str]) -> Optional[str]:
    from core.location import build_location_context
    return build_location_context(session_id)


def _default_runtime_state() -> Optional[dict]:
    """Snapshot Runtime State Engine global. Dipakai get_context_builder()."""
    from core.runtime_state import runtime_state_snapshot
    return runtime_state_snapshot()


def _default_semantic_memory():
    """Singleton SemanticMemory (dibuat lazy). Tidak membuat DB baru per request."""
    from core.semantic_memory import get_semantic_memory
    return get_semantic_memory()


# ============================================================
# HELPERS
# ============================================================

def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def summarize_tool_schemas(schemas, categories: Optional[dict] = None) -> dict:
    """
    Ringkasan tool (nama + kategori, TANPA isi skema) untuk tool_context.
    Skema lengkap sudah dikirim ke provider lewat argumen `tools=`; ringkasan
    ini tidak disisipkan ke prompt. {} kalau tidak ada tool bernama.
    """
    categories = categories or {}
    names: list[str] = []
    by_category: dict[str, list[str]] = {}

    for entry in schemas or []:
        function = entry.get("function", {}) if isinstance(entry, dict) else {}
        name = function.get("name")

        if not name:
            continue

        names.append(name)
        by_category.setdefault(categories.get(name, "tool"), []).append(name)

    if not names:
        return {}

    return {"count": len(names), "names": names, "categories": by_category}


def format_semantic_memories(
    results,
    limit: int = DEFAULT_SEMANTIC_TOP_K,
    max_item_chars: int = MAX_MEMORY_ITEM_CHARS,
) -> tuple[str, int]:
    """
    RetrievalResult -> (teks ringkas, jumlah baris). Deterministik, hanya
    membaca record.text + record.category. Tidak pernah menampilkan embedding,
    id, skor, atau metadata. Teks dijadikan satu baris (newline dibuang supaya
    isi memori tidak bisa menyamar sebagai header section) dan dipotong.
    Item tidak valid dilewati + di-log. ("", 0) kalau tidak ada yang layak.
    """
    lines: list[str] = []
    skipped = 0

    for result in results or []:
        if len(lines) >= limit:
            break

        record = getattr(result, "record", None)
        text = " ".join(str(getattr(record, "text", None) or "").split())

        if not text:
            skipped += 1
            continue

        if len(text) > max_item_chars:
            text = text[: max_item_chars - 1].rstrip() + "…"

        category = getattr(record, "category", None)
        label = str(getattr(category, "value", category) or "").strip()

        lines.append(f"- [{label}] {text}" if label else f"- {text}")

    if skipped:
        logger.warning("CONTEXT | %d memori semantik tidak valid dilewati.", skipped)

    if not lines:
        return "", 0

    return SEMANTIC_MEMORY_HEADER + "\n" + "\n".join(lines), len(lines)


# ============================================================
# BUILDER
# ============================================================

class ContextBuilder:
    """
    Semua argumen opsional. None = pakai default AIRA. Untuk MEMATIKAN satu
    sumber, beri provider yang mengembalikan None (mis. `lambda: None`).
    `tool_summary` dan `runtime_state` tidak punya default
    (None = tanpa tool_context / tanpa data state runtime).

    semantic_memory: objek dengan method retrieve(query, session_id, top_k)
    (mis. SemanticMemory). None = singleton lazy get_semantic_memory().
    semantic_top_k: batas jumlah memori semantik per giliran (default 3;
    nilai tidak valid -> default; 0 -> retrieval semantik dimatikan).
    """

    def __init__(
        self,
        *,
        persona_state: Optional[Callable[[], Optional[dict]]] = None,
        prompt_composer: Optional[Callable[[str], str]] = None,
        memory_text: Optional[Callable[[], Optional[str]]] = None,
        runtime_text: Optional[Callable[[], Optional[str]]] = None,
        location_text: Optional[Callable[[Optional[str]], Optional[str]]] = None,
        tool_summary: Optional[Callable[[], Optional[dict]]] = None,
        runtime_state: Optional[Callable[[], Optional[dict]]] = None,
        semantic_memory: Optional[Any] = None,
        semantic_top_k: int = DEFAULT_SEMANTIC_TOP_K,
    ):
        self._persona_state = persona_state or _default_persona_state
        self._prompt_composer = prompt_composer or _default_prompt_composer
        self._memory_text = memory_text or _default_memory_text
        self._runtime_text = runtime_text or _default_runtime_text
        self._location_text = location_text or _default_location_text
        self._tool_summary = tool_summary
        self._runtime_state = runtime_state
        self._semantic_memory = semantic_memory
        self._semantic_top_k = (
            semantic_top_k
            if isinstance(semantic_top_k, int) and not isinstance(semantic_top_k, bool)
            and semantic_top_k >= 0
            else DEFAULT_SEMANTIC_TOP_K
        )

    # ------------------------------------------------------------ public

    def build(
        self,
        user_input: str,
        *,
        session_id: Optional[str] = None,
        task: Any = None,
    ) -> AIRAContext:
        """
        task: dict, atau objek dengan .to_dict() (mis. TaskClassification),
        atau None. Tidak pernah raise.
        """
        warnings: list[str] = []

        context = AIRAContext(
            user_input=str(user_input or ""),
            session_id=session_id or None,
            task=self._normalize_task(task, warnings),
        )

        state = self._call("persona", self._persona_state, warnings)
        profile, behavior = self._split_persona_state(state)

        context.identity = self._identity_section(profile)
        context.persona = self._persona_section(profile, behavior)

        context.runtime_state = self._text_section(
            SECTION_RUNTIME_STATE, "runtime", self._runtime_text, warnings,
        )

        # Runtime State Engine (Worker 3): data saja, tidak pernah jadi teks prompt.
        context.runtime_state = self._attach_runtime_state(
            context.runtime_state,
            self._call("runtime_state", self._runtime_state, warnings),
        )

        # SATU section memory dari dua sumber (long-term + semantic).
        context.memory = self._memory_section(
            context.user_input, context.session_id, warnings,
        )

        # Lokasi hanya relevan kalau ada sesi (klien PWA). Mode terminal tidak
        # punya session_id dan tidak pernah menerima blok lokasi.
        if context.session_id:
            context.location = self._text_section(
                SECTION_LOCATION, "location", self._location_text, warnings,
                context.session_id,
            )

        context.tool_context = self._tool_section(warnings)

        context.system_prompt = self._compose(context.extra_context(), warnings)
        context.warnings = warnings

        logger.info("CONTEXT | dibangun %s", context.summary())

        return context

    # ---------------------------------------------------------- sections

    @staticmethod
    def _split_persona_state(state: Any) -> tuple[dict, dict]:
        if not isinstance(state, dict):
            return {}, {}

        profile = state.get("profile")
        behavior = state.get("behavior")

        return (
            profile if isinstance(profile, dict) else {},
            behavior if isinstance(behavior, dict) else {},
        )

    @staticmethod
    def _identity_section(profile: dict) -> Optional[ContextSection]:
        data = {
            key: _text(profile.get(key))
            for key in _IDENTITY_KEYS
            if _text(profile.get(key))
        }

        if not data:
            return None

        return ContextSection(SECTION_IDENTITY, data=data, source="persona")

    @staticmethod
    def _persona_section(profile: dict, behavior: dict) -> Optional[ContextSection]:
        data: dict[str, Any] = {}

        preset = _text(profile.get("active_preset"))
        if preset:
            data["active_preset"] = preset

        if behavior:
            data["behavior"] = _json_dict(behavior)

        if not data:
            return None

        return ContextSection(SECTION_PERSONA, data=data, source="persona")

    def _text_section(
        self, name: str, source: str, provider, warnings: list[str], *args,
    ) -> Optional[ContextSection]:
        text = _text(self._call(name, provider, warnings, *args))

        if not text:
            return None

        return ContextSection(name, text=text, source=source)

    # ------------------------------------------------------- memory (2 sumber)

    def _memory_section(
        self, user_input: str, session_id: Optional[str], warnings: list[str],
    ) -> Optional[ContextSection]:
        """
        SATU section memory dari DUA sumber independen (long_term_memory.db dan
        semantic_memory.db). Keduanya dipanggil terisolasi (_call), jadi gagal di
        satu sumber tidak pernah menghilangkan/merusak sumber lainnya.

            legacy + semantic  -> legacy, baris kosong, semantic
            semantic saja      -> semantic
            legacy saja        -> persis perilaku lama
            tidak ada          -> None
        """
        legacy = self._text_section(SECTION_MEMORY, "memory", self._memory_text, warnings)
        semantic = self._semantic_section(user_input, session_id, warnings)

        if semantic is None:
            return legacy

        if legacy is None:
            return semantic

        return ContextSection(
            SECTION_MEMORY,
            text=f"{legacy.text}\n\n{semantic.text}",
            data={**semantic.data, "sources": ["legacy", "semantic"]},
            source="memory+semantic_memory",
        )

    def _semantic_section(
        self, user_input: str, session_id: Optional[str], warnings: list[str],
    ) -> Optional[ContextSection]:
        query = (user_input or "").strip()

        # Tanpa sesi tidak ada batas isolasi -> jangan retrieval (mode terminal).
        if not session_id or not query or self._semantic_top_k <= 0:
            return None

        outcome = self._call(
            "semantic_memory", self._retrieve_semantic, warnings, query, session_id,
        )

        if not outcome or not outcome[0]:
            return None

        text, count = outcome

        return ContextSection(
            SECTION_MEMORY, text=text,
            data={"sources": ["semantic"], "semantic_count": count},
            source="semantic_memory",
        )

    def _retrieve_semantic(self, query: str, session_id: str):
        memory = (
            self._semantic_memory
            if self._semantic_memory is not None
            else _default_semantic_memory()
        )

        if memory is None:
            return None

        results = memory.retrieve(
            query=query, session_id=session_id, top_k=self._semantic_top_k,
        )

        return format_semantic_memories(results, limit=self._semantic_top_k)

    # ------------------------------------------------------ runtime / tool

    @staticmethod
    def _attach_runtime_state(
        section: Optional[ContextSection], snapshot: Any,
    ) -> Optional[ContextSection]:
        """
        Tempelkan snapshot Runtime State ke section runtime_state sebagai DATA.
        - Snapshot kosong/bukan dict -> section apa adanya (bisa None).
        - Section teks (waktu) sudah ada -> teksnya tidak disentuh, data digabung.
        - Section belum ada -> dibuat data-only (text kosong => tidak pernah
          masuk system prompt, lihat AIRAContext.extra_context()).
        """
        if not isinstance(snapshot, dict) or not snapshot:
            return section

        data = {"engine": _json_dict(snapshot)}

        if section is None:
            return ContextSection(SECTION_RUNTIME_STATE, data=data, source="runtime_state")

        section.data = {**section.data, **data}
        return section

    def _tool_section(self, warnings: list[str]) -> Optional[ContextSection]:
        if self._tool_summary is None:
            return None

        summary = self._call("tool_context", self._tool_summary, warnings)

        if not isinstance(summary, dict) or not summary:
            return None

        # Data saja - tidak pernah diberi text, jadi tidak pernah masuk prompt.
        return ContextSection(SECTION_TOOL_CONTEXT, data=_json_dict(summary), source="tools")

    # ------------------------------------------------------------ compose

    def _compose(self, extra_context: str, warnings: list[str]) -> str:
        """
        Delegasi ke PersonaEngine (satu-satunya penyusun system prompt).
        Kalau gagal: degradasi ke konteks runtime saja, giliran tetap jalan.
        """
        try:
            prompt = self._prompt_composer(extra_context)
        except Exception as exc:
            logger.warning(
                "CONTEXT | prompt composer gagal (%s) - memakai konteks runtime saja.",
                type(exc).__name__, exc_info=True,
            )
            warnings.append(f"persona: prompt composer failed ({type(exc).__name__})")
            return extra_context

        if prompt is None:
            return extra_context

        return prompt if isinstance(prompt, str) else str(prompt)

    # ------------------------------------------------------------ safety

    @staticmethod
    def _call(name: str, provider, warnings: list[str], *args):
        """Panggil provider terisolasi. Raise -> None + warning (tipe saja)."""
        if provider is None:
            return None

        try:
            return provider(*args)
        except Exception as exc:
            logger.warning(
                "CONTEXT | sumber '%s' gagal (%s) - section dilewati.",
                name, type(exc).__name__, exc_info=True,
            )
            warnings.append(f"{name}: unavailable ({type(exc).__name__})")
            return None

    @staticmethod
    def _normalize_task(task: Any, warnings: list[str]) -> Optional[dict]:
        if task is None:
            return None

        if isinstance(task, dict):
            return _json_dict(task) if task else None

        to_dict = getattr(task, "to_dict", None)

        if callable(to_dict):
            try:
                result = to_dict()
            except Exception as exc:
                warnings.append(f"task: unavailable ({type(exc).__name__})")
                return None
            return _json_dict(result) if isinstance(result, dict) and result else None

        warnings.append(f"task: unsupported type ({type(task).__name__})")
        return None


# ============================================================
# SINGLETON (dipakai Planner sebagai fallback)
# ============================================================

_builder_singleton: Optional[ContextBuilder] = None
_builder_lock = threading.Lock()


def get_context_builder() -> ContextBuilder:
    global _builder_singleton

    if _builder_singleton is None:
        with _builder_lock:
            if _builder_singleton is None:
                _builder_singleton = ContextBuilder(runtime_state=_default_runtime_state)

    return _builder_singleton