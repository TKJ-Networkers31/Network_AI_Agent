import { createContext, useCallback, useContext, useState } from "react";

const ToastContext = createContext(null);

const STYLES = {
  info: {
    border: "border-accent/40",
    bg: "bg-accent/10",
    text: "text-accent-light",
    icon: "ℹ",
  },
  success: {
    border: "border-emerald-500/40",
    bg: "bg-emerald-500/10",
    text: "text-emerald-300",
    icon: "✓",
  },
  error: {
    border: "border-red-500/40",
    bg: "bg-red-500/10",
    text: "text-red-300",
    icon: "!",
  },
  warning: {
    border: "border-amber-500/40",
    bg: "bg-amber-500/10",
    text: "text-amber-300",
    icon: "◆",
  },
};

let fallbackId = 0;

function makeId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  fallbackId += 1;
  return `toast-${fallbackId}`;
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const notify = useCallback(
    ({ type = "info", message, duration = 4000 }) => {
      if (!message) return null;

      const id = makeId();

      setToasts((prev) => [...prev, { id, type, message }]);

      if (duration) {
        setTimeout(() => dismiss(id), duration);
      }

      return id;
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={{ notify, dismiss }}>
      {children}

      <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-[calc(100%-2rem)] max-w-sm pointer-events-none">
        {toasts.map((t) => {
          const style = STYLES[t.type] || STYLES.info;

          return (
            <div
              key={t.id}
              className={`toast-in pointer-events-auto flex items-start gap-3 rounded-xl2 border ${style.border} ${style.bg} backdrop-blur-md px-4 py-3 shadow-lg shadow-black/30`}
            >
              <span
                className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold border ${style.border} ${style.text}`}
              >
                {style.icon}
              </span>
              <p className={`text-sm leading-snug ${style.text} flex-1`}>
                {t.message}
              </p>
              <button
                onClick={() => dismiss(t.id)}
                className="text-white/30 hover:text-white/70 text-xs leading-none mt-0.5 shrink-0"
                aria-label="Tutup notifikasi"
              >
                ✕
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
