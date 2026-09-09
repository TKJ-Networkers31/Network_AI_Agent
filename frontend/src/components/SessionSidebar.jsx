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

  return (
    <div className="w-64 shrink-0 bg-panel border border-border rounded-xl2 flex flex-col overflow-hidden">
      <div className="p-3 border-b border-border">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 bg-accent-gradient text-white text-sm font-semibold py-2.5 rounded-lg"
        >
          + Chat Baru
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        {sessions.map((s) => {
          const isActive = s.id === activeId;
          const isEditing = editingId === s.id;

          return (
            <div
              key={s.id}
              onClick={() => !isEditing && onSelect(s.id)}
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
  );
}
