const NAV_ITEMS = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "devices", label: "Devices", icon: "🖧" },
  { id: "memory", label: "Memory", icon: "🧠" },
  { id: "settings", label: "Settings", icon: "⚙️" },
];

export default function Sidebar({ active, onChange }) {
  return (
    <aside className="w-64 shrink-0 bg-panel border-r border-border flex flex-col">
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-accent-gradient flex items-center justify-center text-sm font-bold">
            AI
          </div>
          <div>
            <div className="font-semibold text-white leading-tight">
              Network Agent
            </div>
            <div className="text-[10px] uppercase tracking-wide text-white/40">
              AI Assistant
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition
                ${
                  isActive
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

      <div className="px-5 py-4 border-t border-border text-[11px] text-white/30">
        Network AI Agent · Web UI
      </div>
    </aside>
  );
}
