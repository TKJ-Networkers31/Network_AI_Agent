/**
 * Greeting DINAMIS yang dibangun 100% di client, BUKAN AI response -
 * tidak ada panggilan ke backend/LLM sama sekali di sini. Cuma tampilan
 * UI lokal berdasarkan waktu saat ini + identitas Persona yang sedang
 * aktif (assistant_name, user_name, timezone).
 *
 * Dipakai HANYA saat sebuah sesi belum punya history sama sekali
 * (sesi baru / app pertama kali dibuka) - lihat ChatPage.jsx.
 */

function resolveHour(timezone) {
  try {
    const formatted = new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      hour12: false,
      timeZone: timezone || "Asia/Jakarta",
    }).format(new Date());

    return Number(formatted);
  } catch {
    return new Date().getHours();
  }
}

export function buildGreeting(profile) {
  const p = profile || {};
  const assistantName = p.assistant_name || "AIRA";
  const userName = (p.user_name || "").trim();
  const namePart = userName ? `, ${userName}` : "";
  const hour = resolveHour(p.timezone);

  if (hour >= 4 && hour < 11) {
    return `Selamat pagi${namePart} 🌸 Siap melanjutkan proyek ${assistantName} hari ini?`;
  }

  if (hour >= 11 && hour < 15) {
    return `Halo${namePart}. Mau lanjut debugging atau bikin fitur baru?`;
  }

  if (hour >= 15 && hour < 19) {
    return `Sore${namePart}~ Masih ada yang mau dikejar sebelum hari ini berakhir?`;
  }

  return `Malam ya${namePart}… huft, waktunya ngoding lagi? 🌸`;
}