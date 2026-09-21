/**
 * utils/greetingResolver.js — GreetingResolver (Sprint 2.6 / Worker 4).
 *
 *   GreetingContext  ->  resolveGreeting()  ->  Hero Model
 *
 * Hero Model:
 *   {
 *     greeting:    "Selamat pagi, Lingga",      // headline deterministik
 *     subtitle:    "2 koneksi perangkat aktif." // baris sadar-state (boleh null)
 *     time_period: "morning" | ... | null,
 *     status:      HERO_STATUS,                 // aturan state mana yang menang
 *     fallback:    false                        // true = turun ke greeting lama
 *   }
 *
 * Deterministik & murah: tanpa LLM, tanpa fetch, tanpa Math.random, tanpa
 * Date.now() tersembunyi. Input sama -> output sama. Tidak menyentuh
 * Streaming / Thinking / WebSocket / Planner / Brain / Event Bus.
 *
 * Teks bisa diganti lewat `copy` (lihat DEFAULT_GREETING_COPY) tanpa mengubah
 * logika. Bahasa/periode/status yang tidak ada di `copy` jatuh ke default.
 */

import {
  ACTIVITY_STATE,
  WORKSPACE_STATE,
  buildGreetingContext,
  cleanText,
  normalizeLanguage,
  toDate,
} from "./greetingContext.js";
// Greeting lama - dipakai HANYA sebagai jaring pengaman (fallback), tidak diubah.
import { buildGreeting as buildLegacyGreeting } from "./greeting.js";

export const HERO_STATUS = Object.freeze({
  NETWORK_WORK: "network_work",
  CONNECTED: "connected",
  WORKSPACE_ACTIVE: "workspace_active",
  NO_WORKSPACE: "no_workspace",
  IDLE: "idle",
});

const HOUR_MS = 3_600_000;
const STATIC_FALLBACK_GREETING = "Halo! Ada yang bisa dibantu?";

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

/**
 * Placeholder: {name} (headline), {count} (status "connected").
 * Entri headline: { named, anonymous } - `named` dipakai kalau ada nama
 * panggilan, `anonymous` kalau tidak (tanpa koma menggantung).
 */
export const DEFAULT_GREETING_COPY = deepFreeze({
  id: {
    greeting: {
      morning: { named: "Selamat pagi, {name}", anonymous: "Selamat pagi" },
      afternoon: { named: "Selamat siang, {name}", anonymous: "Selamat siang" },
      evening: { named: "Selamat malam, {name}", anonymous: "Selamat malam" },
      night: { named: "Masih semangat ngoding, {name}?", anonymous: "Masih semangat ngoding?" },
      generic: { named: "Halo, {name}", anonymous: "Halo" },
    },
    status: {
      network_work: "Ada pekerjaan jaringan yang sedang berjalan.",
      connected: "{count} koneksi perangkat aktif.",
      workspace_active: "Workspace sedang aktif.",
      no_workspace: "Belum ada workspace aktif.",
    },
    idle: ["Ada yang mau dikerjain?", "Mau mulai dari mana dulu?", "Siap lanjut proyek hari ini?"],
  },
  en: {
    greeting: {
      morning: { named: "Good morning, {name}", anonymous: "Good morning" },
      afternoon: { named: "Good afternoon, {name}", anonymous: "Good afternoon" },
      evening: { named: "Good evening, {name}", anonymous: "Good evening" },
      night: { named: "Still up coding, {name}?", anonymous: "Still up coding?" },
      generic: { named: "Hello, {name}", anonymous: "Hello" },
    },
    status: {
      network_work: "Network work is in progress.",
      connected: "{count} device connection(s) active.",
      workspace_active: "Your workspace is active.",
      no_workspace: "No active workspace yet.",
    },
    idle: ["What are we working on?", "Where should we start?"],
  },
});

// ============================================================
// LOOKUP TEKS
// ============================================================

function firstValid(candidates, isValid) {
  for (const candidate of candidates) {
    if (isValid(candidate)) return candidate;
  }
  return null;
}

const isEntry = (entry) => Boolean(entry) && typeof entry === "object" && Boolean(cleanText(entry.anonymous));
const isLine = (line) => Boolean(cleanText(line));
const isLines = (lines) => Array.isArray(lines) && lines.length > 0 && lines.every(isLine);

