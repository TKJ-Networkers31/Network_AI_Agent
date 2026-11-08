import { useEffect, useRef } from "react";

export default function ContextMenu({ x, y, items, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    function handleKey(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [onClose]);

  const clampedX = Math.min(x, window.innerWidth - 180);
  const clampedY = Math.min(y, window.innerHeight - items.length * 36 - 16);

  return (
    <div
      ref={ref}
      style={{ left: clampedX, top: clampedY }}
      className="fixed z-[200] w-44 bg-panel border border-border rounded-xl2 shadow-2xl shadow-black/40 py-1.5 overflow-hidden"
    >
      {items.map((item, i) => (
        <button
          key={i}
          onClick={() => {
            item.onClick();
            onClose();
          }}
          className={`w-full text-left px-3.5 py-2 text-sm transition flex items-center gap-2
            ${item.danger ? "text-red-300 hover:bg-red-500/10" : "text-white/80 hover:bg-white/5 hover:text-white"}`}
        >
          {item.icon && <span>{item.icon}</span>}
          {item.label}
        </button>
      ))}
    </div>
  );
}