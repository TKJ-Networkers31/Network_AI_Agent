from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    TIMEZONE = ZoneInfo("Asia/Jakarta")
except Exception:
    TIMEZONE = None

HARI = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}
BULAN = {1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
         7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"}


def now():
    return datetime.now(TIMEZONE) if TIMEZONE else datetime.now()


def format_datetime_id(dt=None):
    dt = dt or now()
    hari = HARI[dt.weekday()]
    bulan = BULAN[dt.month]
    return f"{hari}, {dt.day} {bulan} {dt.year} pukul {dt.strftime('%H:%M')} WIB"


def time_context_block():
    return (
        f"\nWaktu saat ini: {format_datetime_id()} (zona waktu Asia/Jakarta / WIB).\n"
        f"Gunakan ini sebagai acuan 'sekarang', 'hari ini', 'besok', dsb. "
        f"Bandingkan langsung dengan waktu di atas untuk menentukan apakah suatu "
        f"tanggal ada di masa lalu atau masa depan - jangan menebak.\n"
    )
