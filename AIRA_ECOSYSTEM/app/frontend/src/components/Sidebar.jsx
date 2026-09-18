// app/frontend/src/components/Sidebar.jsx
// UI Redesign Sprint (Worker C) — visual refactor only. Same props,
// same context hooks, same nav items (none removed) and same handlers
// as before. Only markup/classes changed to the AIRA OS design system
// (theme/colors.js, theme/radius.js) — floating rounded sidebar,
// FEATURES / WORKSPACES sections, bottom user panel.

import { useState } from "react";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useChatRuntime } from "../context/ChatRuntimeContext.jsx";
import { useToast } from "./Toast.jsx";

const NAV_ITEMS = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "workspace", label: "Workspace", icon: "📁" },
  { id: "devices", label: "Devices", icon: "🖧" },
  { id: "akane", label: "AKANE", icon: "🔌" },
  { id: "models", label: "Models", icon: "🧩" },
  { id: "persona", label: "Persona", icon: "🎭" },
  { id: "memory", label: "Memory", icon: "🧠" },
  { id: "logs", label: "Logs", icon: "📋" },
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
  const { sessions, activeId, setActiveId, startNewChat, renameSession, deleteSession } =
    useSessionsContext();
  const { unreadSessionIds } = useChatRuntime();
  const { notify } = useToast();
  const { unreadSessionIds, runningSessionIds } = useChatRuntime();

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
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden" onClick={closeDrawer} />
      )}

      <aside
        className={`fixed inset-y-3 left-3 z-50 w-72 max-w-[85vw] transform transition-transform duration-200 ease-out
          md:static md:inset-auto md:z-auto md:w-64 md:max-w-none md:translate-x-0 md:my-3 md:ml-3
          ${isOpen ? "translate-x-0" : "-translate-x-[120%]"}
          bg-surface/90 backdrop-blur-xl border border-border rounded-card shadow-floating
          flex flex-col h-[calc(100%-1.5rem)] md:h-[calc(100vh-1.5rem)] overflow-hidden shrink-0`}
      >
        {/* Brand */}
        <div className="px-4 py-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-pill bg-sakura-gradient flex items-center justify-center text-sm font-semibold shadow-sakura-glow shrink-0">
              🌸
            </div>
            <div className="min-w-0">
              <div className="font-semibold text-text-primary leading-tight truncate">AIRA OS</div>
              <div className="text-[10px] uppercase tracking-wider text-text-secondary">
                AI Operating System
              </div>
            </div>
          </div>
          <button
            onClick={closeDrawer}
            className="md:hidden shrink-0 w-8 h-8 flex items-center justify-center rounded-pill border border-border text-text-secondary hover:text-text-primary transition"
            aria-label="Tutup menu"
          >
            ✕
          </button>
        </div>

        <button
          onClick={handleNewChat}
          className="mx-3 mb-3 shrink-0 flex items-center justify-center gap-2 bg-sakura-gradient text-white text-sm font-medium py-2.5 rounded-pill shadow-sakura-glow hover:brightness-110 transition"
        >
          + New Chat
        </button>

        {/* FEATURES */}
        <nav className="px-3 pb-2 space-y-0.5 shrink-0">
          <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-secondary/70">
            Features
          </div>
          {NAV_ITEMS.map((item) => {
            const isItemActive = active === item.id;
            return (
              <button
                key={item.id}
                onClick={() => goToNav(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-control text-sm transition
                  ${
                    isItemActive
                      ? "bg-white/[0.06] text-text-primary ring-1 ring-sakura/30"
                      : "text-text-secondary hover:text-text-primary hover:bg-white/[0.04]"
                  }`}
              >
                <span className={isItemActive ? "text-sakura" : ""}>{item.icon}</span>
                <span className="font-medium">{item.label}</span>
                {isItemActive && <span className="ml-auto w-1.5 h-1.5 rounded-pill bg-sakura" />}
              </button>
            );
          })}
        </nav>

        {/* WORKSPACES (chat sessions) */}
        <div className="border-t border-border flex flex-col flex-1 min-h-0 mt-1">
          <button
            type="button"
            onClick={() => setSessionsOpen((v) => !v)}
            className="flex items-center justify-between px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-text-secondary/70 hover:text-text-secondary transition shrink-0"
          >
            <span>Workspaces</span>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className={`transition-transform ${sessionsOpen ? "rotate-180" : ""}`}
              style={{ width: 12, height: 12 }}
            >
              <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>

          {sessionsOpen && (
            <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-2 space-y-1">
              {sessions.map((s) => {
                const isRowActive = s.id === activeId && active === "chat";
                const isEditing = editingId === s.id;
                const isConfirming = confirmDeleteId === s.id;
                const isUnread = unreadSessionIds.has(s.id);

                return (
                  <div
                    key={s.id}
                    onClick={() => !isEditing && !isConfirming && handleSelectSession(s.id)}
                    className={`group rounded-control px-3 py-2.5 cursor-pointer text-sm transition
                      ${isRowActive ? "bg-white/[0.07] text-text-primary" : "text-text-secondary hover:bg-white/[0.04] hover:text-text-primary"}
                      ${isConfirming ? "bg-danger/10 ring-1 ring-danger/30" : ""}`}
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
                        className="w-full bg-transparent border-b border-sakura outline-none text-text-primary text-sm"
                      />
                    ) : isConfirming ? (
                      <div className="flex items-center justify-between gap-2" onClick={(e) => e.stopPropagation()}>
                        <span className="text-xs text-danger">Hapus chat ini?</span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            disabled={deletingId === s.id}
                            onClick={() => confirmDelete(s.id, s.title)}
                            className="text-[11px] font-medium px-2.5 py-1 rounded-pill bg-danger/20 text-danger hover:bg-danger/30 disabled:opacity-50"
                          >
                            {deletingId === s.id ? "..." : "Hapus"}
                          </button>
                          <button
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-[11px] px-2.5 py-1 rounded-pill bg-white/5 text-text-secondary hover:text-text-primary"
                          >
                            Batal
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 min-w-0">
                          {isUnread && <span className="shrink-0 w-1.5 h-1.5 rounded-pill bg-sakura" />}
                          {runningSessionIds?.has(s.id) && (
                            <span className="shrink-0 w-1.5 h-1.5 rounded-pill bg-cyan animate-pulse" title="Sedang diproses" />
                          )}
                          <span className="truncate">{s.title}</span>
                        </span>
                        <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              startEdit(s);
                            }}
                            title="Ganti judul"
                            className="text-text-secondary hover:text-text-primary text-xs"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteId(s.id);
                            }}
                            title="Hapus"
                            className="text-text-secondary hover:text-danger text-xs"
                          >
                            🗑
                          </button>
                        </div>
                      </div>
                    )}
                    {!isEditing && !isConfirming && (
                      <div className="text-[10px] text-text-secondary/60 mt-0.5">{timeAgo(s.updated_at)}</div>
                    )}
                  </div>
                );
              })}

              {sessions.length === 0 && (
                <p className="text-text-secondary/60 text-xs px-2 py-4 text-center">
                  Belum ada percakapan.
                  <br />
                  Mulai chat baru!
                </p>
              )}
            </div>
          )}
        </div>

        {/* Bottom user panel */}
        <div className="p-3 border-t border-border shrink-0">
          <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-control bg-white/[0.04]">
            <div className="w-8 h-8 rounded-pill bg-accent-gradient flex items-center justify-center text-xs font-semibold shrink-0">
              L
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-text-primary truncate">Lingga</div>
              <div className="text-[10px] text-text-secondary truncate">AIRA Ecosystem</div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}