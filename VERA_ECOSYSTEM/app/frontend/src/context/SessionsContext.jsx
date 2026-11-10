import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "../api.js";

const SessionsContext = createContext(null);
const SESSION_STORAGE_KEY = "vera_active_session_id";

function getInitialActiveId() {
  if (typeof window === "undefined") return null;
  try {
    const urlParam = new URLSearchParams(window.location.search).get("session");
    if (urlParam && urlParam !== "new" && urlParam !== "null") {
      return urlParam;
    }
    const saved = localStorage.getItem(SESSION_STORAGE_KEY);
    if (saved && saved !== "null" && saved !== "undefined") {
      return saved;
    }
  } catch {}
  return null;
}

export function SessionsProvider({ children }) {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveIdState] = useState(getInitialActiveId);
  const [sessionsReady, setSessionsReady] = useState(false);

  const setActiveId = useCallback((idOrUpdater) => {
    setActiveIdState((prev) => {
      const nextId = typeof idOrUpdater === "function" ? idOrUpdater(prev) : idOrUpdater;
      try {
        if (nextId) {
          localStorage.setItem(SESSION_STORAGE_KEY, nextId);
          const url = new URL(window.location.href);
          url.searchParams.set("session", nextId);
          window.history.replaceState({}, "", url.toString());
        } else {
          localStorage.removeItem(SESSION_STORAGE_KEY);
          const url = new URL(window.location.href);
          url.searchParams.delete("session");
          window.history.replaceState({}, "", url.toString());
        }
      } catch {}
      return nextId;
    });
  }, []);

  const loadSessions = useCallback(() => {
    return api.sessions
      .list()
      .then((res) => {
        const list = res.sessions || [];
        setSessions(list);
        setActiveIdState((currentId) => {
          if (currentId && list.length > 0 && !list.some((s) => s.id === currentId)) {
            try {
              localStorage.removeItem(SESSION_STORAGE_KEY);
              const url = new URL(window.location.href);
              url.searchParams.delete("session");
              window.history.replaceState({}, "", url.toString());
            } catch {}
            return null;
          }
          return currentId;
        });
        return list;
      })
      .catch(() => []);
  }, []);

  // FIX (Sprint 2.5 - Session): sebelumnya init() memanggil
  // GET /api/sessions/active yang (a) membuka sesi TERAKHIR, bukan chat
  // baru, dan (b) bisa MEMBUAT sesi baru di server - dua kali kalau
  // StrictMode menjalankan effect dua kali pada DB kosong. Sekarang app
  // selalu dibuka di New Chat kosong (activeId=null); sesi baru baru
  // dibuat server-side saat pesan pertama dikirim (lihat
  // ChatRuntimeContext.ensureSession). Init hanya MEMBACA daftar history,
  // jadi aman dijalankan berkali-kali.
  useEffect(() => {
    let cancelled = false;

    loadSessions().finally(() => {
      if (!cancelled) setSessionsReady(true);
    });

    function handleAuthSuccess() {
      loadSessions();
    }
    window.addEventListener("aira:auth_success", handleAuthSuccess);

    return () => {
      cancelled = true;
      window.removeEventListener("aira:auth_success", handleAuthSuccess);
    };
  }, [loadSessions]);

  const startNewChat = useCallback(() => {
    try {
      localStorage.removeItem(SESSION_STORAGE_KEY);
      const url = new URL(window.location.href);
      url.searchParams.delete("session");
      window.history.replaceState({}, "", url.toString());
    } catch {}
    setActiveId(null);
  }, [setActiveId]);

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