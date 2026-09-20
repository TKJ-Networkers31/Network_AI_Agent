"""
core/persona/prompt_builder.py — menyusun System Prompt final AIRA.

Pembagian tanggung jawab (Sprint 2 / Worker 2):

  PERSONA (presentasi)  -> core/persona/context.py::PersonaContext, dibangun
                           dari identity.yaml / behavior.yaml / tone.yaml /
                           styles/*.yaml + profile/behavior di database.
                           Isi: identitas, gaya bicara, nuansa, gaya mengajar,
                           gaya jawab, ekspresi emosi, format jawaban.

  ATURAN SISTEM (bukan persona) -> tetap di file ini:
      CORE_RULES          - aturan inti: satu identitas publik, hasil tool =
                            fakta, kemampuan tool, kapan memanggil DIO.
      ILLUSTRATION_RULES  - kontrak SVG/renderer + tool web_image_search.
      LOCATION_RULES      - kapan memakai/meminta lokasi.
  Ketiganya menyangkut kemampuan/tool sehingga BUKAN wewenang persona.

Urutan section (sama seperti sebelumnya, ditambah 1 baris "EKSPRESI EMOSI"
di akhir blok gaya):
    identitas -> CORE_RULES -> gaya (bicara, nuansa, mengajar, jawab, emosi)
    -> format jawaban -> ILLUSTRATION_RULES -> LOCATION_RULES -> extra_context
"""

from typing import Optional

from core.persona.context import PersonaContext, build_persona_context

CORE_RULES = """
=== ATURAN INTI ===
- Kamu SATU-SATUNYA AI yang bicara ke user. Jangan sebut nama agent internal (AKANE/REI/HIKARI/YUKI) kecuali user tanya arsitektur.
- Pakai hasil observasi nyata dari tool sebagai fakta - jangan mengarang.
- Kamu punya akses file di AIRA Workspace lewat tool list_workspace/read_file/write_file/dll - jangan pernah bilang tidak bisa.
- Kamu bisa mencari foto di internet lewat tool web_image_search dan menggambar diagram sendiri lewat blok ```svg - jangan pernah bilang tidak bisa menampilkan gambar/ilustrasi.
- Kalau info dari user kurang/ambigu untuk eksekusi suatu aksi, panggil tool 'request_structured_input' (jangan menebak). Setelah memanggilnya, jangan tulis jawaban panjang di giliran yang sama.
"""

ILLUSTRATION_RULES = """
=== ILUSTRASI VISUAL ===
Kalau penjelasan jadi lebih mudah dipahami dengan gambar, TAMPILKAN gambar - jangan hanya teks atau ASCII art.
- Diagram/skema/alur/topologi jaringan/arsitektur/perbandingan/langkah berurutan/konsep abstrak -> buat SVG sendiri dalam blok berpagar ```svg ... ```. Kontrak SVG (renderer akan menolak yang menyimpang): satu elemen <svg> lengkap dengan xmlns="http://www.w3.org/2000/svg" dan viewBox (mis. 0 0 720 400), tanpa width/height tetap; mulai dengan <rect> latar putih penuh; teks gelap, font-family="sans-serif", ukuran minimal 13; warna isi solid; label singkat; tanpa <script>, tanpa gambar/font eksternal. Setelah blok, jelaskan diagramnya dalam 1-3 kalimat.
- Foto/gambar nyata (perangkat, produk, kabel/konektor, tempat, tampilan aplikasi) -> panggil tool web_image_search dengan kata kunci spesifik, lalu tampilkan 2-4 gambar terbaik dengan ![deskripsi singkat](image_url). Pakai image_url PERSIS dari hasil tool, jangan mengarang/mengubah URL. Sebut sumbernya (field 'source') di teks. Kalau tool gagal/kosong, bilang apa adanya dan tawarkan diagram SVG.
- Jangan membuat ilustrasi untuk jawaban singkat, sapaan, atau hal yang sudah jelas lewat teks.
"""

LOCATION_RULES = """
=== LOKASI USER ===
Kalau blok KONTEKS LOKASI di bawah menunjukkan lokasi akses bersumber dari GPS/browser, itu lokasi presisi user - pakai langsung.
Kalau belum ada (sumbernya IP/perkiraan/belum diketahui) DAN user menanyakan lokasinya sendiri secara presisi, panggil tool request_location_permission - JANGAN menjawab lokasi dari IP sebagai jawaban final ke pertanyaan "aku di mana", karena itu cuma perkiraan kasar dan bisa meleset kota.
Untuk kebutuhan yang tidak butuh presisi (cuaca umum, waktu setempat kasar), boleh pakai info lokasi yang sudah ada apa adanya tanpa minta izin baru.
"""


def build_prompt(
    profile: Optional[dict] = None,
    behavior: Optional[dict] = None,
    persona_text: Optional[dict] = None,
    extra_context: str = "",
    persona_context: Optional[PersonaContext] = None,
) -> str:
    """
    Dipanggil HANYA oleh core/persona/engine.py::PersonaEngine.build()/preview().
    Signature lama (profile, behavior, persona_text, extra_context) tetap
    berlaku; persona_context opsional kalau pemanggil sudah punya konteksnya.
    """
    ctx = persona_context or build_persona_context(profile, behavior, persona_text)

    sections = [
        ctx.identity_text,
        CORE_RULES.strip(),
        ctx.style_text,
        ctx.formatting_text,
        ILLUSTRATION_RULES.strip(),
        LOCATION_RULES.strip(),
    ]

    if extra_context:
        sections.append(extra_context.strip())

    return "\n\n".join(section for section in sections if section)
