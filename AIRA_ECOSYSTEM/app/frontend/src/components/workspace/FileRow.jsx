function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatDate(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function icon(entry) {
  return entry.is_dir ? "📁" : "📄";
}

export default function FileRow({ entry, isGrid, isSelected, onSelect, onOpen, onContextMenu }) {
  if (isGrid) {
    return (
      <button
        onClick={() => onSelect(entry)}
        onDoubleClick={() => onOpen(entry)}
        onContextMenu={(e) => {
          e.preventDefault();
          onContextMenu(e, entry);
        }}
        className={`flex flex-col items-center gap-2 p-3 rounded-xl2 border transition text-center
          ${
            isSelected
              ? "bg-pink-500/10 border-pink-400/40"
              : "bg-white/5 border-transparent hover:border-border hover:bg-white/[0.07]"
          }`}
      >
        <span className="text-3xl">{icon(entry)}</span>
        <span className="text-xs text-white/80 truncate w-full">{entry.name}</span>
      </button>
    );
  }

  return (
    <div
      onClick={() => onSelect(entry)}
      onDoubleClick={() => onOpen(entry)}
      onContextMenu={(e) => {
        e.preventDefault();
        onContextMenu(e, entry);
      }}
      className={`grid grid-cols-[1fr_100px_160px] items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer text-sm transition
        ${isSelected ? "bg-pink-500/10" : "hover:bg-white/5"}`}
    >
      <span className="flex items-center gap-2 min-w-0 text-white/85">
        <span>{icon(entry)}</span>
        <span className="truncate">{entry.name}</span>
      </span>
      <span className="text-white/40 text-xs">{entry.is_dir ? "—" : formatBytes(entry.size)}</span>
      <span className="text-white/40 text-xs">{formatDate(entry.modified_at)}</span>
    </div>
  );
}

export { formatBytes, formatDate };