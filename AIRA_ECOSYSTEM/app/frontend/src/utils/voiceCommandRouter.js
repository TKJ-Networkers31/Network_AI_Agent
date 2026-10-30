// src/utils/voiceCommandRouter.js
//
// Router Perintah Suara AIRA (Voice Command Router)
// Mengkonversi transkrip suara pengguna (bahasa Indonesia + istilah teknis)
// menjadi intent terstruktur, memvalidasi allowlist aksi, dan menghasilkan
// respons verbal ringkas serta aksi navigasi/UI.
//
// Desain:
// - Fungsi murni tanpa efek samping luar -> 100% testable via unit tests.
// - Menghapus prefix wake word ("AIRA", "Hai AIRA", "Halo AIRA") bila ada.
// - Normalisasi teks (case, tanda baca, spasi ganda, toleransi variasi fonetik).
// - Membatasi eksekusi hanya ke halaman dan aksi yang diizinkan (safety allowlist).

export const ALLOWED_PAGES = [
  "chat",
  "workspace",
  "topology",
  "devices",
  "nms",
  "akane",
  "models",
  "persona",
  "memory",
  "logs",
  "settings",
];

// Pemetaan sinonim & kata kunci bahasa Indonesia ke ID halaman
const PAGE_KEYWORDS = [
  {
    page: "topology",
    label: "Network Topology",
    spoken: "Halaman topologi jaringan sudah dibuka.",
    patterns: [
      /\b(topolog[iy]|network topology|topologi jaringan|fabric|skema jaringan|peta jaringan)\b/i,
    ],
  },
  {
    page: "nms",
    label: "Network Management System",
    spoken: "Halaman pemantauan NMS sudah dibuka.",
    patterns: [
      /\b(nms|network management|monitoring|pemantauan|dashboard nms)\b/i,
    ],
  },
  {
    page: "devices",
    label: "Devices Inventory",
    spoken: "Halaman daftar perangkat sudah dibuka.",
    patterns: [
      /\b(device[s]?|perangkat|router|daftar router|inventori|inventory)\b/i,
    ],
  },
  {
    page: "akane",
    label: "AKANE Terminal",
    spoken: "Halaman koneksi dan terminal AKANE sudah dibuka.",
    patterns: [
      /\b(akane|terminal|koneksi|connection[s]?|ssh|konsol|console)\b/i,
    ],
  },
  {
    page: "chat",
    label: "Chat & Assistant",
    spoken: "Halaman obrolan sudah dibuka.",
    patterns: [
      /\b(chat|obrolan|dashboard|halaman utama|beranda|home|pesan)\b/i,
    ],
  },
  {
    page: "workspace",
    label: "Workspace Files",
    spoken: "Halaman workspace berkas sudah dibuka.",
    patterns: [
      /\b(workspace|file[s]?|berkas|dokumen|folder)\b/i,
    ],
  },
  {
    page: "models",
    label: "AI Models",
    spoken: "Halaman model kecerdasan buatan sudah dibuka.",
    patterns: [
      /\b(model[s]?|ai model|ganti model|pilih model|llm)\b/i,
    ],
  },
  {
    page: "persona",
    label: "AIRA Persona",
    spoken: "Halaman persona AIRA sudah dibuka.",
    patterns: [
      /\b(persona|profil aira|karakter|gaya bicara|sifat)\b/i,
    ],
  },
  {
    page: "memory",
    label: "Long-Term Memory",
    spoken: "Halaman memori jangka panjang sudah dibuka.",
    patterns: [
      /\b(memor[iy]|ingatan|data user|riwayat ingatan)\b/i,
    ],
  },
  {
    page: "logs",
    label: "System Logs",
    spoken: "Halaman log sistem sudah dibuka.",
    patterns: [
      /\b(log[s]?|catatan sistem|audit log|riwayat sistem)\b/i,
    ],
  },
  {
    page: "settings",
    label: "Settings",
    spoken: "Halaman pengaturan sudah dibuka.",
    patterns: [
      /\b(setting[s]?|pengaturan|konfigurasi|preferensi)\b/i,
    ],
  },
];

