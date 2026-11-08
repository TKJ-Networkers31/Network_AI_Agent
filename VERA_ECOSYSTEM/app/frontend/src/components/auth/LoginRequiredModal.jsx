// src/components/auth/LoginRequiredModal.jsx
// AIRA OS — "Sign in to continue" Modal when authentication is required.
// Preserves draft user prompt in memory/session so after authentication it can be resumed seamlessly.

import { AlertCircle, CheckCircle2, Lock, Sparkles, UserPlus, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext.jsx";

export default function LoginRequiredModal() {
  const {
    isLoginRequiredModalOpen,
    setIsLoginRequiredModalOpen,
    loginRequiredReason,
    draftPrompt,
    openLogin,
    openRegister,
  } = useAuth();

  if (!isLoginRequiredModalOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-md rounded-2xl bg-neutral-900 border border-neutral-800 p-6 shadow-2xl">
        <button
          onClick={() => setIsLoginRequiredModalOpen(false)}
          className="absolute top-4 right-4 text-neutral-400 hover:text-white p-1 rounded-lg hover:bg-neutral-800 transition"
        >
          <X size={18} />
        </button>

        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-amber-500/20 to-sakura/20 border border-amber-500/30 flex items-center justify-center text-amber-400 mb-4">
          <Lock size={22} />
        </div>

        <h2 className="text-lg font-semibold text-white mb-1.5">Sign in to continue</h2>
        <p className="text-xs text-neutral-300 leading-relaxed mb-4">
          {loginRequiredReason ||
            "Akses memerlukan login ke akun resmi VERA Platform."}
        </p>

        {draftPrompt && (
          <div className="mb-4 p-3 rounded-xl bg-neutral-800/80 border border-neutral-700/60">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-cyan-400 mb-1">
              <CheckCircle2 size={13} />
              <span>Draf prompt Anda aman tersimpan</span>
            </div>
            <p className="text-xs text-neutral-300 italic line-clamp-2">
              &ldquo;{draftPrompt}&rdquo;
            </p>
          </div>
        )}

        <div className="space-y-2.5">
          <button
            type="button"
            onClick={openLogin}
            className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-sakura hover:from-cyan-400 hover:to-sakura text-xs font-semibold text-white shadow-lg shadow-cyan-500/10 flex items-center justify-center gap-2 transition"
          >
            <Sparkles size={14} />
            <span>Masuk ke Akun Saya</span>
          </button>

          <button
            type="button"
            onClick={openRegister}
            className="w-full py-2.5 px-4 rounded-xl bg-neutral-800 hover:bg-neutral-750 border border-neutral-700 text-xs font-medium text-neutral-200 hover:text-white flex items-center justify-center gap-2 transition"
          >
            <UserPlus size={14} />
            <span>Daftar Akun Baru</span>
          </button>
        </div>
      </div>
    </div>
  );
}
