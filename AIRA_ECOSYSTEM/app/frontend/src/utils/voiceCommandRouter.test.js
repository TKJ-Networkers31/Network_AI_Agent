// src/utils/voiceCommandRouter.test.js
import test from "node:test";
import assert from "node:assert/strict";
import {
  ALLOWED_PAGES,
  containsWakeWord,
  isPureWakeWord,
  normalizeTranscript,
  routeVoiceCommand,
  stripWakeWord,
} from "./voiceCommandRouter.js";

test("normalizeTranscript: membersihkan tanda baca dan spasi ganda", () => {
  assert.equal(
    normalizeTranscript("AIRA,  buka   Topologi..."),
    "aira buka topologi"
  );
  assert.equal(normalizeTranscript(""), "");
  assert.equal(normalizeTranscript(null), "");
});

test("stripWakeWord: memotong awalan wake word", () => {
  assert.equal(stripWakeWord("AIRA buka topology"), "buka topology");
  assert.equal(stripWakeWord("Hai AIRA, tampilkan chat"), "tampilkan chat");
  assert.equal(stripWakeWord("Halo Aira! buka pengaturan"), "buka pengaturan");
  assert.equal(stripWakeWord("Aira"), "");
  assert.equal(stripWakeWord("buka devices tanpa wake word"), "buka devices tanpa wake word");
});

test("containsWakeWord & isPureWakeWord: mendeteksi panggilan kata bangun", () => {
  assert.equal(containsWakeWord("halo aira apa kabar"), true);
  assert.equal(containsWakeWord("tidak ada kata bangun"), false);
  assert.equal(isPureWakeWord("AIRA"), true);
  assert.equal(isPureWakeWord("Hai Aira!"), true);
  assert.equal(isPureWakeWord("Aira buka topology"), false);
});

test("routeVoiceCommand: navigasi ke halaman Network Topology", () => {
  const variations = [
    "AIRA, buka topology.",
    "Buka topologi",
    "Tampilkan topologi jaringan",
    "Buka fabric",
    "Lihat topology jaringan",
  ];

  for (const phrase of variations) {
    const res = routeVoiceCommand(phrase);
    assert.equal(res.type, "navigation", `Gagal pada frasa: ${phrase}`);
    assert.equal(res.action.kind, "navigate");
    assert.equal(res.action.target, "topology");
    assert.equal(ALLOWED_PAGES.includes(res.action.target), true);
    assert.match(res.spokenResponse, /topologi jaringan/i);
    assert.equal(res.shouldExecute, true);
  }
});

test("routeVoiceCommand: navigasi ke halaman Devices dan AKANE Terminal", () => {
  const devRes = routeVoiceCommand("AIRA buka devices");
  assert.equal(devRes.action.target, "devices");
  assert.match(devRes.spokenResponse, /daftar perangkat/i);

  const akaneRes = routeVoiceCommand("Buka terminal AKANE");
  assert.equal(akaneRes.action.target, "akane");
  assert.match(akaneRes.spokenResponse, /terminal/i);
});

test("routeVoiceCommand: navigasi ke Chat, Workspace, Models, Persona, Memory, Logs, Settings", () => {
  const tests = [
    { input: "Buka chat", target: "chat" },
    { input: "Buka workspace", target: "workspace" },
    { input: "Tampilkan models", target: "models" },
    { input: "Buka persona", target: "persona" },
    { input: "Buka memory", target: "memory" },
    { input: "Buka log sistem", target: "logs" },
    { input: "Buka settings", target: "settings" },
  ];

  for (const { input, target } of tests) {
    const res = routeVoiceCommand(input);
    assert.equal(res.type, "navigation");
    assert.equal(res.action.target, target);
  }
});

test("routeVoiceCommand: perintah kontrol sesi 'bye' dan 'selesai'", () => {
  const byePhrases = ["bye", "AIRA, bye!", "selesai", "tutup sesi", "sampai jumpa"];
  for (const phrase of byePhrases) {
    const res = routeVoiceCommand(phrase);
    assert.equal(res.type, "session_control");
    assert.equal(res.action.kind, "end_session");
    assert.match(res.spokenResponse, /sampai jumpa/i);
    assert.equal(res.shouldExecute, true);
  }
});

test("routeVoiceCommand: perintah stop bicara / diam", () => {
  const stopPhrases = ["berhenti bicara", "diam", "stop", "cukup"];
  for (const phrase of stopPhrases) {
    const res = routeVoiceCommand(phrase);
    assert.equal(res.type, "session_control");
    assert.equal(res.action.kind, "stop_speaking");
    assert.equal(res.shouldExecute, true);
  }
});

test("routeVoiceCommand: panggilan murni wake word 'AIRA'", () => {
  const res = routeVoiceCommand("AIRA");
  assert.equal(res.type, "wake_acknowledgement");
  assert.match(res.spokenResponse, /ada yang bisa saya bantu/i);
  assert.equal(res.shouldExecute, false);
});

test("routeVoiceCommand: fallback pertanyaan bebas ke chat_query", () => {
  const res = routeVoiceCommand("AIRA, jelaskan konfigurasi firewall NAT di MikroTik");
  assert.equal(res.type, "chat_query");
  assert.equal(res.action.kind, "chat_query");
  assert.match(res.action.prompt, /konfigurasi firewall NAT/i);
  assert.equal(res.shouldExecute, true);
});

test("routeVoiceCommand: penanganan input kosong atau spasi", () => {
  const res = routeVoiceCommand("   ");
  assert.equal(res.type, "empty");
  assert.equal(res.shouldExecute, false);
});
