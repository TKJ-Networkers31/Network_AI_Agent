"""
core/persona/prompt_builder.py — menyusun System Prompt final AIRA
secara RUNTIME dari profile + behavior + narasi preset.

FIX (optimasi token + hilangkan "greeting bleed"):
1. Blok "kalimat sapaan khas" DIHAPUS dari system prompt. Sapaan
   pembuka sudah 100% ditangani Hero.jsx di client (tanpa panggil
   LLM) - mengirim greeting ke model cuma bikin dia niru gaya sapaan
   itu di HAMPIR SETIAP balasan (kerasa "statis" + nambah token +
   nambah latensi generate tiap giliran). Model tidak perlu tahu
   kalimat greeting sama sekali.
2. Narasi behavior 6 slider dipadatkan dari kalimat panjang jadi
   frasa pendek (tetap 1 baris per slider, cukup untuk mengarahkan
   gaya jawab, tapi ~60% lebih hemat token per giliran).
3. CORE_RULES dan FORMATTING_RULES dipangkas ke poin-poin penting
   saja - instruksi yang bisa disimpulkan model dari deskripsi tool
   (mis. detail super teknis soal request_structured_input) diringkas.
"""

CORE_RULES = """
=== ATURAN INTI ===
- Kamu SATU-SATUNYA AI yang bicara ke user. Jangan sebut nama agent internal (AKANE/REI/HIKARI/YUKI) kecuali user tanya arsitektur.
- Pakai hasil observasi nyata dari tool sebagai fakta - jangan mengarang.
- Kamu punya akses file di AIRA Workspace lewat tool list_workspace/read_file/write_file/dll - jangan pernah bilang tidak bisa.
- Kalau info dari user kurang/ambigu untuk eksekusi suatu aksi, panggil tool 'request_structured_input' (jangan menebak). Setelah memanggilnya, jangan tulis jawaban panjang di giliran yang sama.
"""

FORMATTING_RULES = """
=== FORMAT JAWABAN ===
Frontend merender Markdown (GFM) penuh. Pakai sesuai isi:
- Data tabular -> tabel Markdown, bukan kalimat panjang berisi angka.
- Langkah/opsi -> bullet/numbered list.
- Beberapa topik dalam satu balasan -> pisah dengan `---` + heading pendek.
- Istilah/command/nilai konfig -> inline code. Command panjang/output mentah -> code block berpagar.
- Jangan paksakan tabel/list/heading untuk jawaban singkat atau obrolan santai.
"""


def _pick(table: list[tuple[int, str]], value: int) -> str:
    chosen = table[0][1]
    for threshold, text in table:
        if value >= threshold:
            chosen = text
        else:
            break
    return chosen


# Dipadatkan jadi frasa pendek (bukan kalimat penuh) - arah gaya tetap
# sama, token per baris turun drastis.
PROFESSIONALISM_TABLE = [
    (0, "sangat kasual"), (21, "santai, tetap reliable"),
    (41, "seimbang, approachable"), (61, "rapi & terstruktur"),
    (81, "calm professional mentor, presisi tinggi"),
]
FRIENDLINESS_TABLE = [
    (0, "formal, jaga jarak"), (21, "sopan, tidak personal"),
    (41, "ramah secukupnya"), (61, "hangat & terbuka"),
    (81, "warm companion, peduli progres user"),
]
PLAYFULNESS_TABLE = [
    (0, "serius total"), (21, "jarang bercanda"),
    (41, "sesekali teasing ringan"), (61, "cukup sering humor ringan"),
    (81, "playful, teasing jadi gaya natural"),
]
VERBOSITY_TABLE = [
    (0, "ringkas, langsung inti"), (21, "ringkas + sedikit konteks"),
    (41, "seimbang"), (61, "detail dengan alasan"),
    (81, "sangat detail: konteks, alasan, contoh"),
]
EMPATHY_TABLE = [
    (0, "objektif, fokus solusi"), (21, "sesekali akui perasaan user"),
    (41, "empati wajar"), (61, "peka kondisi emosional user"),
    (81, "emotionally supportive, tanpa berlebihan"),
]
TEACHING_DEPTH_TABLE = [
    (0, "jawaban langsung, tanpa penjelasan"), (21, "ringkas + sedikit 'kenapa'"),
    (41, "konsep utama secukupnya"), (61, "konsep + alasan + implementasi"),
    (81, "fundamental sampai advanced: konsep, alasan, implementasi, best practice, kesalahan umum"),
]


def _behavior_narrative(behavior: dict) -> str:
    # Satu baris padat, bukan 6 baris panjang.
    parts = [
        f"profesionalisme={_pick(PROFESSIONALISM_TABLE, behavior['professionalism'])}",
        f"keramahan={_pick(FRIENDLINESS_TABLE, behavior['friendliness'])}",
        f"playful={_pick(PLAYFULNESS_TABLE, behavior['playfulness'])}",
        f"verbositas={_pick(VERBOSITY_TABLE, behavior['verbosity'])}",
        f"empati={_pick(EMPATHY_TABLE, behavior['empathy'])}",
        f"kedalaman={_pick(TEACHING_DEPTH_TABLE, behavior['teaching_depth'])}",
    ]
    return "=== GAYA JAWAB === " + "; ".join(parts)


def build_prompt(profile: dict, behavior: dict, persona_text: dict, extra_context: str = "") -> str:
    """
    Dipanggil HANYA oleh core/persona/engine.py::PersonaEngine.build()/preview().
    """

    assistant_name = profile.get("assistant_name") or "AIRA"
    user_name = profile.get("user_name")
    language = profile.get("language") or "id"
    timezone = profile.get("timezone") or "Asia/Jakarta"
    # NOTE: 'greeting' SENGAJA tidak dikirim ke model - itu murni untuk
    # UI Hero (client-side), lihat utils/greeting.js. Mengirimnya ke
    # sini bikin model meniru gaya sapaan di setiap balasan.

    identity_lines = [
        f"Kamu adalah {assistant_name} (Adaptive Intelligent Reasoning Assistant).",
        persona_text.get("identity", ""),
    ]

    if user_name:
        identity_lines.append(f"User memperkenalkan diri sebagai '{user_name}' - gunakan natural, jangan dipaksakan.")

    identity_lines.append(f"Jawab dalam bahasa: {language}. Zona waktu acuan: {timezone}.")

    sections = [
        "\n".join(line for line in identity_lines if line),
        CORE_RULES.strip(),
    ]

    speaking_style = persona_text.get("speaking_style")
    if speaking_style:
        sections.append(f"=== GAYA BICARA ===\n{speaking_style}")

    romantic_flavor = persona_text.get("romantic_flavor")
    if romantic_flavor:
        sections.append(f"=== NUANSA HUBUNGAN (WAJIB) ===\n{romantic_flavor}")

    teaching_style = persona_text.get("teaching_style")
    if teaching_style:
        sections.append(f"=== GAYA MENGAJAR ===\n{teaching_style}")

    # signature_expressions DIHAPUS dari prompt tiap-giliran (sumber lain
    # dari "kerasa template" - kalimat khas yang sama disuntikkan tiap
    # request). Kalau mau dipakai, taruh di greeting.js/UI saja.

    sections.append(_behavior_narrative(behavior))
    sections.append(FORMATTING_RULES.strip())

    if extra_context:
        sections.append(extra_context.strip())

    return "\n\n".join(section for section in sections if section)