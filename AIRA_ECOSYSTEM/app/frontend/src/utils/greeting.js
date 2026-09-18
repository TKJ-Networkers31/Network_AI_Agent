/**
 * Greeting DINAMIS, 100% client-side (tidak panggil backend/LLM).
 * FIX: sebelumnya cuma 1 kalimat tetap per rentang jam (kerasa
 * "statis" tiap buka chat baru). Sekarang tiap rentang jam punya
 * beberapa varian, dipilih deterministik berdasarkan tanggal+jam
 * (bukan Math.random murni) supaya tidak "flicker" berubah tiap
 * re-render React dalam sesi yang sama, tapi tetap berganti dari
 * hari ke hari / jam ke jam.
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

// Seed deterministik: tanggal (YYYYMMDD) + jam, supaya varian tetap
// sama selama satu jam berjalan tapi beda tiap buka di jam/hari lain.
function seedIndex(length, timezone) {
  const now = new Date();
  const dateKey = Number(
    new Intl.DateTimeFormat("en-CA", { timeZone: timezone || "Asia/Jakarta" }).format(now).replace(/-/g, "")
  );
  const hour = resolveHour(timezone);
  const seed = dateKey + hour * 31;
  return seed % length;
}

const TEMPLATES = {
  pagi: (name, assistant) => [
    `Selamat pagi${name} 🌸 Siap lanjut proyek hari ini?`,
    `Pagi${name}! Mau mulai dari mana dulu?`,
    `Halo${name}, pagi yang pas buat ngoding santai. Ada yang mau dikerjain?`,
  ],
  siang: (name) => [
    `Halo${name}. Mau lanjut debugging atau bikin fitur baru?`,
    `Siang${name} — ada yang lagi ngadat, atau mau eksplor sesuatu yang baru?`,
    `Hai${name}, gas lanjutin yang kemarin atau mulai topik baru?`,
  ],
  sore: (name) => [
    `Sore${name}~ Masih ada yang mau dikejar sebelum hari ini berakhir?`,
    `Halo${name}, sore-sore gini enaknya beresin yang tanggung dulu ya?`,
    `Sore${name}, ada progress yang mau direview atau mulai baru?`,
  ],
  malam: (name) => [
    `Malam${name}… huft, waktunya ngoding lagi? 🌸`,
    `Halo${name}, masih terjaga? Ada yang mau dirampungin malam ini?`,
    `Malam${name} — sesi ngoding larut lagi nih, gas atau istirahat dulu?`,
  ],
};

export function buildGreeting(profile) {
  const p = profile || {};
  const assistantName = p.assistant_name || "AIRA";
  const userName = (p.user_name || "").trim();
  const namePart = userName ? `, ${userName}` : "";
  const timezone = p.timezone || "Asia/Jakarta";
  const hour = resolveHour(timezone);

  let bucket = "malam";
  if (hour >= 4 && hour < 11) bucket = "pagi";
  else if (hour >= 11 && hour < 15) bucket = "siang";
  else if (hour >= 15 && hour < 19) bucket = "sore";

  const variants = TEMPLATES[bucket](namePart, assistantName);
  const idx = seedIndex(variants.length, timezone);

  return variants[idx];
}