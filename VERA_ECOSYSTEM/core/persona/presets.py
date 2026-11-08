"""
core/persona/presets.py — preset persona built-in AIRA (akane, sensei, companion).

Sumber kebenaran preset built-in sekarang adalah file YAML di
core/persona/styles/<preset_id>.yaml (dimuat & divalidasi oleh loader.py,
dengan fallback ke core/persona/defaults.py kalau file hilang/rusak).
Baris di database/persona.db::persona_presets untuk preset built-in
disinkronkan ulang ke definisi ini setiap startup (engine.py::
_seed_builtin_presets) - jadi update preset bawaan cukup edit YAML, tanpa
migrasi database. Preset hasil clone milik user (is_builtin=0) tidak pernah
disentuh proses sinkron ini.

Bentuk BUILTIN_PRESETS TIDAK berubah: {id: {name, description, profile,
behavior, persona_text}}.
"""

from core.persona.loader import get_persona_config

BUILTIN_PRESETS: dict[str, dict] = get_persona_config().styles