// custom[lang] -> default[lang] -> default.id
function lookup(copy, language, ...path) {
  const read = (root) => path.reduce((node, key) => (node == null ? undefined : node[key]), root);

  return [read(copy?.[language]), read(DEFAULT_GREETING_COPY[language]), read(DEFAULT_GREETING_COPY.id)];
}

// {name}/{count} diganti dalam SATU putaran (fungsi pengganti) - nilai user yang
// memuat "{name}" atau "$&" tidak ikut diperluas.
function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in values ? String(values[key]) : match));
}

// ============================================================
// STATUS
// ============================================================

function deriveStatus(context) {
  if (context.activity_state === ACTIVITY_STATE.NETWORK_WORK) return HERO_STATUS.NETWORK_WORK;
  if (Number.isInteger(context.connection_count) && context.connection_count > 0) return HERO_STATUS.CONNECTED;
  if (context.workspace_state === WORKSPACE_STATE.ACTIVE) return HERO_STATUS.WORKSPACE_ACTIVE;
  if (context.workspace_state === WORKSPACE_STATE.NONE) return HERO_STATUS.NO_WORKSPACE;
  return HERO_STATUS.IDLE;
}

// ============================================================
// RESOLVER
// ============================================================

/**
 * @param {import("./greetingContext.js").GreetingContext} context
 * @param {{ copy?: object, seed?: number }} [options]
 *   copy : override teks (bentuk sama dengan DEFAULT_GREETING_COPY, parsial boleh)
 *   seed : bilangan bulat untuk memilih varian baris idle secara deterministik
 * @returns Hero Model
 *
 * Toleran terhadap context parsial/rusak: field hilang -> greeting generik,
 * tanpa status khusus. Tidak melakukan I/O.
 */
export function resolveGreeting(context, { copy = null, seed = 0 } = {}) {
  const ctx = context && typeof context === "object" ? context : {};

  const language = normalizeLanguage(ctx.language) ?? "id";
  const period = cleanText(ctx.time_period); // periode kustom tanpa copy jatuh ke "generic"

  const address = cleanText(ctx.nickname) ?? cleanText(ctx.display_name);

  // ---- headline
  const entry =
    firstValid(lookup(copy, language, "greeting", period ?? "generic"), isEntry) ??
    firstValid(lookup(copy, language, "greeting", "generic"), isEntry);

  const greeting =
    address && cleanText(entry.named)
      ? fill(entry.named, { name: address })
      : fill(entry.anonymous, {});

  // ---- baris sadar-state
  const status = deriveStatus(ctx);
  let subtitle = null;

  if (status === HERO_STATUS.IDLE) {
    const lines = firstValid(lookup(copy, language, "idle"), isLines);
    const index = Number.isInteger(seed) ? Math.abs(seed) % (lines?.length || 1) : 0;
    subtitle = lines ? lines[index] : null;
  } else {
    const line = firstValid(lookup(copy, language, "status", status), isLine);
    subtitle = line ? fill(line, { count: ctx.connection_count }) : null;
  }

  return { greeting, subtitle, time_period: period, status, fallback: false };
}

// ============================================================
// FASAD: aman dipanggil dari UI (tidak pernah raise)
// ============================================================

function legacyHeroModel(input) {
  let greeting = STATIC_FALLBACK_GREETING;

  try {
    const text = buildLegacyGreeting(input?.persona);
    if (cleanText(text)) greeting = text;
  } catch {
    // greeting lama pun gagal -> teks statis
  }

  return { greeting, subtitle: null, time_period: null, status: HERO_STATUS.IDLE, fallback: true };
}

/**
 * Satu-satunya fungsi yang perlu dipanggil UI (W5):
 *
 *   resolveGreetingModel({ settings, persona, workspace, connections, activity, now, copy })
 *
 * settings tidak tersedia -> tetap jalan dari persona/default.
 * Ada error tak terduga -> greeting.js lama (fallback: true); kalau itu juga
 * gagal -> teks statis. Aplikasi tidak pernah gagal hanya karena greeting.
 */
export function resolveGreetingModel(input = {}) {
  try {
    const source = input && typeof input === "object" ? input : {};
    const context = buildGreetingContext(source);
    const seed = Math.floor(toDate(source.now).getTime() / HOUR_MS); // berganti tiap jam, stabil dalam jam yang sama

    return resolveGreeting(context, { copy: source.copy, seed });
  } catch {
    return legacyHeroModel(input);
  }
}
