import { useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import SessionSidebar from "../components/SessionSidebar.jsx";
import { api } from "../api.js";

export default function ChatPage() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    loadSessions();
    api
      .tools()
      .then((res) => setTools(res.tools))
      .catch(() => {
        // Kalau gagal load daftar tool, slash-command cuma tidak
        // menampilkan menu - tidak fatal, chat biasa tetap jalan.
      });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function loadSessions() {
    api.sessions
      .list()
      .then((res) => setSessions(res.sessions))
      .catch((e) => setError(e.message));
  }

  function startNewChat() {
    setActiveId(null);
    setMessages([]);
    setError(null);
  }

  async function selectSession(id) {
    if (id === activeId) return;

    setSwitching(true);
    setError(null);

    try {
      const res = await api.sessions.messages(id);
      setMessages(
        res.turns.map((t) => ({
          role: t.role,
          content: t.content,
          steps: t.steps,
        }))
      );
      setActiveId(id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSwitching(false);
    }
  }

  async function handleSend(text) {
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const result = await api.chat(text, activeId);

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.answer, steps: result.steps },
      ]);

      if (result.session_id !== activeId) {
        // Sesi baru dibuat otomatis oleh backend (giliran pertama).
        setActiveId(result.session_id);
        loadSessions();
      } else {
        setSessions((prev) =>
          prev.map((s) =>
            s.id === result.session_id
              ? {
                  ...s,
                  title: result.session_title,
                  updated_at: Date.now() / 1000,
                }
              : s
          )
        );
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRename(id, title) {
    try {
      await api.sessions.rename(id, title);
      loadSessions();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(id) {
    try {
      await api.sessions.remove(id);
      if (id === activeId) startNewChat();
      loadSessions();
    } catch (err) {
      setError(err.message);
    }
  }

  const activeTitle =
    sessions.find((s) => s.id === activeId)?.title || "Chat Baru";

  return (
    <div className="flex h-full min-h-0 gap-6">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={selectSession}
        onNew={startNewChat}
        onRename={handleRename}
        onDelete={handleDelete}
      />

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        <TopBar
          title={activeTitle}
          subtitle="Ngobrol atau ketik '/' untuk pakai tool langsung"
        />

        <div className="flex-1 overflow-y-auto min-h-0 space-y-4 pr-1 pb-3">
          {switching && (
            <p className="text-white/30 text-sm text-center mt-10">
              Memuat percakapan...
            </p>
          )}

          {!switching && messages.length === 0 && !loading && (
            <p className="text-white/30 text-sm text-center mt-10">
              Mulai percakapan baru, atau ketik{" "}
              <span className="font-mono text-accent-light">/</span> untuk
              pakai tool langsung.
            </p>
          )}

          {!switching &&
            messages.map((m, i) => (
              <MessageBubble
                key={i}
                role={m.role}
                content={m.content}
                steps={m.steps}
              />
            ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-card border border-border rounded-xl2 px-4 py-3 text-sm text-white/50">
                <span className="animate-pulse">Agent sedang berpikir...</span>
              </div>
            </div>
          )}

          {error && (
            <div className="text-xs px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300">
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div className="mt-3 mb-1">
          <ChatInput onSend={handleSend} disabled={loading} tools={tools} />
        </div>
      </div>
    </div>
  );
}
