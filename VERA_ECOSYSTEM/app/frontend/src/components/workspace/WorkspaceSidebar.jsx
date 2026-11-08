const SECTIONS = [
  { id: "Projects", label: "Projects", icon: "📁" },
  { id: "Documents", label: "Documents", icon: "📄" },
  { id: "Images", label: "Images", icon: "🖼️" },
  { id: "Temp", label: "Temp", icon: "🗃️" },
  { id: "Trash", label: "Trash", icon: "🗑️" },
];

export default function WorkspaceSidebar({ active, onSelect }) {
  return (
    <aside className="w-full md:w-60 shrink-0 bg-card border border-border rounded-xl2 p-3 flex md:flex-col gap-1.5 overflow-x-auto md:overflow-visible">
      {SECTIONS.map((s) => {
        const isActive = active === s.id;
        return (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm whitespace-nowrap transition
              ${
                isActive
                  ? "bg-pink-500/10 text-pink-200 border border-pink-400/30"
                  : "text-white/60 hover:text-white hover:bg-white/5 border border-transparent"
              }`}
          >
            <span className={isActive ? "text-pink-300" : ""}>{s.icon}</span>
            <span className="font-medium">{s.label}</span>
          </button>
        );
      })}
    </aside>
  );
}