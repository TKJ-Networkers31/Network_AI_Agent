"""
Utilitas untuk memberi tahu LLM waktu saat ini.

Kenapa ini perlu: SYSTEM_PROMPT sebelumnya adalah string statis
yang dibuat sekali saat modul di-import, jadi model tidak pernah
tahu tanggal/jam saat ini secara real. Ini kelihatan jelas di
logs/agent.log lama - model sempat bingung apakah "2026" itu
tanggal masa depan atau bukan, dan salah menyimpulkan currentnya.

Modul ini generate context waktu FRESH setiap kali get_messages()
dipanggil (lihat agent/memory.py), bukan sekali di awal sesi,
supaya akurat walau sesi dibiarkan terbuka lama.
"""

from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    TIMEZONE = ZoneInfo("Asia/Jakarta")
except Exception:
    # Fallback kalau tzdata tidak tersedia di sistem. Daripada
    # crash total, pakai waktu lokal sistem tanpa info timezone
    # eksplisit.
    TIMEZONE = None

HARI = {
    0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
    4: "Jumat", 5: "Sabtu", 6: "Minggu",
}

BULAN = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}


def now():
    if TIMEZONE:
        return datetime.now(TIMEZONE)
    return datetime.now()


def format_datetime_id(dt=None):

    dt = dt or now()

    hari = HARI[dt.weekday()]
    bulan = BULAN[dt.month]

    return (
        f"{hari}, {dt.day} {bulan} {dt.year} "
        f"pukul {dt.strftime('%H:%M')} WIB"
    )


def time_context_block():
    """
    Blok teks yang disisipkan ke system prompt setiap request,
    supaya LLM selalu tahu waktu saat ini secara real-time.
    """

    return (
        f"\nWaktu saat ini: {format_datetime_id()} "
        f"(zona waktu Asia/Jakarta / WIB).\n"
        f"Gunakan ini sebagai acuan 'sekarang', 'hari ini', 'besok', "
        f"dsb. Bandingkan langsung dengan waktu di atas untuk "
        f"menentukan apakah suatu tanggal ada di masa lalu atau "
        f"masa depan - jangan menebak.\n"
    )