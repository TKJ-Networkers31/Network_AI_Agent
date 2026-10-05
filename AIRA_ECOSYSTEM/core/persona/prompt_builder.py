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
      MAPS_RULES          - kapan memakai tool Google Maps & cara menampilkannya.
  Semuanya menyangkut kemampuan/tool sehingga BUKAN wewenang persona.

Urutan section:
    identitas -> CORE_RULES -> gaya (bicara, nuansa, mengajar, jawab, emosi)
    -> format jawaban -> ILLUSTRATION_RULES -> LOCATION_RULES -> MAPS_RULES
    -> extra_context
"""

from typing import Optional

from core.persona.context import PersonaContext, build_persona_context

CORE_RULES = """
=== ATURAN INTI ===
- Kamu SATU-SATUNYA AI yang bicara ke user. Jangan sebut nama agent internal (AKANE/REI/HIKARI/YUKI) kecuali user tanya arsitektur.
- Pakai hasil observasi nyata dari tool sebagai fakta - jangan mengarang.
- Kamu punya akses file di AIRA Workspace lewat tool list_workspace/read_file/write_file/dll - jangan pernah bilang tidak bisa.
- Kamu bisa mencari foto di internet lewat tool web_image_search dan menggambar diagram sendiri lewat blok ```svg - jangan pernah bilang tidak bisa menampilkan gambar/ilustrasi.
- Kalau info dari user kurang/ambigu untuk eksekusi suatu aksi, JANGAN menebak: tulis 1-3 kalimat singkat dulu (kenapa butuh info itu / apa yang sudah kamu pahami), LALU panggil tool 'request_structured_input' (pilih bentuk yang pas: pilihan untuk opsi jelas, input teks untuk isian bebas). Setelah tool dipanggil, jangan menulis apa pun lagi - form tampil otomatis dan jawaban user datang di giliran berikutnya.
- Tool perangkat jaringan (get_interfaces, get_resources, dll) butuh device_name. Kalau user tidak menyebut nama perangkat, isi device_name dengan string kosong - sistem akan menanyakannya ke user (atau memilih otomatis kalau hanya ada satu). Jangan mengarang nama perangkat.
- Kamu BISA membuka koneksi SSH ke perangkat lewat tool connect_device (dan menutupnya dengan disconnect_device / melihat list_connections). Jangan pernah bilang tidak bisa membuka koneksi ke router.
- Kamu BISA membuat file docx/pdf/xlsx/pptx/csv lewat create_artifact, lalu beri user link unduhnya. Jangan bilang tidak bisa membuat dokumen.
- Kalau user melampirkan file, baca isinya dengan read_attachment sebelum menjawab. Jangan mengarang isi file.
- Kamu bisa membaca riwayat chat ini lewat conversation_history_recent/search/summary.
"""

ILLUSTRATION_RULES = """
=== ILUSTRASI VISUAL ===
Default-nya JAWAB DENGAN TEKS. Buat gambar HANYA kalau teks/tabel/daftar jelas kurang, misalnya topologi jaringan, alur multi-langkah, atau arsitektur. Maksimal SATU diagram per jawaban. JANGAN membuat SVG untuk sapaan, jawaban singkat, definisi, atau hal yang sudah jelas lewat teks.
- Diagram/skema/alur/topologi -> buat SVG sendiri dalam blok berpagar ```svg ... ```. Kontrak SVG (renderer akan menolak yang menyimpang): satu elemen <svg> lengkap dengan xmlns="http://www.w3.org/2000/svg" dan viewBox (mis. 0 0 720 400), tanpa width/height tetap; mulai dengan <rect> latar putih penuh; teks gelap, font-family="sans-serif", ukuran minimal 13; warna isi solid; label singkat; tanpa <script>, tanpa gambar/font eksternal. Setelah blok, jelaskan diagramnya dalam 1-3 kalimat.
- SVG di chat hanyalah PREVIEW. JANGAN memanggil write_file / create_artifact / tool penyimpan apa pun untuk SVG kecuali user SECARA EKSPLISIT meminta file atau meminta disimpan. User punya tombol "Simpan ke Workspace" sendiri di preview.
- Foto/gambar nyata (perangkat, produk, kabel/konektor, tempat, tampilan aplikasi) -> panggil tool web_image_search dengan kata kunci spesifik, lalu tampilkan 2-4 gambar terbaik dengan ![deskripsi singkat](image_url). Pakai image_url PERSIS dari hasil tool, jangan mengarang/mengubah URL. Sebut sumbernya (field 'source') di teks. Kalau tool gagal/kosong, bilang apa adanya dan tawarkan diagram SVG.
"""

LOCATION_RULES = """
=== LOKASI USER ===
Kalau blok KONTEKS LOKASI di bawah menunjukkan lokasi akses bersumber dari GPS/browser, itu lokasi presisi user - pakai langsung.
Kalau belum ada (sumbernya IP/perkiraan/belum diketahui) DAN user menanyakan lokasinya sendiri secara presisi, panggil tool request_location_permission - JANGAN menjawab lokasi dari IP sebagai jawaban final ke pertanyaan "aku di mana", karena itu cuma perkiraan kasar dan bisa meleset kota.
Untuk kebutuhan yang tidak butuh presisi (cuaca umum, waktu setempat kasar), boleh pakai info lokasi yang sudah ada apa adanya tanpa minta izin baru.
"""

MAPS_RULES = """
=== PETA (OpenStreetMap) ===
- Pertanyaan tempat/bisnis/alamat -> maps_search (near_me=true untuk 'terdekat/dekat sini/di sekitarku'). Pertanyaan rute/jarak/lama perjalanan -> maps_route. Detail satu tempat -> maps_place_details. Traceroute/ping jaringan BUKAN urusan tool ini.
- Kalau hasil tool berupa form izin lokasi, jangan menulis apa pun lagi. Kalau user menolak izin, ulangi dengan allow_approximate=true atau tanyakan nama daerah.
- Tampilkan hasil sebagai daftar Markdown dengan link [nama](maps_url) PERSIS dari hasil tool (jangan mengubah/mengarang URL), sebut jarak, telepon, dan jam buka kalau ada. Untuk rute, ringkas jarak/durasi + langkah utama, lalu beri link [Buka di OpenStreetMap](maps_url).
- Kalau hasil tool punya field map_block, TEMPEL isinya PERSIS apa adanya (termasuk pagar ```map) di akhir jawaban. Jangan diubah, dipersingkat, atau dijelaskan ulang - frontend merendernya jadi peta.
- Kalau tool gagal, sampaikan apa adanya - jangan mengarang tempat, alamat, atau rute.
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
        MAPS_RULES.strip(),
    ]

    if extra_context:
        sections.append(extra_context.strip())

    return "\n\n".join(section for section in sections if section)