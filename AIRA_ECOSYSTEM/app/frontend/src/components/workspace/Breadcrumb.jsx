export default function Breadcrumb({ path, onNavigate }) {
  const segments = (path || "").split("/").filter(Boolean);

  return (
    <div className="flex items-center gap-1.5 text-sm text-white/60 min-w-0 overflow-x-auto">
      <button
        onClick={() => onNavigate("")}
        className="shrink-0 px-2 py-1 rounded-lg hover:bg-white/5 hover:text-white transition"
      >
        🏠 Home
      </button>

      {segments.map((seg, i) => {
        const segPath = segments.slice(0, i + 1).join("/");
        const isLast = i === segments.length - 1;

        return (
          <span key={segPath} className="flex items-center gap-1.5 shrink-0">
            <span className="text-white/25">/</span>
            <button
              onClick={() => onNavigate(segPath)}
              disabled={isLast}
              className={`px-2 py-1 rounded-lg transition ${
                isLast
                  ? "text-pink-300 font-medium"
                  : "hover:bg-white/5 hover:text-white"
              }`}
            >
              {seg}
            </button>
          </span>
        );
      })}
    </div>
  );
}