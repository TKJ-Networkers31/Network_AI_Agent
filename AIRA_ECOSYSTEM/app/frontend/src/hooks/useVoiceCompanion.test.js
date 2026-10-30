// src/hooks/useVoiceCompanion.test.js
import test from "node:test";
import assert from "node:assert/strict";
import {
  COMPANION_STATES,
  cleanTextForSpeech,
} from "./useVoiceCompanion.js";

test("COMPANION_STATES: memiliki seluruh 6 status siklus hidup", () => {
  assert.equal(COMPANION_STATES.DISABLED, "DISABLED");
  assert.equal(COMPANION_STATES.STANDBY, "STANDBY");
  assert.equal(COMPANION_STATES.LISTENING, "LISTENING");
  assert.equal(COMPANION_STATES.PROCESSING, "PROCESSING");
  assert.equal(COMPANION_STATES.SPEAKING, "SPEAKING");
  assert.equal(COMPANION_STATES.ERROR, "ERROR");
});

test("cleanTextForSpeech: membersihkan teks Markdown, kode, dan link untuk TTS", () => {
  const markdownText = `
### Hasil Konfigurasi
Berikut adalah link [Topology](/topology) dan kode:
\`\`\`bash
/ip route print
\`\`\`
Gunakan opsi \`default-route=yes\` ya!
`;

  const cleaned = cleanTextForSpeech(markdownText);
  assert.equal(cleaned.includes("```"), false);
  assert.equal(cleaned.includes("/ip route print"), false);
  assert.equal(cleaned.includes("Topology"), true);
  assert.equal(cleaned.includes("default-route=yes"), true);
  assert.equal(cleaned.includes("###"), false);
});

test("cleanTextForSpeech: aman terhadap input kosong atau non-string", () => {
  assert.equal(cleanTextForSpeech(""), "");
  assert.equal(cleanTextForSpeech(null), "");
  assert.equal(cleanTextForSpeech(undefined), "");
  assert.equal(cleanTextForSpeech(123), "");
});

test("Voice Lifecycle: simulasi onend TIDAK memulai ulang mikrofon saat STANDBY", () => {
  let startCount = 0;
  const mockRecognition = {
    start() { startCount += 1; },
    stop() {},
  };

  const stateRef = { current: COMPANION_STATES.STANDBY };
  const isPausedRef = { current: false };
  let restartScheduled = false;

  function handleOnEnd() {
    if (isPausedRef.current) return;
    if (stateRef.current === COMPANION_STATES.LISTENING) {
      restartScheduled = true;
      mockRecognition.start();
    }
  }

  // Saat standby, onend dipanggil
  handleOnEnd();
  assert.equal(restartScheduled, false, "Restart tidak boleh dijadwalkan saat STANDBY");
  assert.equal(startCount, 0, "start() tidak boleh dipanggil saat STANDBY");
});

test("Voice Lifecycle: simulasi onend memulai ulang HANYA saat LISTENING aktif dengan batas retry", () => {
  let startCount = 0;
  const mockRecognition = {
    start() { startCount += 1; },
    stop() {},
  };

  const stateRef = { current: COMPANION_STATES.LISTENING };
  const isPausedRef = { current: false };
  let consecutiveRestarts = 0;

  function handleOnEnd() {
    if (isPausedRef.current) return;
    if (stateRef.current === COMPANION_STATES.LISTENING) {
      if (consecutiveRestarts >= 3) {
        stateRef.current = COMPANION_STATES.STANDBY;
        return;
      }
      consecutiveRestarts += 1;
      mockRecognition.start();
    }
  }

  // Panggilan 1..3 berhasil restart
  handleOnEnd();
  assert.equal(startCount, 1);
  handleOnEnd();
  assert.equal(startCount, 2);
  handleOnEnd();
  assert.equal(startCount, 3);

  // Panggilan ke-4 melampaui batas -> kembali ke STANDBY tanpa looping tak terbatas
  handleOnEnd();
  assert.equal(startCount, 3, "start() tidak boleh dipanggil lagi setelah batas max retry");
  assert.equal(stateRef.current, COMPANION_STATES.STANDBY, "Harus transisi ke STANDBY setelah batas retry");
});

test("Voice Lifecycle: klaim mikrofon (aira:mic-claimed) menghentikan sesi aktif tanpa error", () => {
  let stopped = false;
  const mockRecognition = {
    stop() { stopped = true; },
  };

  const isPausedRef = { current: false };
  const stateRef = { current: COMPANION_STATES.LISTENING };

  function onMicClaimed() {
    isPausedRef.current = true;
    mockRecognition.stop();
  }

  onMicClaimed();
  assert.equal(stopped, true);
  assert.equal(isPausedRef.current, true);
});
