/**
 * utils/greetingContext.js — GreetingContext (Sprint 2.6 / Worker 4).
 *
 *   Settings (snapshot) + Persona profile + state runtime UI
 *        -> buildGreetingContext()
 *        -> GreetingContext (objek beku, 9 field)
 *        -> greetingResolver.js::resolveGreeting() -> Hero Model
 *
 * MURNI: fungsi sinkron, tanpa React, tanpa fetch, tanpa database, tanpa LLM,
 * tanpa Date.now() tersembunyi (waktu disuntik lewat `now`). Tidak menyentuh
 * Streaming / Thinking / WebSocket / Planner / Brain / Event Bus / Persona Engine.
 *
 * ------------------------------------------------------------------
 * KONTRAK DEPENDENSI SETTINGS (didefinisikan lokal sampai W1 selesai)
 * ------------------------------------------------------------------
 * Layer ini TIDAK menyimpan dan TIDAK mengambil settings. Ia hanya menerima
 * SNAPSHOT settings yang sudah dimuat pemanggil (W5 yang menyambungkan ke
 * Settings Service W1):
 *
 *   GreetingSettings (semua field opsional, semua string):
 *     display_name    nama tampil user
 *     nickname        panggilan user (didahulukan dari display_name saat menyapa)
 *     assistant_name  nama asisten (default "AIRA")
 *     timezone        IANA, mis. "Asia/Jakarta"
 *     language        "id" | "en" | tag lain (mis. "id-ID" -> "id")
 *
 *   Parameter `settings` boleh berupa:
 *     - objek GreetingSettings,
 *     - fungsi SINKRON () => GreetingSettings | null   (mis. getGreetingSettings()),
 *     - null / undefined (settings belum ada / tidak tersedia).
 *   Promise TIDAK didukung (dianggap tidak tersedia): resolve dulu di pemanggil.
 *   Fungsi yang melempar error = settings tidak tersedia, bukan crash.
 *
 * Prioritas nilai tiap field:  settings  >  persona profile  >  default.
 * Persona profile = bentuk /api/persona -> profile ({user_name, assistant_name,
 * language, timezone}) - sumber yang SUDAH dipakai greeting lama.
 */

// ============================================================
// KONSTANTA
// ============================================================

export const TIME_PERIOD = Object.freeze({
  MORNING: "morning",
  AFTERNOON: "afternoon",
  EVENING: "evening",
  NIGHT: "night",
});

export const WORKSPACE_STATE = Object.freeze({
  NONE: "none",     // tidak ada workspace aktif
  ACTIVE: "active", // ada workspace aktif
});

// Sengaja kecil & dimiliki layer ini: TIDAK memakai state Runtime/Streaming/
// Thinking (IDLE/LISTENING/THINKING/SPEAKING). Pemanggil (W5) yang memetakan
// sinyalnya ke nilai ini; nilai tak dikenal diperlakukan sebagai null.
export const ACTIVITY_STATE = Object.freeze({
  IDLE: "idle",
  NETWORK_WORK: "network_work", // ada pekerjaan jaringan (SSH/SNMP/tool jaringan) berjalan
});

export const DEFAULT_GREETING_SETTINGS = Object.freeze({
  assistant_name: "AIRA",
  timezone: "Asia/Jakarta",
  language: "id",
});

/**
 * Batas periode dalam jam (0-23) pada zona waktu TERKONFIGURASI. Urut naik
 * menurut `from`; periode aktif = entri terakhir dengan from <= jam. Data,
 * bukan logika: menambah periode (mis. "late_afternoon") = tambah satu baris
 * di sini + satu entri copy di greetingResolver.js.
 */
export const DEFAULT_PERIOD_BOUNDARIES = Object.freeze([
  Object.freeze({ from: 0, period: TIME_PERIOD.NIGHT }),
  Object.freeze({ from: 4, period: TIME_PERIOD.MORNING }),
  Object.freeze({ from: 11, period: TIME_PERIOD.AFTERNOON }),
  Object.freeze({ from: 18, period: TIME_PERIOD.EVENING }),
  Object.freeze({ from: 22, period: TIME_PERIOD.NIGHT }),
]);

// ============================================================
// HELPER MURNI (diekspor karena dipakai greetingResolver.js & test)
// ============================================================

/** string non-kosong (trim) atau null. */
export function cleanText(value) {
  if (typeof value !== "string") return null;
  const text = value.trim();
  return text ? text : null;
}

/** "id-ID" / "ID_id" / " en " -> "id" / "id" / "en"; selain itu null. */
export function normalizeLanguage(value) {
  const text = cleanText(value);
  if (!text) return null;
  return text.toLowerCase().split(/[-_]/)[0] || null;
}

/** Date valid apa adanya, angka epoch ms -> Date, selain itu "sekarang". */
export function toDate(now) {
  if (now instanceof Date && !Number.isNaN(now.getTime())) return now;
  if (typeof now === "number" && Number.isFinite(now)) return new Date(now);
  return new Date();
}

// Membuat Intl.DateTimeFormat itu mahal (~50µs): satu formatter per zona,
// dipakai ulang untuk validasi DAN pembacaan jam. Cache dibatasi supaya string
// zona sembarang dari settings tidak membuatnya tumbuh tanpa batas.
const FORMATTER_CACHE_LIMIT = 32;
const formatterCache = new Map();

function getHourFormatter(timezone) {
  const key = cleanText(timezone);
  if (!key) return null;

  if (formatterCache.has(key)) return formatterCache.get(key);

  let formatter = null;

  try {
    // hourCycle "h23" menjamin tengah malam = 0 (bukan "24").
    formatter = new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: key });
  } catch {
    formatter = null; // zona tidak valid / Intl tidak tersedia
  }

  if (formatterCache.size >= FORMATTER_CACHE_LIMIT) formatterCache.clear();
  formatterCache.set(key, formatter);

  return formatter;
}

