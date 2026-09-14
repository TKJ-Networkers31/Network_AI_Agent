import { formatBytes, formatDate } from "./FileRow.jsx";

function resolvePermission(path, rules) {
  if (!rules) return "Read & Write";

  const target = (path || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  let match = null;

  for (const folder of Object.keys(rules)) {
    const key = folder === "/" ? "" : folder;
    if (target === key || target.startsWith(`${key}/`) || key === "") {
      if (match === null || key.length > match.length) match = key;
    }
  }

  if (match === null) return "Read & Write";

  const level = rules[match === "" ? "/" : match];
  return level === "READ_ONLY" ? "Read Only" : level === "DENY" ? "Denied" : "Read & Write";
}

export default function PropertyPanel({ entry, permissionRules, onClose, onRename, onMove, onDelete }) {
  if (!entry) return null;

  const permission = resolvePermission(entry.path, permissionRules);

  return (
    <aside className="w-full md:w-72 shrink-0 bg-card border border-border rounded-xl2 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-white text-sm">Properties</h3>
        <button onClick={onClose} className="text-white/40 hover:text-white text-xs">
          ✕
        </button>
      </div>

      <div className="flex flex-col items-center gap-2 py-3 border-b border-border">
        <span className="text-4xl">{entry.is_dir ? "📁" : "📄"}</span>
        <span className="text-sm text-white/90 text-center break-all">{entry.name}</span>
      </div>

      <dl className="text-xs space-y-2">
        <div className="flex justify-between gap-2">
          <dt className="text-white/40">Path</dt>
          <dd className="text-white/80 text-right break-all">{entry.path || "/"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/40">Size</dt>
          <dd className="text-white/80">{entry.is_dir ? "—" : formatBytes(entry.size)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/40">Modified</dt>
          <dd className="text-white/80">{formatDate(entry.modified_at)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/40">Created</dt>
          <dd className="text-white/40">—</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/40">Checksum</dt>
          <dd className="text-white/40">—</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/40">Permission</dt>
          <dd className="text-pink-200">{permission}</dd>
        </div>
      </dl>

      <div className="flex flex-col gap-1.5 pt-2 border-t border-border">
        <button
          onClick={() => onRename(entry)}
          className="text-xs px-3 py-2 rounded-lg bg-white/5 text-white/70 hover:text-white hover:bg-white/10 transition text-left"
        >
          ✏️ Rename
        </button>
        <button
          onClick={() => onMove(entry)}
          className="text-xs px-3 py-2 rounded-lg bg-white/5 text-white/70 hover:text-white hover:bg-white/10 transition text-left"
        >
          📦 Move
        </button>
        <button
          onClick={() => onDelete(entry)}
          className="text-xs px-3 py-2 rounded-lg bg-red-500/10 text-red-300 hover:bg-red-500/20 transition text-left"
        >
          🗑 Delete
        </button>
      </div>
    </aside>
  );
}