"""
core/persona/emotion.py — ekspresi emosi (gaya penyampaian) AIRA.

Murni fungsi dari slider behavior + konfigurasi tone.yaml: deterministik,
tanpa I/O, tanpa membaca isi pesan user, tanpa klasifikasi apa pun. Emosi
di sini hanya mengarahkan NADA penyampaian; guard di tone.yaml
(emotion.guard) selalu ikut ditulis supaya ekspresi tidak mengubah fakta
atau kesimpulan teknis.
"""

from core.persona.scales import pick


def derive_emotion(behavior: dict) -> dict:
    """Turunkan 3 dimensi ekspresi (0-100) dari slider behavior."""
    friendliness = behavior["friendliness"]
    empathy = behavior["empathy"]
    playfulness = behavior["playfulness"]

    return {
        "warmth": (friendliness + empathy + 1) // 2,
        "humor": playfulness,
        "expressiveness": (friendliness + empathy + playfulness) // 3,
    }


def describe_emotion(behavior: dict, emotion_config: dict) -> str:
    """Satu blok teks ringkas untuk system prompt; "" kalau dimatikan di tone.yaml."""
    if not emotion_config.get("enabled"):
        return ""

    values = derive_emotion(behavior)
    labels = emotion_config["labels"]
    bands = emotion_config["bands"]

    parts = [f"{labels[name]}={pick(bands[name], values[name])}" for name in ("warmth", "humor", "expressiveness")]

    text = f"=== {emotion_config['title']} === " + "; ".join(parts)
    guard = emotion_config.get("guard")

    return f"{text}. {guard}" if guard else text