export function isValidTimeZone(timezone) {
  return getHourFormatter(timezone) !== null;
}

/**
 * Jam (0-23) pada `timezone`. Zona tidak valid / Intl tidak tersedia -> jam
 * lokal mesin sebagai jaring pengaman terakhir (tidak pernah raise).
 */
export function resolveHourInTimezone(timezone, now) {
  const date = toDate(now);
  const formatter = getHourFormatter(timezone);

  if (formatter) {
    try {
      const hour = Number(formatter.formatToParts(date).find((part) => part.type === "hour")?.value);

      if (Number.isInteger(hour)) return hour % 24;
    } catch {
      // jatuh ke jam lokal di bawah
    }
  }

  return date.getHours();
}

/** Jam -> periode. Boundaries tidak valid -> DEFAULT_PERIOD_BOUNDARIES. */
export function resolveTimePeriod(hour, boundaries = DEFAULT_PERIOD_BOUNDARIES) {
  const valid =
    Array.isArray(boundaries) &&
    boundaries.length > 0 &&
    boundaries.every(
      (b) => b && Number.isInteger(b.from) && b.from >= 0 && b.from <= 23 && cleanText(b.period)
    );

  const table = [...(valid ? boundaries : DEFAULT_PERIOD_BOUNDARIES)].sort((a, b) => a.from - b.from);

  let chosen = null;

  for (const entry of table) {
    if (Number.isFinite(hour) && entry.from <= hour) chosen = entry.period;
  }

  // Sebelum entri pertama (atau jam tidak valid) = lanjutan periode terakhir hari sebelumnya.
  return chosen ?? table[table.length - 1].period;
}

export function normalizeWorkspaceState(value) {
  const candidate =
    value && typeof value === "object" && "active" in value ? value.active : value;

  if (candidate === true) return WORKSPACE_STATE.ACTIVE;
  if (candidate === false) return WORKSPACE_STATE.NONE;

  const text = cleanText(candidate)?.toLowerCase();

  if (text === WORKSPACE_STATE.ACTIVE) return WORKSPACE_STATE.ACTIVE;
  if (text === WORKSPACE_STATE.NONE) return WORKSPACE_STATE.NONE;

  return null; // tidak diketahui
}

/** Angka, atau array koneksi (panjangnya). Selain itu / negatif / NaN -> 0. */
export function normalizeConnectionCount(value) {
  if (Array.isArray(value)) return value.length;
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.floor(value));
  return 0;
}

export function normalizeActivityState(value) {
  const text = cleanText(value)?.toLowerCase();
  return Object.values(ACTIVITY_STATE).includes(text) ? text : null;
}

function readSettings(source) {
  try {
    const value = typeof source === "function" ? source() : source;

    if (!value || typeof value !== "object") return null;
    if (typeof value.then === "function") return null; // Promise: bukan snapshot sinkron

    return value;
  } catch {
    return null; // settings tidak tersedia - bukan alasan aplikasi gagal
  }
}

function pickTimezone(candidates) {
  for (const candidate of candidates) {
    if (isValidTimeZone(candidate)) return candidate.trim();
  }
  return null;
}

// ============================================================
// BUILDER
// ============================================================

/**
 * @typedef {Object} GreetingContext
 * @property {string|null} display_name
 * @property {string|null} nickname
 * @property {string}      assistant_name
 * @property {string}      timezone          IANA valid (selalu terisi)
 * @property {string}      language          subtag utama ("id", "en", ...)
 * @property {string}      time_period       salah satu TIME_PERIOD (atau periode kustom)
 * @property {string|null} workspace_state   WORKSPACE_STATE | null (tidak diketahui)
 * @property {number}      connection_count  bilangan bulat >= 0
 * @property {string|null} activity_state    ACTIVITY_STATE | null
 *
 * Tidak pernah raise untuk input tidak valid pada `settings`/`persona`/state.
 * (Hanya getter yang melempar pada objek input itu sendiri yang bisa lolos -
 * resolveGreetingModel() menangkapnya dan turun ke greeting lama.)
 */
export function buildGreetingContext({
  settings = null,
  persona = null,
  workspace = null,
  connections = 0,
  activity = null,
  now = undefined,
  boundaries = DEFAULT_PERIOD_BOUNDARIES,
} = {}) {
  const fromSettings = readSettings(settings) || {};
  const fromPersona = persona && typeof persona === "object" ? persona : {};

  const timezone =
    pickTimezone([fromSettings.timezone, fromPersona.timezone, DEFAULT_GREETING_SETTINGS.timezone]) ??
    DEFAULT_GREETING_SETTINGS.timezone;

  const hour = resolveHourInTimezone(timezone, now);

  return Object.freeze({
    display_name: cleanText(fromSettings.display_name) ?? cleanText(fromPersona.user_name),
    nickname: cleanText(fromSettings.nickname),
    assistant_name:
      cleanText(fromSettings.assistant_name) ??
      cleanText(fromPersona.assistant_name) ??
      DEFAULT_GREETING_SETTINGS.assistant_name,
    timezone,
    language:
      normalizeLanguage(fromSettings.language) ??
      normalizeLanguage(fromPersona.language) ??
      DEFAULT_GREETING_SETTINGS.language,
    time_period: resolveTimePeriod(hour, boundaries),
    workspace_state: normalizeWorkspaceState(workspace),
    connection_count: normalizeConnectionCount(connections),
    activity_state: normalizeActivityState(activity),
  });
}
