export default function SlashMenu({ tools, query, onPick }) {
  const filtered = tools.filter((t) =>
    t.name.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="absolute bottom-full mb-2 left-0 right-0 bg-card border border-border rounded-xl2 shadow-xl max-h-64 overflow-y-auto z-10">
      {filtered.length === 0 && (
        <div className="px-4 py-3 text-xs text-white/40">
          Tidak ada tool bernama "/{query}"
        </div>
      )}

      {filtered.map((t) => (
        <button
          key={t.name}
          type="button"
          onClick={() => onPick(t.name)}
          className="w-full text-left px-4 py-2.5 hover:bg-white/5 border-b border-border/50 last:border-b-0 flex items-start gap-3"
        >
          <span className="text-accent-light font-mono text-sm shrink-0">
            /{t.name}
          </span>
          <span className="text-white/50 text-xs mt-0.5 line-clamp-1">
            {t.description || t.category}
          </span>
        </button>
      ))}
    </div>
  );
}
