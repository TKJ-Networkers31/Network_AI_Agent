// src/components/Sidebar.jsx
//
// PERUBAHAN (UI Layout):
// - Sidebar menempel penuh ke kiri/atas/bawah layar (tanpa margin & rounded card).
// - Bisa di-minimize (mode ikon 68px) / maximize lewat tombol panel atau Ctrl+B.
//   State `collapsed` dimiliki App.jsx (dan disimpan di localStorage di sana).
// - Menu diklasifikasi per grup (lihat navConfig.js) dan tiap grup bisa
//   dibuka/ditutup. Daftar percakapan juga jadi grup dropdown sendiri.
// - Icon memakai lucide-react (bukan emoji).
// - Mode "compact" hanya berlaku di desktop (>= md). Drawer mobile selalu
//   tampil penuh.
// - Logo header memakai emblem core sakura (BrandEmblem).

import { useEffect, useState } from "react";
import {
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useChatRuntime } from "../context/ChatRuntimeContext.jsx";
import { useToast } from "./Toast.jsx";
import { NAV_GROUPS } from "./navConfig.js";
import BrandEmblem from "./BrandEmblem.jsx";

const GROUPS_KEY = "aira_sidebar_groups";
const DEFAULT_OPEN = { main: true, network: true, ai: true, system: false, sessions: true };

function loadOpenGroups() {
  try {
    const raw = localStorage.getItem(GROUPS_KEY);
    if (raw) return { ...DEFAULT_OPEN, ...JSON.parse(raw) };
  } catch {
    // storage tidak tersedia / JSON rusak - pakai default
  }
  return DEFAULT_OPEN;
}

function timeAgo(ts) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "baru saja";
  if (diff < 3600) return `${Math.floor(diff / 60)}m lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}j lalu`;
  return `${Math.floor(diff / 86400)}h lalu`;
}

// Mode compact hanya relevan di desktop. Di mobile drawer selalu penuh.
function useIsDesktop() {
  const query = "(min-width: 768px)";
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e) => setMatches(e.matches);
    setMatches(mql.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return matches;
}

