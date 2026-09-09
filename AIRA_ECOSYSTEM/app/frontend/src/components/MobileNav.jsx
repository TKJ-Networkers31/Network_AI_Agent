const NAV_ITEMS = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "devices", label: "Devices", icon: "🖧" },
  { id: "memory", label: "Memory", icon: "🧠" },
  { id: "settings", label: "Settings", icon: "⚙️" },
];

export default function MobileNav({ active, onChange }) {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-panel/95 backdrop-blur border-t border-border pb-[env(safe-area-inset-bottom)]">
      <div className="flex items-stretch justify-around">
        {NAV_ITEMS.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2.5 text-[10px] font-medium transition
                ${isActive ? "text-accent-light" : "text-white/40"}`}
            >
              <span className={`text-lg transition-transform ${isActive ? "scale-110" : ""}`}>
                {item.icon}
              </span>
              <span>{item.label}</span>
              {isActive && (
                <span className="w-1 h-1 rounded-full bg-accent-light mt-0.5" />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}