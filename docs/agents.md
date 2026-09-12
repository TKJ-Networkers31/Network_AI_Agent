# Agents

## AIRA (public identity)

Defined in `core/persona.py`. AIRA is the **only** identity the user ever
sees. It never refers to internal agents by name unless the user
explicitly asks about internal architecture. `core/persona.py::build_system_prompt()`
combines the AIRA identity block with runtime context (current time, long-term
memory snippet from `core/memory.py::build_context_snippet()`).

## AKANE — Adaptive Knowledge & Autonomous Network Engine

- **File:** `agents/akane/registry.py` (schemas), `agents/akane/network_tools.py` (implementation)
- **Domain:** SSH, SNMP, MikroTik RouterOS, ping/traceroute/nslookup, device inventory
- **Tools:** `ping`, `nslookup`, `traceroute`, `list_devices`, `get_interfaces`,
  `get_ip_addresses`, `get_routes`, `get_firewall`, `get_resources`,
  `get_identity`, `get_dns`, `get_dhcp_client`, `get_dhcp_server`, `get_nat`,
  `get_neighbors`, `get_arp`, `snmp_get_system_info`, `snmp_get_interface_traffic`
- **Notable fix:** the `traceroute` and `get_routes` schema descriptions are
  deliberately written to cross-reference and disambiguate each other,
  because the planner previously confused "traceroute to an external host"
  with "get the MikroTik device's internal routing table."

## REI — Reasoning & Executive Intelligence

- **Files:** `agents/rei/planner.py`, `agents/rei/provider_client.py`,
  `agents/rei/research_tools.py`, `agents/rei/registry.py`, `agents/rei/auto_extract.py`
- **Domain:** LLM planning/tool-call loop, the only LLM provider gateway,
  web search/fetch, long-term memory (`remember` / `recall` / `forget`)
- **Tools:** `web_search`, `web_fetch`, `remember`, `recall`, `forget`
- REI is also the orchestration brain: `Planner.run()` drives the
  think -> tool-call -> think loop (max 10 tool calls per turn, one retry
  on an empty/invalid provider response).

## HIKARI — Hybrid Intelligent Knowledge & Augmented Recognition

- **Files:** `agents/hikari/registry.py`, `agents/hikari/vision.py`,
  `agents/hikari/fusion.py`
- **Domain:** webcam-based vision via YOLO11n (`tools/vision/detector.py`)
- **Tools:** `detect_objects` (implemented), `recognize_object` (**not yet
  implemented** — always returns `{"success": false, "error": "Belum diimplementasikan."}`)
- **Fusion:** `fusion.py::fuse_voice_and_vision()` appends a short visual
  description to a voice transcript when "combined sensor mode" is active,
  so a text-only LLM effectively gets multimodal context without a
  vision-capable model.

## YUKI — Your Unified Knowledge Interface

- **Files:** `agents/yuki/stt.py` / `stt_engine.py`, `agents/yuki/tts.py` /
  `tts_engine.py`, `agents/yuki/voice_io.py`
- **Domain:** offline speech pipeline
  - STT: faster-whisper, model size `tiny`, `int8` compute, CPU-only
  - TTS: Kokoro ONNX (requires manually downloaded model files under
    `models/kokoro/`), fails gracefully (returns `False`) if the model is missing
  - `voice_io.py` implements simple energy-based VAD (no external VAD
    library) with barge-in prevention (mic paused while TTS speaks)

## Tool aggregation

`core/orchestrator.py` merges all four agents' registries into
`AGENT_TOOL_MAP`, `AGENT_TOOL_CATEGORY`, and `AGENT_TOOL_SCHEMAS`. No agent
is aware of another agent's internals — HIKARI's fusion callback, for
example, is injected into YUKI's `VoiceIO` from `core/orchestrator.py`
rather than imported directly, per the "no agent imports another agent"
rule (see [`constitution.md`](constitution.md)).

## Dangerous tools

Every agent registry exposes a `*_DANGEROUS_TOOLS` set for tools that
should require manual confirmation before execution (e.g. a future
config-writing tool). Currently all three sets are empty — every tool
in the system is read-only/observational.
