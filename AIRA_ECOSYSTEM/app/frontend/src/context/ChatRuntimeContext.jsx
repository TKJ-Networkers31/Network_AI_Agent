import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useSessionsContext } from "./SessionsContext.jsx";
import { useAiraSocketPool } from "../hooks/useAiraSocketPool.js";
import { api } from "../api.js";
import { createSingleFlight } from "../utils/singleFlight.js";
import {
  EVENT_RESPONSE_CHUNK,
  PHASE_REGENERATING,
  PHASE_SENDING,
  classifyRunEvent,
  createRun,
  deriveChatView,
  reduceRunEvent,
  settleStreamingMessage,
} from "../utils/runLifecycle.js";

const ChatRuntimeContext = createContext(null);

const NOTICE_STOPPED = "⏹ Proses dihentikan.";
const NOTICE_STOPPED_RESTORED = "⏹ Proses dihentikan — percakapan dikembalikan seperti sebelumnya.";

function makeRunId() {
  // crypto.randomUUID hanya ada di secure context (https/localhost) -
  // AIRA sering dibuka lewat http://IP-LAN, jadi wajib ada fallback.
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 12);
  }
  return `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * ChatRuntimeProvider — dipasang di App.jsx level (bukan di dalam
 * ChatPage) supaya koneksi WebSocket + state pesan TIDAK putus saat
 * user pindah ke halaman lain (Devices/Models/Persona/dst) lalu balik
 * lagi ke Chat.
 *
 * PERUBAHAN BESAR (Chat Session):
 *
 * 1. STATE PROSES SEKARANG PER-SESI (runsBySession). Sebelumnya
 *    loading/phase/liveTools adalah state GLOBAL - prompt yang sedang
 *    diproses di sesi A ikut "muncul" (spinner, input terkunci, langkah
 *    tool) di sesi B setelah user pindah sesi. Sekarang tiap sesi punya
 *    state proses sendiri; `loading/phase/liveTools` yang diekspos ke
 *    ChatPage hanyalah milik SESI AKTIF.
 *
 * 2. SOCKET PER-SESI (useAiraSocketPool). Sesi yang sedang memproses
 *    dijaga tetap tersambung walau user pindah ke sesi lain, jadi
 *    balasannya tetap masuk ke sesi yang benar (dan sesi itu ditandai
 *    "belum dibaca" di Sidebar).
 *
 * 3. FIX "PROMPT HILANG": race condition antara bubble user (optimistic)
 *    dan fetch riwayat sesi. Sesi BARU dulu tetap memicu fetch riwayat
 *    begitu activeId berganti; kalau fetch (kosong) selesai SETELAH
 *    bubble user ditambahkan, ia menimpa seluruh pesan sesi itu -> bubble
 *    prompt lenyap padahal proses tetap jalan. Sekarang: sesi baru ditandai
 *    "sudah dimuat" sebelum activeId berganti, dan hasil fetch DIGABUNG
 *    dengan pesan lokal, tidak lagi menimpa.
 *
 * 4. FITUR: stopRun, regenerate, editMessage. Identitas pesan memakai
 *    `turnId` (id baris chat_turns dari server), BUKAN index array.
 *
 * 5. FIX (Sprint 2.5 - Session): pembuatan sesi baru SATU jalur lewat
 *    ensureSession() + single-flight. Sebelumnya dua kirim beruntun di
 *    New Chat (activeIdRef belum terupdate sebelum render) membuat dua
 *    sesi di server, dan sesi yang selesai dibuat menarik tampilan user
 *    balik walau ia sudah pindah ke history lain.
 *
 * 6. FIX (Sprint 2.5 - Thinking/Loading UX): siklus proses
 *    kirim -> thinking -> streaming -> selesai/error/cancel. Aturan
 *    transisinya ada di utils/runLifecycle.js (fungsi murni + test);
 *    state-nya tetap runsBySession/messagesBySession di sini - tidak ada
 *    sistem loading baru. Ringkas:
 *    - event `response_chunk` (belum dikirim backend, lihat runLifecycle.js)
 *      mengakhiri fase thinking sekali saja; chunk berikutnya tidak
 *      me-restart animasi dan pesan streaming DIGANTI di tempat oleh
 *      `response` (bukan di-push -> tidak ada bubble ganda/remount).
 *    - error NON-fatal tidak lagi mengakhiri proses lebih awal (input
 *      terbuka padahal server masih bekerja) dan tidak menambah bubble
 *      ganda: `response` selalu menyusul dan membawa teks errornya.
 *    - New Chat menampilkan "Mengirim..." selama sesi dibuat (creatingSession).
 */
export function ChatRuntimeProvider({ children, isOnChatPage }) {
  const { activeId, upsertSession } = useSessionsContext();

  // Pesan disimpan PER session_id supaya pindah sesi tidak saling
  // menimpa / tidak perlu re-fetch tiap kali balik ke sesi yang sama.
  const [messagesBySession, setMessagesBySession] = useState({});
  // { [sessionId]: { runId, status, phase, liveTools } } - ada entri = sedang
  // diproses (status: "thinking" | "streaming", lihat utils/runLifecycle.js)
  const [runsBySession, setRunsBySession] = useState({});
  const [loadingHistoryIds, setLoadingHistoryIds] = useState(() => new Set());
  const [unreadSessionIds, setUnreadSessionIds] = useState(() => new Set());
  const [persona, setPersona] = useState(null);
  const [personaReady, setPersonaReady] = useState(false);
  // New Chat sedang membuat sesi di server (run pertama belum ada).
  const [creatingSession, setCreatingSession] = useState(false);

  // Cermin sinkron dari state di atas - dibaca di dalam callback/event
  // handler supaya tidak kena stale closure dan bisa dipakai untuk guard
  // "sedang berjalan" secara instan (sebelum React sempat re-render).
  const messagesRef = useRef({});
  const runsRef = useRef({});
  const snapshotsRef = useRef({}); // sid -> pesan sebelum edit/regenerate (untuk rollback)
  const staleRunIdsRef = useRef(new Set()); // run_id yang sudah di-stop user
  const loadedSessionsRef = useRef(new Set());
  const voiceHandlersRef = useRef(null);
  const createSessionRef = useRef(null); // single-flight pembuat sesi baru

  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;

  // --------------------------------------------------------------
  // HELPER STATE
  // --------------------------------------------------------------

  const setMessagesForSession = useCallback((sessionId, updater) => {
    if (!sessionId) return;
    const current = messagesRef.current[sessionId] || [];
    const next = typeof updater === "function" ? updater(current) : updater;
    messagesRef.current = { ...messagesRef.current, [sessionId]: next };
    setMessagesBySession(messagesRef.current);
  }, []);

  const setRun = useCallback((sessionId, run) => {
    const next = { ...runsRef.current };
    if (run) next[sessionId] = run;
    else delete next[sessionId];
    runsRef.current = next;
    setRunsBySession(next);
  }, []);

  // Terapkan satu event WebSocket lewat reducer murni (utils/runLifecycle.js)
  // lalu tulis HANYA bagian yang berubah (perbandingan referensi) - chunk
  // berikutnya tidak menyentuh run sama sekali, jadi animasi tidak re-render.
  const commitRunEvent = useCallback(
    (sessionId, event) => {
      const before = {
        run: runsRef.current[sessionId] || null,
        messages: messagesRef.current[sessionId] || [],
      };

      const after = reduceRunEvent(before, event, { staleRunIds: staleRunIdsRef.current });

      if (after.messages !== before.messages) setMessagesForSession(sessionId, after.messages);
      if (after.run !== before.run) setRun(sessionId, after.run);
    },
    [setMessagesForSession, setRun]
  );

  // Akhiri proses dengan pesan error lokal. Kalau ada snapshot (edit/
  // regenerate), percakapan dikembalikan ke kondisi sebelum diubah - server
  // memang belum menghapus apa pun saat proses gagal.
  const failRun = useCallback(
    (sessionId, text) => {
      const failedRunId = runsRef.current[sessionId]?.runId;

      setRun(sessionId, null);

      const snapshot = snapshotsRef.current[sessionId];
      delete snapshotsRef.current[sessionId];

      const bubble = { role: "assistant", content: text, local: true, isNew: true };
      setMessagesForSession(sessionId, (prev) =>
        snapshot
          ? [...snapshot, bubble]
          : [...settleStreamingMessage(prev, failedRunId), bubble]
      );

      voiceHandlersRef.current?.cancelWaiting?.();
    },
    [setRun, setMessagesForSession]
  );

  // --------------------------------------------------------------
  // WEBSOCKET EVENT HANDLER — satu jalur untuk teks, suara, DAN
  // dio_submission (semuanya lewat api/routers/ws.py::chat_ws).
  // Setiap event membawa session_id + run_id; event dari proses yang
  // sudah di-stop (run_id basi) atau dari proses lain dibuang.
  // --------------------------------------------------------------
  const handleEvent = useCallback(
    (event) => {
      const { type, data = {} } = event || {};
      if (!type) return;

      const sid = data.session_id;
      if (!sid) return;

      const runId = data.run_id;
      const current = runsRef.current[sid];
      const { isStale, isOtherRun } = classifyRunEvent(current, data, staleRunIdsRef.current);

      switch (type) {
        // Semua transisi thinking/streaming ada di reducer (utils/runLifecycle.js):
        // ack (giliran suara mengadopsi run_id server), thinking, tool_*, dan
        // response_chunk (chunk pertama mengakhiri fase thinking, berikutnya no-op).
        case "ack":
        case "thinking":
        case "tool_start":
        case "tool_finish":
        case EVENT_RESPONSE_CHUNK: {
          commitRunEvent(sid, event);
          break;
        }

        case "transcript": {
          if (isStale) break;
          // hasil STT dari voice call mode - tampilkan sebagai bubble user
          setMessagesForSession(sid, (prev) => [
            ...prev,
            { role: "user", content: data.text, isNew: true },
          ]);
          break;
        }

        case "transcript_empty": {
          voiceHandlersRef.current?.cancelWaiting?.();
          if (current && !isOtherRun) setRun(sid, null);
          break;
        }

        case "response": {
          // Selalu ditampilkan (termasuk bila run_id-nya basi): kalau server
          // sempat menyelesaikan giliran sebelum pesan Stop terbaca, hasilnya
          // SUDAH tersimpan di database, jadi UI harus ikut menampilkannya.
          // Reducer: mengganti pesan streaming milik run ini di tempat (atau
          // menambah satu pesan kalau tidak ada), memberi id server ke bubble
          // user, dan mengakhiri run kecuali event ini milik run lain.
          commitRunEvent(sid, event);

          if (!isOtherRun) {
            delete snapshotsRef.current[sid];
          }

          if (runId) staleRunIdsRef.current.delete(runId);

          if (data.session_title) {
            upsertSession({
              id: sid,
              title: data.session_title,
              updated_at: Date.now() / 1000,
            });
          }

          if (sid !== activeIdRef.current) {
            setUnreadSessionIds((prev) => {
              const next = new Set(prev);
              next.add(sid);
              return next;
            });
          }

          voiceHandlersRef.current?.playResponseAudio?.(
            data.audio_base64,
            data.answer
          );
          break;
        }

        case "cancelled": {
          if (runId) staleRunIdsRef.current.delete(runId);

          // Kasus normal (user menekan Stop): proses sudah diakhiri lokal
          // saat tombol ditekan, jadi tidak ada yang perlu dilakukan.
          // Kasus lain (mis. sesi dihapus saat berjalan): akhiri proses
          // yang masih tercatat dan kembalikan snapshot kalau ada.
          if (current && !isOtherRun && !isStale) {
            setRun(sid, null);
            const snapshot = snapshotsRef.current[sid];
            delete snapshotsRef.current[sid];
            if (snapshot) setMessagesForSession(sid, snapshot);
            else setMessagesForSession(sid, (prev) => settleStreamingMessage(prev, current.runId));
            voiceHandlersRef.current?.cancelWaiting?.();
          }
          break;
        }

        case "error": {
          if (isStale || isOtherRun) break;

          if (data.fatal) {
            // Error dari server sendiri: tidak akan ada event "response" lagi.
            failRun(sid, `⚠ ${data.message}`);
            break;
          }

          // Error non-fatal (mis. planner gagal / batas tool): event "response"
          // SELALU menyusul (api/routers/ws.py) dan membawa teks errornya.
          // Proses TIDAK diakhiri di sini - sebelumnya animasi berhenti dan
          // input terbuka padahal server masih bekerja, lalu bubble error
          // muncul dua kali (lokal + response).
          break;
        }

        default:
          break;
      }
    },
    [commitRunEvent, failRun, setMessagesForSession, setRun, upsertSession]
  );

  // --------------------------------------------------------------
  // SOCKET POOL — sesi aktif + semua sesi yang sedang diproses
  // --------------------------------------------------------------
  const runningIds = Object.keys(runsBySession);

  const { statusById, sendTo, waitUntilOpen, isOpenFor } = useAiraSocketPool({
    activeId,
    keepAliveIds: runningIds,
    onEvent: handleEvent,
  });

  // --------------------------------------------------------------
  // PERSONA — dimuat sekali, dipakai Hero/greeting (buildGreeting)
  // --------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    api.persona
      .get()
      .then((res) => {
        if (!cancelled) setPersona(res.profile || {});
      })
      .catch(() => {
        if (!cancelled) setPersona({});
      })
      .finally(() => {
        if (!cancelled) setPersonaReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // --------------------------------------------------------------
  // LOAD HISTORY — sekali per session_id, supaya reload halaman /
  // buka sesi lama tetap tampil riwayatnya. Hasil fetch DIGABUNG dengan
  // pesan lokal (bukan menimpa) - lihat catatan "PROMPT HILANG" di atas.
  // --------------------------------------------------------------
  useEffect(() => {
    if (!activeId) return;
    if (loadedSessionsRef.current.has(activeId)) return;

    const sid = activeId;
    loadedSessionsRef.current.add(sid);

    setLoadingHistoryIds((prev) => {
      const next = new Set(prev);
      next.add(sid);
      return next;
    });

    api.sessions
      .messages(sid)
      .then((res) => {
        const turns = (res.turns || []).map((t) => ({
          role: t.role,
          content: t.content,
          steps: t.steps || [],
          interactionSchema: t.interaction_schema || null,
          turnId: t.id,
        }));

        const local = messagesRef.current[sid] || [];

        if (local.length === 0) {
          setMessagesForSession(sid, turns);
          return;
        }

        // Ada pesan lokal yang masuk selagi fetch berjalan (mis. balasan
        // WebSocket): pertahankan, kecuali yang sudah ada di server.
        const serverIds = new Set(turns.map((t) => t.turnId));
        const extras = local.filter(
          (m) => m.isNew && !(m.turnId != null && serverIds.has(m.turnId))
        );
        setMessagesForSession(sid, [...turns, ...extras]);
      })
      .catch(() => {
        // sesi baru / belum ada riwayat - biarkan messages tetap apa adanya.
        // Izinkan percobaan ulang saat sesi dibuka lagi.
        loadedSessionsRef.current.delete(sid);
      })
      .finally(() => {
        setLoadingHistoryIds((prev) => {
          const next = new Set(prev);
          next.delete(sid);
          return next;
        });
      });
  }, [activeId, setMessagesForSession]);

  // Tandai sesi aktif sebagai "sudah dibaca" saat user membuka Chat page
  useEffect(() => {
    if (!activeId || !isOnChatPage) return;
    setUnreadSessionIds((prev) => {
      if (!prev.has(activeId)) return prev;
      const next = new Set(prev);
      next.delete(activeId);
      return next;
    });
  }, [activeId, isOnChatPage]);

  // --------------------------------------------------------------
  // ACTIONS
  // --------------------------------------------------------------

  /**
   * ensureSession — SATU-SATUNYA jalur membuat sesi baru dari New Chat
   * (kirim pesan DAN voice call). Kalau sudah ada sesi aktif, dikembalikan
   * apa adanya. Kalau belum, pembuatan dilindungi single-flight: panggilan
   * bersamaan berbagi SATU request create, jadi tidak ada sesi ganda.
   *
   * onNewSession hanya dipanggil kalau user MASIH di New Chat saat sesi
   * selesai dibuat. Kalau ia sudah pindah ke sesi lain, tampilannya tidak
   * ditarik balik; sesi baru tetap diproses dan muncul di sidebar (unread).
   */
  const ensureSession = useCallback(async ({ onNewSession } = {}) => {
    const current = activeIdRef.current;
    if (current) return current;

    if (createSessionRef.current === null) {
      createSessionRef.current = createSingleFlight(async (switchTo) => {
        const created = await api.sessions.create();

        // FIX prompt hilang: sesi baru pasti kosong - tandai "sudah dimuat"
        // SEBELUM activeId berganti supaya tidak memicu fetch riwayat yang
        // bisa menimpa bubble prompt.
        loadedSessionsRef.current.add(created.id);

        if (!activeIdRef.current) switchTo?.(created.id);

        return created.id;
      });
    }

    return createSessionRef.current(onNewSession);
  }, []);

  /**
   * Satu-satunya jalur untuk memulai giliran:
   *  kind = "send"       -> pesan baru (juga dipakai submit form DIO)
   *  kind = "edit"       -> ganti isi pesan user ke-`fromIndex` + jawaban sesudahnya
   *  kind = "regenerate" -> buat ulang jawaban untuk pesan user ke-`fromIndex`
   */
  const runTurn = useCallback(
    async ({ sid, kind, text, fromIndex = 0, extra = null }) => {
      if (!sid || runsRef.current[sid]) return;

      const runId = makeRunId();
      const current = messagesRef.current[sid] || [];

      let effectiveKind = kind;
      let replaceFrom = null;
      let nextMessages = null;

      if (kind === "edit" || kind === "regenerate") {
        // id turn PERTAMA yang tersimpan di server mulai dari titik ini
        for (let i = fromIndex; i < current.length; i += 1) {
          if (current[i].turnId != null) {
            replaceFrom = current[i].turnId;
            break;
          }
        }

        // Pesan user belum tersimpan di server (mis. sempat di-stop):
        // tidak ada yang bisa "di-regenerate", kirim ulang sebagai pesan biasa.
        if (kind === "regenerate" && current[fromIndex]?.turnId == null) {
          effectiveKind = "edit";
        }

        snapshotsRef.current[sid] = current;

        nextMessages =
          effectiveKind === "regenerate"
            ? current
                .slice(0, fromIndex + 1)
                .map((m, i) => (i === fromIndex ? { ...m, turnId: null } : m))
            : [...current.slice(0, fromIndex), { role: "user", content: text, isNew: true }];
      }

      setRun(
        sid,
        createRun({
          runId,
          phase: effectiveKind === "regenerate" ? PHASE_REGENERATING : PHASE_SENDING,
        })
      );

      if (nextMessages) {
        setMessagesForSession(sid, nextMessages);
      } else {
        setMessagesForSession(sid, (prev) => [
          ...prev,
          { role: "user", content: text, isNew: true },
        ]);
      }

      // Beri waktu socket tersambung (sesi baru / baru pindah sesi).
      try {
        await waitUntilOpen(sid, 5000);
      } catch {
        // biarkan sendTo() di bawah yang melaporkan kegagalan
      }

      // User menekan Stop selagi menunggu koneksi -> jangan kirim apa-apa.
      const run = runsRef.current[sid];
      if (!run || run.runId !== runId) return;

      const payload =
        effectiveKind === "regenerate"
          ? { type: "regenerate", replace_from_turn_id: replaceFrom, run_id: runId }
          : {
              message: text,
              run_id: runId,
              ...(replaceFrom != null ? { replace_from_turn_id: replaceFrom } : {}),
              ...(extra || {}),
            };

      const ok = sendTo(sid, payload);

      if (!ok) {
        failRun(sid, "⚠ Koneksi belum siap, coba lagi sebentar.");
      }
    },
    [failRun, sendTo, setMessagesForSession, setRun, waitUntilOpen]
  );

  const sendMessage = useCallback(
    async (text, { onNewSession } = {}) => {
      const existing = activeIdRef.current;

      if (existing && runsRef.current[existing]) return;

      // New Chat: sesi dibuat dulu di server. Selama itu tampilkan
      // "Mengirim..." + kunci input (lihat deriveChatView) - tanpa ini tidak
      // ada umpan balik antara tombol kirim dan run pertama.
      if (!existing) setCreatingSession(true);

      let sid;

      try {
        sid = await ensureSession({ onNewSession });
      } catch (err) {
        setCreatingSession(false);
        throw err;
      }

      // runTurn menyetel run + bubble user SECARA SINKRON sebelum await
      // pertamanya, jadi penanda creatingSession dilepas sesudahnya tanpa
      // celah tampilan (Hero tidak sempat muncul sesaat).
      const turn = runTurn({ sid, kind: "send", text });
      setCreatingSession(false);

      await turn;
    },
    [ensureSession, runTurn]
  );

  // Dipakai ChatPage.jsx saat user submit form/pilihan interaktif DIO
  // (hasil request_structured_input()) - lihat agents/rei/dio_tools.py.
  const sendDioSubmission = useCallback(
    (submission, displayText) => {
      const sid = activeIdRef.current;
      if (!sid) return;
      runTurn({ sid, kind: "send", text: displayText, extra: { dio_submission: submission } });
    },
    [runTurn]
  );

  const editMessage = useCallback(
    async (index, newText) => {
      const sid = activeIdRef.current;
      const text = (newText || "").trim();
      if (!sid || !text || runsRef.current[sid]) return;
      await runTurn({ sid, kind: "edit", text, fromIndex: index });
    },
    [runTurn]
  );

  const regenerate = useCallback(async () => {
    const sid = activeIdRef.current;
    if (!sid || runsRef.current[sid]) return;

    const list = messagesRef.current[sid] || [];
    let idx = -1;
    for (let i = list.length - 1; i >= 0; i -= 1) {
      if (list[i].role === "user") {
        idx = i;
        break;
      }
    }
    if (idx === -1) return;

    await runTurn({ sid, kind: "regenerate", text: list[idx].content, fromIndex: idx });
  }, [runTurn]);

  const stopRun = useCallback(
    (sessionId) => {
      const sid = sessionId || activeIdRef.current;
      const run = sid ? runsRef.current[sid] : null;
      if (!run) return;

      // 1. Buang semua event susulan dari proses ini.
      if (run.runId) staleRunIdsRef.current.add(run.runId);

      // 2. Minta server berhenti (best effort: berlaku di titik aman berikutnya).
      sendTo(sid, { type: "cancel" });

      // 3. UI langsung bebas - tidak menunggu server.
      setRun(sid, null);
      voiceHandlersRef.current?.cancelWaiting?.();

      const snapshot = snapshotsRef.current[sid];
      delete snapshotsRef.current[sid];

      if (snapshot) {
        // Edit/regenerate dihentikan: server tidak mengubah apa pun, jadi
        // kembalikan percakapan seperti semula.
        setMessagesForSession(sid, [
          ...snapshot,
          { role: "assistant", content: NOTICE_STOPPED_RESTORED, local: true, isNew: true },
        ]);
        return;
      }

      // Pesan baru dihentikan: bubble prompt tetap tampil (bisa di-edit lalu
      // dikirim ulang), tapi ditandai belum tersimpan di server.
      // Potongan jawaban yang sempat tampil (streaming) dipertahankan sebagai
      // pesan lokal, tidak lagi streaming.
      setMessagesForSession(sid, (prev) => {
        const next = [...settleStreamingMessage(prev, run.runId)];
        for (let i = next.length - 1; i >= 0; i -= 1) {
          if (next[i].role === "user") {
            if (next[i].turnId == null) {
              next[i] = { ...next[i], local: true, cancelled: true };
            }
            break;
          }
        }
        next.push({ role: "assistant", content: NOTICE_STOPPED, local: true, isNew: true });
        return next;
      });
    },
    [sendTo, setMessagesForSession, setRun]
  );

  const markInteractionResolved = useCallback(
    (index) => {
      const sid = activeIdRef.current;
      if (!sid) return;
      setMessagesForSession(sid, (prev) =>
        prev.map((m, i) => (i === index ? { ...m, interactionResolved: true } : m))
      );
    },
    [setMessagesForSession]
  );

  // Dipakai voice call mode - selalu ke sesi yang sedang aktif.
  const sendRaw = useCallback((payload) => sendTo(activeIdRef.current, payload), [sendTo]);

  // Menunggu socket SESI AKTIF (yang dibaca ulang tiap tick, karena
  // activeId bisa baru saja berganti) sampai benar-benar OPEN.
  const waitForConnection = useCallback(
    (timeoutMs = 8000) =>
      new Promise((resolve, reject) => {
        const startedAt = Date.now();

        const tick = () => {
          if (isOpenFor(activeIdRef.current)) {
            resolve();
            return;
          }
          if (Date.now() - startedAt > timeoutMs) {
            reject(new Error("Waktu menyambungkan ke server habis. Coba lagi."));
            return;
          }
          setTimeout(tick, 100);
        };

        tick();
      }),
    [isOpenFor]
  );

  const registerVoiceCallHandlers = useCallback((handlers) => {
    voiceHandlersRef.current = handlers;
  }, []);

  // --------------------------------------------------------------
  // NILAI TURUNAN UNTUK SESI AKTIF
  // --------------------------------------------------------------
  const messages = (activeId && messagesBySession[activeId]) || [];
  const activeRun = activeId ? runsBySession[activeId] : null;
  const { loading, streaming, phase, liveTools } = deriveChatView({
    activeRun,
    creatingSession,
    activeId,
  });
  const switching = activeId ? loadingHistoryIds.has(activeId) : false;
  const wsStatus = (activeId && statusById[activeId]) || "idle";
  const runningSessionIds = new Set(runningIds);

  return (
    <ChatRuntimeContext.Provider
      value={{
        messages,
        loading,
        phase,
        liveTools,
        streaming,
        switching,
        wsStatus,
        sendMessage,
        sendDioSubmission,
        sendRaw,
        waitForConnection,
        registerVoiceCallHandlers,
        persona,
        personaReady,
        unreadSessionIds,
        // --- baru ---
        runningSessionIds,
        stopRun,
        regenerate,
        editMessage,
        markInteractionResolved,
        ensureSession,
      }}
    >
      {children}
    </ChatRuntimeContext.Provider>
  );
}

export function useChatRuntime() {
  const ctx = useContext(ChatRuntimeContext);
  if (!ctx) {
    throw new Error("useChatRuntime must be used within a ChatRuntimeProvider");
  }
  return ctx;
}