function SectionHeader({ label, open, onToggle, count }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="w-full flex items-center justify-between px-3 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-secondary/70 hover:text-text-secondary transition"
    >
      <span className="flex items-center gap-1.5">
        {label}
        {typeof count === "number" && (
          <span className="text-[10px] font-normal normal-case tracking-normal text-text-secondary/50">
            {count}
          </span>
        )}
      </span>
      <ChevronDown
        size={13}
        strokeWidth={2.2}
        className={`transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
      />
    </button>
  );
}

// Animasi buka/tutup halus tanpa perlu ukur tinggi konten.
function Collapsible({ open, children }) {
  return (
    <div
      className={`grid transition-[grid-template-rows] duration-200 ease-out ${
        open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
      }`}
    >
      <div className="overflow-hidden min-h-0">{children}</div>
    </div>
  );
}

function NavButton({ item, active, compact, dot, onClick }) {
  const Icon = item.icon;

  return (
    <button
      type="button"
      onClick={onClick}
      title={compact ? item.label : undefined}
      aria-current={active ? "page" : undefined}
      className={`relative w-full flex items-center h-9 rounded-control text-sm transition
        ${compact ? "justify-center" : "gap-3 px-3"}
        ${
          active
            ? "bg-white/[0.07] text-text-primary"
            : "text-text-secondary hover:text-text-primary hover:bg-white/[0.04]"
        }`}
    >
      {active && (
        <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-sakura" />
      )}

      <span className="relative shrink-0">
        <Icon size={18} strokeWidth={1.9} className={active ? "text-sakura" : ""} />
        {dot && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-pill bg-sakura ring-2 ring-surface" />
        )}
      </span>

      {!compact && <span className="font-medium truncate">{item.label}</span>}
    </button>
  );
}

export default function Sidebar({
  active,
  onChange,
  isOpen,
  onClose,
  collapsed = false,
  onToggleCollapsed,
}) {
  const { sessions, activeId, setActiveId, startNewChat, renameSession, deleteSession } =
    useSessionsContext();
  const { unreadSessionIds, runningSessionIds } = useChatRuntime();
  const { notify } = useToast();

  const isDesktop = useIsDesktop();
  const compact = collapsed && isDesktop;

  const [openGroups, setOpenGroups] = useState(loadOpenGroups);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  // Simpan status buka/tutup grup.
  useEffect(() => {
    try {
      localStorage.setItem(GROUPS_KEY, JSON.stringify(openGroups));
    } catch {
      // abaikan
    }
  }, [openGroups]);

  // Grup yang berisi halaman aktif otomatis terbuka.
  useEffect(() => {
    const group = NAV_GROUPS.find((g) => g.items.some((i) => i.id === active));
    if (!group) return;
    setOpenGroups((prev) => (prev[group.id] ? prev : { ...prev, [group.id]: true }));
  }, [active]);

  function toggleGroup(id) {
    setOpenGroups((prev) => ({ ...prev, [id]: !prev[id] }));
  }

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

  const hasUnread = unreadSessionIds.size > 0;

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[45] md:hidden"
          onClick={closeDrawer}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] transition-transform duration-200 ease-out
          md:static md:z-auto md:max-w-none md:translate-x-0 md:transition-[width] md:duration-200
          ${compact ? "md:w-[68px]" : "md:w-64"}
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          bg-surface border-r border-border flex flex-col h-full shrink-0 overflow-hidden`}
      >
        {/* Header / brand */}
        <div
          className={`shrink-0 h-14 flex items-center border-b border-border ${
            compact ? "justify-center" : "justify-between px-3"
          }`}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <BrandEmblem size={36} />
            {!compact && (
              <div className="min-w-0">
                <div className="text-sm font-semibold text-text-primary leading-tight truncate">
                  AIRA OS
                </div>
                <div className="text-[10px] uppercase tracking-wider text-text-secondary">
                  AI Operating System
                </div>
              </div>
            )}
          </div>

          {!compact && (
            <>
              <button
                type="button"
                onClick={onToggleCollapsed}
                title="Ciutkan sidebar (Ctrl+B)"
                aria-label="Ciutkan sidebar"
                className="hidden md:flex shrink-0 w-8 h-8 items-center justify-center rounded-control text-text-secondary hover:text-text-primary hover:bg-white/[0.06] transition"
              >
                <PanelLeftClose size={18} strokeWidth={1.9} />
              </button>
              <button
                type="button"
                onClick={closeDrawer}
                aria-label="Tutup menu"
                className="md:hidden shrink-0 w-8 h-8 flex items-center justify-center rounded-control text-text-secondary hover:text-text-primary hover:bg-white/[0.06] transition"
              >
                <X size={18} strokeWidth={1.9} />
              </button>
            </>
          )}
        </div>

        {compact && (
          <div className="shrink-0 flex justify-center pt-2">
            <button
              type="button"
              onClick={onToggleCollapsed}
              title="Perluas sidebar (Ctrl+B)"
              aria-label="Perluas sidebar"
              className="w-9 h-9 flex items-center justify-center rounded-control text-text-secondary hover:text-text-primary hover:bg-white/[0.06] transition"
            >
              <PanelLeftOpen size={18} strokeWidth={1.9} />
            </button>
          </div>
        )}

        {/* New chat */}
        <div className={`shrink-0 ${compact ? "py-2" : "px-3 py-3"}`}>
          <button
            type="button"
            onClick={handleNewChat}
            title="Chat baru"
            className={`flex items-center justify-center gap-2 h-10 bg-sakura-gradient text-white text-sm font-medium rounded-pill shadow-sakura-glow hover:brightness-110 transition ${
              compact ? "w-10 mx-auto" : "w-full"
            }`}
          >
            <Plus size={16} strokeWidth={2.4} />
            {!compact && "New Chat"}
          </button>
        </div>

        {/* Menu + percakapan (satu area scroll) */}
        <nav className="flex-1 min-h-0 overflow-y-auto px-2 pb-2">
          {NAV_GROUPS.map((group, index) => (
            <div key={group.id}>
              {compact ? (
                index > 0 && <div className="mx-3 my-2 border-t border-border/70" />
              ) : (
                <SectionHeader
                  label={group.label}
                  open={openGroups[group.id]}
                  onToggle={() => toggleGroup(group.id)}
                />
              )}

              <Collapsible open={compact || openGroups[group.id]}>
                <div className="space-y-0.5 pb-1">
                  {group.items.map((item) => (
                    <NavButton
                      key={item.id}
                      item={item}
                      active={active === item.id}
                      compact={compact}
                      dot={compact && item.id === "chat" && hasUnread}
                      onClick={() => goToNav(item.id)}
                    />
                  ))}
                </div>
              </Collapsible>
            </div>
          ))}

          {/* Percakapan (disembunyikan di mode compact) */}
          {!compact && (
            <div className="mt-1 pt-1 border-t border-border/70">
              <SectionHeader
                label="Percakapan"
                count={sessions.length}
                open={openGroups.sessions}
                onToggle={() => toggleGroup("sessions")}
              />

              <Collapsible open={openGroups.sessions}>
                <div className="space-y-1 pb-1">
                  {sessions.map((s) => {
                    const isRowActive = s.id === activeId && active === "chat";
                    const isEditing = editingId === s.id;
                    const isConfirming = confirmDeleteId === s.id;
                    const isUnread = unreadSessionIds.has(s.id);
                    const isRunning = runningSessionIds?.has(s.id);

                    return (
                      <div
                        key={s.id}
                        onClick={() => !isEditing && !isConfirming && handleSelectSession(s.id)}
                        className={`group rounded-control px-3 py-2 cursor-pointer text-sm transition
                          ${
                            isRowActive
                              ? "bg-white/[0.07] text-text-primary"
                              : "text-text-secondary hover:bg-white/[0.04] hover:text-text-primary"
                          }
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
                          <div
                            className="flex items-center justify-between gap-2"
                            onClick={(e) => e.stopPropagation()}
                          >
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
                              {isUnread && (
                                <span className="shrink-0 w-1.5 h-1.5 rounded-pill bg-sakura" />
                              )}
                              {isRunning && (
                                <span
                                  className="shrink-0 w-1.5 h-1.5 rounded-pill bg-cyan animate-pulse"
                                  title="Sedang diproses"
                                />
                              )}
                              <span className="truncate">{s.title}</span>
                            </span>

                            {/* Di layar sentuh selalu tampil; di desktop muncul saat hover */}
                            <div className="flex md:hidden md:group-hover:flex items-center gap-1 shrink-0">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  startEdit(s);
                                }}
                                title="Ganti judul"
                                className="text-text-secondary hover:text-text-primary"
                              >
                                <Pencil size={13} strokeWidth={1.9} />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteId(s.id);
                                }}
                                title="Hapus"
                                className="text-text-secondary hover:text-danger"
                              >
                                <Trash2 size={13} strokeWidth={1.9} />
                              </button>
                            </div>
                          </div>
                        )}

                        {!isEditing && !isConfirming && (
                          <div className="text-[10px] text-text-secondary/60 mt-0.5">
                            {timeAgo(s.updated_at)}
                          </div>
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
              </Collapsible>
            </div>
          )}
        </nav>

        {/* User panel */}
        <div className={`shrink-0 border-t border-border ${compact ? "p-2" : "p-3"}`}>
          <div
            className={`flex items-center gap-2.5 rounded-control bg-white/[0.04] ${
              compact ? "justify-center p-1.5" : "px-3 py-2"
            }`}
            title={compact ? "Lingga" : undefined}
          >
            <div className="w-8 h-8 rounded-pill bg-accent-gradient flex items-center justify-center text-xs font-semibold shrink-0">
              L
            </div>
            {!compact && (
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium text-text-primary truncate">Lingga</div>
                <div className="text-[10px] text-text-secondary truncate">AIRA Ecosystem</div>
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}