import { createContext, useCallback, useContext, useRef, useState } from "react";
import { AlertTriangle, CheckCircle, Info, X } from "lucide-react";

const ModalDialogContext = createContext(null);

export function ModalDialogProvider({ children }) {
  const [dialog, setDialog] = useState(null);
  const resolverRef = useRef(null);
  const inputRef = useRef(null);

  const closeDialog = useCallback((result) => {
    setDialog(null);
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
  }, []);

  const alert = useCallback((options) => {
    return new Promise((resolve) => {
      resolverRef.current = () => resolve();
      const opts = typeof options === "string" ? { message: options } : options || {};
      setDialog({
        mode: "alert",
        title: opts.title || "Pemberitahuan",
        message: opts.message || "",
        confirmText: opts.confirmText || "OK",
        type: opts.type || "info",
        isDestructive: Boolean(opts.isDestructive),
      });
    });
  }, []);

  const confirm = useCallback((options) => {
    return new Promise((resolve) => {
      resolverRef.current = (val) => resolve(Boolean(val));
      const opts = typeof options === "string" ? { message: options } : options || {};
      setDialog({
        mode: "confirm",
        title: opts.title || "Konfirmasi Tindakan",
        message: opts.message || "",
        confirmText: opts.confirmText || "Lanjutkan",
        cancelText: opts.cancelText || "Batal",
        type: opts.type || (opts.isDestructive ? "danger" : "warning"),
        isDestructive: Boolean(opts.isDestructive),
      });
    });
  }, []);

  const prompt = useCallback((options, defaultVal = "") => {
    return new Promise((resolve) => {
      resolverRef.current = (val) => resolve(val !== null ? String(val) : null);
      const opts = typeof options === "string" ? { message: options, defaultValue: defaultVal } : options || {};
      setDialog({
        mode: "prompt",
        title: opts.title || "Input Diperlukan",
        message: opts.message || "",
        placeholder: opts.placeholder || "",
        defaultValue: opts.defaultValue || defaultVal || "",
        confirmText: opts.confirmText || "Simpan",
        cancelText: opts.cancelText || "Batal",
        type: opts.type || "info",
        inputValue: opts.defaultValue || defaultVal || "",
      });
    });
  }, []);

  return (
    <ModalDialogContext.Provider value={{ alert, confirm, prompt }}>
      {children}

      {dialog && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn"
          onKeyDown={(e) => {
            if (e.key === "Escape") closeDialog(dialog.mode === "prompt" ? null : false);
          }}
        >
          <div className="relative w-full max-w-md rounded-2xl border border-white/10 bg-neutral-900/95 p-6 shadow-[0_0_40px_rgba(0,0,0,0.8)] space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                    dialog.isDestructive || dialog.type === "danger"
                      ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                      : dialog.type === "warning"
                      ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                      : dialog.type === "success"
                      ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                      : "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                  }`}
                >
                  {dialog.isDestructive || dialog.type === "danger" || dialog.type === "warning" ? (
                    <AlertTriangle className="h-5 w-5" />
                  ) : dialog.type === "success" ? (
                    <CheckCircle className="h-5 w-5" />
                  ) : (
                    <Info className="h-5 w-5" />
                  )}
                </div>
                <h3 className="text-base font-semibold text-white tracking-wide">{dialog.title}</h3>
              </div>
              <button
                type="button"
                onClick={() => closeDialog(dialog.mode === "prompt" ? null : false)}
                className="text-neutral-400 hover:text-white transition p-1 rounded-lg hover:bg-white/5"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {dialog.message && (
              <p className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap">
                {dialog.message}
              </p>
            )}

            {dialog.mode === "prompt" && (
              <div className="pt-1">
                <input
                  ref={inputRef}
                  autoFocus
                  type="text"
                  defaultValue={dialog.defaultValue}
                  placeholder={dialog.placeholder}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/40 transition"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      closeDialog(e.currentTarget.value);
                    }
                  }}
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2.5 pt-2">
              {dialog.mode !== "alert" && (
                <button
                  type="button"
                  onClick={() => closeDialog(dialog.mode === "prompt" ? null : false)}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-medium text-neutral-300 hover:bg-white/10 hover:text-white transition"
                >
                  {dialog.cancelText || "Batal"}
                </button>
              )}
              <button
                type="button"
                autoFocus={dialog.mode !== "prompt"}
                onClick={() => {
                  if (dialog.mode === "prompt") {
                    closeDialog(inputRef.current ? inputRef.current.value : dialog.defaultValue);
                  } else {
                    closeDialog(true);
                  }
                }}
                className={`rounded-xl px-4 py-2 text-xs font-semibold text-white shadow-lg transition active:scale-95 ${
                  dialog.isDestructive || dialog.type === "danger"
                    ? "bg-rose-600 hover:bg-rose-500 shadow-rose-600/30"
                    : "bg-cyan-600 hover:bg-cyan-500 shadow-cyan-600/30"
                }`}
              >
                {dialog.confirmText || "OK"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ModalDialogContext.Provider>
  );
}

export function useModalDialog() {
  const ctx = useContext(ModalDialogContext);
  if (!ctx) {
    // Graceful fallback if invoked outside provider
    return {
      alert: (opts) => window.alert(typeof opts === "string" ? opts : opts?.message),
      confirm: (opts) => Promise.resolve(window.confirm(typeof opts === "string" ? opts : opts?.message)),
      prompt: (opts, def) => Promise.resolve(window.prompt(typeof opts === "string" ? opts : opts?.message, def)),
    };
  }
  return ctx;
}
