// src/components/auth/LoginModal.jsx
// AIRA OS — Client Site Login Modal (Phase F.1)
// Username and Password only. Zero Sign Up, Zero Guest Access, Zero OAuth.

import { useState } from "react";
import { Eye, EyeOff, Lock, ShieldAlert, Sparkles, User, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext.jsx";
import { useToast } from "../Toast.jsx";

export default function LoginModal() {
  const { isLoginModalOpen, setIsLoginModalOpen, login } = useAuth();
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [totpCode, setTotpCode] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const { notify } = useToast();

  if (!isLoginModalOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMessage("");
    setSubmitting(true);

    try {
      const res = await login({
        usernameOrEmail: usernameOrEmail.trim(),
        password,
        totpCode: mfaRequired ? totpCode.trim() : null,
        adminOnly: false,
      });

      if (res?.mfa_required) {
        setMfaRequired(true);
        notify({ type: "info", message: "Masukkan kode 2FA (TOTP) dari aplikasi authenticator Anda." });
      } else {
        notify({ type: "success", message: "Berhasil masuk ke VERA Workspace!" });
        setIsLoginModalOpen(false);
      }
    } catch (err) {
      setErrorMessage(err.message || "Gagal masuk. Periksa kembali kredensial Anda.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-md rounded-2xl bg-neutral-900 border border-neutral-800 p-6 shadow-2xl">
        <button
          onClick={() => setIsLoginModalOpen(false)}
          className="absolute top-4 right-4 text-neutral-400 hover:text-white p-1 rounded-lg hover:bg-neutral-800 transition"
          aria-label="Tutup"
        >
          <X size={18} />
        </button>

        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500/20 to-sakura/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Sparkles size={20} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Masuk ke VERA</h2>
            <p className="text-xs text-neutral-400">Enterprise Network Intelligence Platform</p>
          </div>
        </div>

        {errorMessage && (
          <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-start gap-2.5 text-xs text-rose-300">
            <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-400" />
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block text-xs font-medium text-neutral-300 mb-1">
              Username atau Email
            </label>
            <div className="relative">
              <input
                type="text"
                required
                autoFocus
                autoComplete="username"
                value={usernameOrEmail}
                onChange={(e) => setUsernameOrEmail(e.target.value)}
                placeholder="mis. lingga_admin"
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <User size={14} className="absolute left-3 top-2.5 text-neutral-400" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-300 mb-1">
              Kata Sandi
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-10 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <Lock size={14} className="absolute left-3 top-2.5 text-neutral-400" />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="absolute right-3 top-2.5 text-neutral-400 hover:text-white transition"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {mfaRequired && (
            <div className="pt-1">
              <label className="block text-xs font-medium text-cyan-300 mb-1">
                Kode Autentikasi 2FA (TOTP)
              </label>
              <input
                type="text"
                required
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                placeholder="000000"
                className="w-full px-3 py-2 text-center tracking-widest text-sm font-mono rounded-lg bg-neutral-800 border border-cyan-500/50 text-cyan-200 focus:outline-none focus:border-cyan-400"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full mt-2 py-2.5 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-sakura hover:from-cyan-400 hover:to-sakura text-xs font-semibold text-white shadow-md transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {submitting ? (
              <>
                <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Memverifikasi...</span>
              </>
            ) : mfaRequired ? (
              "Verifikasi 2FA & Masuk"
            ) : (
              "Masuk ke Workspace"
            )}
          </button>
        </form>

        <div className="mt-4 pt-3 border-t border-neutral-800 text-center">
          <p className="text-[11px] text-neutral-400 leading-relaxed">
            Seluruh akun dan hak akses dikelola oleh administrator (<span className="text-cyan-400 font-mono">lingga_admin</span>).
            Hubungi administrator jika Anda memerlukan akun baru.
          </p>
        </div>
      </div>
    </div>
  );
}
