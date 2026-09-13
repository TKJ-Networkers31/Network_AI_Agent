import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "../api.js";

const SessionsContext = createContext(null);

export function SessionsProvider({ children }) {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [sessionsReady, setSessionsReady] = useState(false);

  const loadSessions = useCallback(() => {
    return api.sessions
      .list()
      .then((res) => setSessions(res.sessions))
      .catch(() => {});
  }, []);

  // FIX (Chat Session Lifecycle): sebelumnya activeId default null dan
  // TIDAK PERNAH di-resolve otomatis - user harus refresh/klik manual
  // sebuah sesi dulu sebelum bisa chat. Sekarang, sekali saat app
  // dibuka, kita minta backend "sesi aktif" (terakhir dipakai, atau
  // otomatis dibuatkan baru kalau belum ada sama sekali sesuai
  // GET /api/sessions/active) - frontend tidak pernah bikin dummy
  // session sendiri.
  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const active = await api.sessions.active();
        if (cancelled) return;
        setActiveId(active.id);
        await loadSessions();
      } catch {
        // Backend belum siap / gagal - biarkan activeId null, user
        // tetap bisa mulai chat baru secara manual nanti.
      } finally {
        if (!cancelled) setSessionsReady(true);
      }
    }

    init();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startNewChat = useCallback(() => {
    setActiveId(null);
  }, []);

  const renameSession = useCallback(async (id, title) => {
    await api.sessions.rename(id, title);
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title } : s))
    );
  }, []);

  const deleteSession = useCallback(async (id) => {
    await api.sessions.remove(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
    setActiveId((current) => (current === id ? null : current));
  }, []);

  // Menambah/mengupdate satu sesi di state LOKAL tanpa round-trip ke
  // server - dipakai ChatPage begitu sesi baru dibuat atau sesi yang
  // sedang aktif dapat judul baru, supaya sidebar langsung update
  // instan tanpa "kedip" nunggu loadSessions().
  const upsertSession = useCallback((session) => {
    setSessions((prev) => {
      const exists = prev.some((s) => s.id === session.id);

      if (exists) {
        return prev.map((s) =>
          s.id === session.id ? { ...s, ...session } : s
        );
      }

      return [{ created_at: session.updated_at, ...session }, ...prev];
    });
  }, []);

  return (
    <SessionsContext.Provider
      value={{
        sessions,
        activeId,
        setActiveId,
        loadSessions,
        sessionsReady,
        startNewChat,
        renameSession,
        deleteSession,
        upsertSession,
      }}
    >
      {children}
    </SessionsContext.Provider>
  );
}

export function useSessionsContext() {
  const ctx = useContext(SessionsContext);
  if (!ctx) {
    throw new Error("useSessionsContext must be used within a SessionsProvider");
  }
  return ctx;
}