// Regex pola wake word AIRA beserta toleransi fonetik STT bahasa Indonesia
export const WAKE_WORD_PATTERN = "(?:aira|ayra|aera|eyra|haira|hayra|airah|ayrah|ira|era|ai\\s*ra|air\\s*a|aer\\s*a)";
const WAKE_WORD_PREFIX = new RegExp(`^\\s*(?:hai|halo|hallo|hei|hey|ok|oke)?\\s*${WAKE_WORD_PATTERN}[,.:;!?\\s]*`, "i");

/**
 * Membersihkan dan menormalkan teks masukan suara
 */
export function normalizeTranscript(text) {
  if (!text || typeof text !== "string") return "";
  return text
    .toLowerCase()
    .replace(/[.,\/#!$%\^&\*;:{}=\-_`~()?"']/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Menghapus prefix kata bangun "AIRA" bila ada di awal kalimat
 */
export function stripWakeWord(text) {
  if (!text || typeof text !== "string") return "";
  const cleaned = text.trim();
  const stripped = cleaned.replace(WAKE_WORD_PREFIX, "").trim();
  return stripped;
}

/**
 * Mengecek apakah kalimat mengandung wake word "AIRA"
 */
export function containsWakeWord(text) {
  if (!text || typeof text !== "string") return false;
  return new RegExp(`\\b${WAKE_WORD_PATTERN}\\b`, "i").test(text);
}

/**
 * Menguji apakah teks adalah murni panggilan wake word saja
 */
export function isPureWakeWord(text) {
  if (!text || typeof text !== "string") return false;
  const norm = normalizeTranscript(text);
  return new RegExp(`^(?:hai |halo |hallo |hei |hey |ok |oke )?${WAKE_WORD_PATTERN}$`, "i").test(norm);
}

/**
 * Memetakan transkrip suara pengguna ke intent perintah terstruktur
 *
 * @param {string} rawTranscript - Ucapan pengguna dari STT
 * @param {object} [context] - Konteks opsional (mis. halaman aktif saat ini)
 * @returns {object} Intent terstruktur
 */
export function routeVoiceCommand(rawTranscript, context = {}) {
  if (!rawTranscript || typeof rawTranscript !== "string" || !rawTranscript.trim()) {
    return {
      type: "empty",
      intent: "none",
      confidence: 0,
      userText: "",
      actionTitle: "Tidak terdengar ucapan",
      spokenResponse: "Maaf, saya tidak mendengar ucapan dengan jelas.",
      shouldExecute: false,
    };
  }

  const raw = rawTranscript.trim();
  const stripped = stripWakeWord(raw);
  const normalized = normalizeTranscript(stripped || raw);

  // 1. Cek perintah pengakhiran sesi ("bye", "selesai", "tutup")
  if (
    /^(bye|goodbye|dadah|sampai jumpa|tutup|tutup sesi|selesai|akhiri|akhiri sesi|stop sesi|keluar)$/i.test(
      normalized
    ) ||
    /\b(sampai jumpa|dadah aira|selesai aira|bye aira|tutup sesi)\b/i.test(normalized)
  ) {
    return {
      type: "session_control",
      intent: "control:bye",
      confidence: 0.98,
      userText: raw,
      commandText: stripped || raw,
      actionTitle: "Mengakhiri Sesi Suara",
      spokenResponse: "Sampai jumpa! Sesi suara diakhiri.",
      shouldExecute: true,
      action: { kind: "end_session" },
    };
  }

  // 2. Cek perintah menghentikan pembicaraan ("berhenti bicara", "diam", "stop")
  if (
    /^(berhenti|berhenti bicara|diam|stop|cukup|batal|cancel|mute)$/i.test(
      normalized
    ) ||
    /\b(berhenti bicara|jangan bicara|diam dulu)\b/i.test(normalized)
  ) {
    return {
      type: "session_control",
      intent: "control:stop_speaking",
      confidence: 0.95,
      userText: raw,
      commandText: stripped || raw,
      actionTitle: "Menghentikan Pembicaraan",
      spokenResponse: "",
      shouldExecute: true,
      action: { kind: "stop_speaking" },
    };
  }

  // 3. Cek perintah dengarkan ("dengarkan", "mulai dengar")
  if (/^(dengarkan|mulai dengar|dengar|siap|aktif)$/i.test(normalized)) {
    return {
      type: "session_control",
      intent: "control:listen",
      confidence: 0.9,
      userText: raw,
      commandText: stripped || raw,
      actionTitle: "Mendengarkan",
      spokenResponse: "Saya mendengarkan, silakan bicara.",
      shouldExecute: true,
      action: { kind: "listen" },
    };
  }

  // 4. Cek perintah ulangi ("ulangi", "katakan lagi")
  if (/^(ulangi|katakan lagi|bicara lagi|apa tadi)$/i.test(normalized)) {
    return {
      type: "session_control",
      intent: "control:repeat",
      confidence: 0.9,
      userText: raw,
      commandText: stripped || raw,
      actionTitle: "Mengulangi Respons",
      spokenResponse: context.lastResponse || "Tidak ada respons sebelumnya untuk diulangi.",
      shouldExecute: true,
      action: { kind: "repeat" },
    };
  }

  // 5. Cek perintah bantuan ("bisa apa saja", "perintah apa saja", "help")
  if (
    /\b(bisa apa saja|apa yang bisa kamu lakukan|bantuan|daftar perintah|help)\b/i.test(
      normalized
    )
  ) {
    return {
      type: "info",
      intent: "control:help",
      confidence: 0.95,
      userText: raw,
      commandText: stripped || raw,
      actionTitle: "Bantuan Perintah Suara",
      spokenResponse:
        "Kamu bisa meminta saya membuka topologi, daftar perangkat, terminal AKANE, chat, atau pengaturan.",
      shouldExecute: false,
    };
  }

  // 6. Cek perintah Navigasi Halaman UI
  // Pola: "(buka|tampilkan|lihat|pindah ke|masuk ke|navigasi ke) <halaman>"
  const hasNavPrefix =
    /\b(buka|tampilkan|lihat|pindah|masuk|tuju|navigasi|ke|open|show|go to)\b/i.test(
      normalized
    );

  for (const item of PAGE_KEYWORDS) {
    const matched = item.patterns.some((pattern) => pattern.test(normalized));
    if (matched) {
      // Prioritaskan bila ada prefix navigasi atau bila teks hanya berisi kata kunci itu
      const isDirectMatch =
        hasNavPrefix ||
        normalized.split(" ").length <= 4 ||
        new RegExp(`^${item.page}$`, "i").test(normalized);

      if (isDirectMatch) {
        return {
          type: "navigation",
          intent: `navigate:${item.page}`,
          confidence: hasNavPrefix ? 0.96 : 0.88,
          userText: raw,
          commandText: stripped || raw,
          actionTitle: `Membuka ${item.label}`,
          spokenResponse: item.spoken,
          shouldExecute: true,
          action: {
            kind: "navigate",
            target: item.page,
            pageLabel: item.label,
          },
        };
      }
    }
  }

  // 7. Jika murni panggilan wake word saja ("AIRA", "Hai AIRA")
  if (!stripped || isPureWakeWord(raw)) {
    return {
      type: "wake_acknowledgement",
      intent: "wake:greet",
      confidence: 0.95,
      userText: raw,
      commandText: "",
      actionTitle: "AIRA Siap",
      spokenResponse: "Ya, ada yang bisa saya bantu?",
      shouldExecute: false,
    };
  }

  // 8. Fallback: Pertanyaan / Perintah bebas yang diarahkan ke AI Chat Engine
  return {
    type: "chat_query",
    intent: "chat:query",
    confidence: 0.75,
    userText: raw,
    commandText: stripped || raw,
    actionTitle: "Memproses Pertanyaan AI",
    spokenResponse: null, // Dinamis dari respons LLM
    shouldExecute: true,
    action: {
      kind: "chat_query",
      prompt: stripped || raw,
    },
  };
}
