import { useState } from "react";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useToast } from "./Toast.jsx";

const NAV_ITEMS = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "devices", label: "Devices", icon: "🖧" },
  { id: "memory", label: "Memory", icon: "🧠" },
  { id: "settings", label: "Settings", icon: "⚙️" },
];

function timeAgo(ts) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "baru saja";
  if (diff < 3600) return `${Math.floor(diff / 60)}m lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}j lalu`;
  return `${Math.floor(diff / 86400)}h lalu`;
}

export default function Sidebar({ active, onChange, isOpen, onClose }) {
  const {
    sessions,
    activeId,
    setActiveId,
    startNewChat,
    renameSession,
    deleteSession,
  } = useSessionsContext();

  const { notify } = useToast();

  const [sessionsOpen, setSessionsOpen] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  function closeDrawer() {
    onClose?.();
  }

  function goToNav(id) {
    onChange(id);
    closeDrawer();
  }

  function handleNewChat() {
    startNewChat();
    goToNav("chat");
  }

  function handleSelectSession(id) {
    setActiveId(id);
    goToNav("chat");
  }

  function startEdit(session) {
    setEditingId(session.id);
    setEditValue(session.title);
    setConfirmDeleteId(null);
  }

  async function commitEdit(id) {
    const title = editValue.trim();
    setEditingId(null);
    if (!title) return;

    try {
      await renameSession(id, title);
      notify({ type: "success", message: "Judul chat diperbarui.", duration: 2500 });
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function confirmDelete(id, title) {
    setDeletingId(id);
    try {
      await deleteSession(id);
      notify({ type: "success", message: `Chat "${title}" dihapus.`, duration: 2500 });
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  }

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={closeDrawer}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] transform transition-transform duration-200 ease-out
          md:static md:z-auto md:w-64 md:max-w-none md:translate-x-0
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          bg-panel border-r border-border flex flex-col h-full overflow-hidden shrink-0`}
      >
        <div className="px-5 py-5 border-b border-border flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-accent-gradient flex items-center justify-center text-sm font-bold shrink-0">
              AI
            </div>
            <div className="min-w-0">
              <div className="font-semibold text-white leading-tight truncate">
                Network Agent
              </div>
              <div className="text-[10px] uppercase tracking-wide text-white/40">
                AI Assistant
              </div>
            </div>
          </div>

          <button
            onClick={closeDrawer}
            className="md:hidden shrink-0 w-9 h-9 flex items-center justify-center rounded-lg border border-border text-white/60"
            aria-label="Tutup menu"
          >
            ✕
          </button>
        </div>

        <nav className="px-3 py-4 space-y-1 shrink-0">
          {NAV_ITEMS.map((item) => {
            const isItemActive = active === item.id;
            return (
              <button
                key={item.id}
                onClick={() => goToNav(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition
                  ${
                    isItemActive
                      ? "bg-accent-gradient text-white shadow-lg shadow-accent/20"
                      : "text-white/60 hover:text-white hover:bg-white/5"
                  }`}
              >
                <span>{item.icon}</span>
                <span className="font-medium">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="border-t border-border flex flex-col flex-1 min-h-0">
          <button
            type="button"
            onClick={() => setSessionsOpen((v) => !v)}
            className="flex items-center justify-between px-4 py-3 text-xs font-semibold tracking-wide text-white/40 hover:text-white/70 transition shrink-0"
          >
            <span>Riwayat chat</span>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className={`transition-transform ${sessionsOpen ? "rotate-180" : ""}`}
              style={{ width: 14, height: 14 }}
            >
              <path
                d="m6 9 6 6 6-6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          {sessionsOpen && (
            <div className="flex-1 min-h-0 flex flex-col px-2 pb-2">
              <button
                onClick={handleNewChat}
                className="mb-2 shrink-0 flex items-center justify-center gap-2 bg-accent-gradient text-white text-sm font-semibold py-2.5 rounded-lg"
              >
                + Chat baru
              </button>

              <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pr-0.5">
                {sessions.map((s) => {
                  const isRowActive = s.id === activeId && active === "chat";
                  const isEditing = editingId === s.id;
                  const isConfirming = confirmDeleteId === s.id;

                  return (
                    <div
                      key={s.id}
                      onClick={() => !isEditing && !isConfirming && handleSelectSession(s.id)}
                      className={`group rounded-lg px-3 py-2.5 cursor-pointer text-sm transition
                        ${
                          isRowActive
                            ? "bg-white/10 text-white"
                            : "text-white/60 hover:bg-white/5 hover:text-white"
                        }
                        ${isConfirming ? "bg-red-500/10 ring-1 ring-red-500/30" : ""}`}
                    >
                      {isEditing ? (
                        <input
                          autoFocus
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") commitEdit(s.id);
                            if (e.key === "Escape") setEditingId(null);
                          }}
                          onBlur={() => commitEdit(s.id)}
                          className="w-full bg-transparent border-b border-accent outline-none text-white text-sm"
                        />
                      ) : isConfirming ? (
                        <div
                          className="flex items-center justify-between gap-2"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <span className="text-xs text-red-300">Hapus chat ini?</span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <button
                              type="button"
                              disabled={deletingId === s.id}
                              onClick={() => confirmDelete(s.id, s.title)}
                              className="text-[11px] font-medium px-2.5 py-1 rounded-md bg-red-500/20 text-red-300 hover:bg-red-500/30 disabled:opacity-50"
                            >
                              {deletingId === s.id ? "..." : "Hapus"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmDeleteId(null)}
                              className="text-[11px] px-2.5 py-1 rounded-md bg-white/5 text-white/50 hover:text-white"
                            >
                              Batal
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate">{s.title}</span>
                          <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                startEdit(s);
                              }}
                              title="Ganti judul"
                              className="text-white/40 hover:text-white text-xs"
                            >
                              ✏️
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setConfirmDeleteId(s.id);
                              }}
                              title="Hapus"
                              className="text-white/40 hover:text-red-400 text-xs"
                            >
                              🗑
                            </button>
                          </div>
                        </div>
                      )}

                      {!isEditing && !isConfirming && (
                        <div className="text-[10px] text-white/30 mt-0.5">
                          {timeAgo(s.updated_at)}
                        </div>
                      )}
                    </div>
                  );
                })}

                {sessions.length === 0 && (
                  <p className="text-white/30 text-xs px-2 py-4 text-center">
                    Belum ada percakapan.
                    <br />
                    Mulai chat baru!
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-border text-[11px] text-white/30 shrink-0">
          Network AI Agent · Web UI
        </div>
      </aside>
    </>
  );
}
