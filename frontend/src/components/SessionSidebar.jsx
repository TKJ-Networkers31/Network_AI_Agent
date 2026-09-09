import { useState } from "react";

function timeAgo(ts) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "baru saja";
  if (diff < 3600) return `${Math.floor(diff / 60)}m lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}j lalu`;
  return `${Math.floor(diff / 86400)}h lalu`;
}

export default function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  onRename,
  onDelete,
  isOpen,
  onClose,
}) {
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");

  function startEdit(session) {
    setEditingId(session.id);
    setEditValue(session.title);
  }

  function commitEdit(id) {
    const title = editValue.trim();
    if (title) onRename(id, title);
    setEditingId(null);
  }

  function handleSelect(id) {
    onSelect(id);
    onClose?.();
  }

  function handleNew() {
    onNew();
    onClose?.();
  }

  return (
    <>
      {/* Backdrop khusus mobile, muncul saat drawer terbuka */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={onClose}
        />
      )}

      <div
        className={`fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] transform transition-transform duration-200 ease-out
          md:static md:z-auto md:w-64 md:max-w-none md:translate-x-0 md:rounded-xl2 md:border
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          bg-panel border-r border-border flex flex-col overflow-hidden shrink-0`}
      >
        <div className="p-3 border-b border-border flex items-center gap-2">
          <button
            onClick={handleNew}
            className="flex-1 flex items-center justify-center gap-2 bg-accent-gradient text-white text-sm font-semibold py-2.5 rounded-lg"
          >
            + Chat Baru
          </button>
          <button
            onClick={onClose}
            className="md:hidden shrink-0 w-9 h-9 flex items-center justify-center rounded-lg border border-border text-white/60"
            aria-label="Tutup menu sesi"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
          {sessions.map((s) => {
            const isActive = s.id === activeId;
            const isEditing = editingId === s.id;

            return (
              <div
                key={s.id}
                onClick={() => !isEditing && handleSelect(s.id)}
                className={`group rounded-lg px-3 py-2.5 cursor-pointer text-sm transition
                  ${
                    isActive
                      ? "bg-white/10 text-white"
                      : "text-white/60 hover:bg-white/5 hover:text-white"
                  }`}
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
                ) : (
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate">{s.title}</span>
                    <div className="flex md:hidden md:group-hover:flex items-center gap-1 shrink-0">
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
                          if (window.confirm(`Hapus chat "${s.title}"?`)) {
                            onDelete(s.id);
                          }
                        }}
                        title="Hapus"
                        className="text-white/40 hover:text-red-400 text-xs"
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                )}

                {!isEditing && (
                  <div className="text-[10px] text-white/30 mt-0.5">
                    {timeAgo(s.updated_at)}
                  </div>
                )}
              </div>
            );
          })}

          {sessions.length === 0 && (
            <p className="text-white/30 text-xs px-3 py-4 text-center">
              Belum ada percakapan.
              <br />
              Mulai chat baru!
            </p>
          )}
        </div>
      </div>
    </>
  );
}