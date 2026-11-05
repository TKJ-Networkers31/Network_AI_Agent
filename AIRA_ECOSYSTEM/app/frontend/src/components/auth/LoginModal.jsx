// src/components/auth/LoginModal.jsx
// AIRA OS — Client Site Login Modal

import { useState } from "react";
import { Lock, Mail, ShieldAlert, Sparkles, User, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext.jsx";
import { useToast } from "../Toast.jsx";

export default function LoginModal() {
  const { isLoginModalOpen, setIsLoginModalOpen, login, openRegister, continueAsGuest } = useAuth();
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
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
        notify({ type: "success", message: "Berhasil masuk ke AIRA Workspace!" });
        setIsLoginModalOpen(false);
      }
    } catch (err) {
      setErrorMessage(err.message || "Gagal masuk. Periksa kembali kredensial Anda.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGoogleOAuth() {
    try {
      const res = await fetch("/api/v1/auth/google/url");
      const data = await res.json();
      if (data.configured && data.url) {
        window.location.href = data.url;
      } else {
        notify({
          type: "warning",
          message: data.message || "Google OAuth belum dikonfigurasi pada environment server.",
        });
      }
    } catch (err) {
      notify({ type: "error", message: "Koneksi ke penyedia OAuth gagal." });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-md rounded-2xl bg-neutral-900 border border-neutral-800 p-6 shadow-2xl">
        <button
          onClick={() => setIsLoginModalOpen(false)}
          className="absolute top-4 right-4 text-neutral-400 hover:text-white p-1 rounded-lg hover:bg-neutral-800 transition"
        >
          <X size={18} />
        </button>

        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500/20 to-sakura/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Sparkles size={20} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Masuk ke AIRA OS</h2>
            <p className="text-xs text-neutral-400">AI-Native Network Engineer Workspace</p>
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
                value={usernameOrEmail}
                onChange={(e) => setUsernameOrEmail(e.target.value)}
                placeholder="nama_pengguna atau email@domain.com"
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
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <Lock size={14} className="absolute left-3 top-2.5 text-neutral-400" />
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
            className="w-full mt-2 py-2.5 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-sakura hover:from-cyan-400 hover:to-sakura text-xs font-semibold text-white shadow-md transition disabled:opacity-50"
          >
            {submitting ? "Memverifikasi..." : mfaRequired ? "Verifikasi 2FA & Masuk" : "Masuk ke Workspace"}
          </button>
        </form>

        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-neutral-800" />
          </div>
          <div className="relative flex justify-center text-[10px] uppercase">
            <span className="bg-neutral-900 px-2 text-neutral-500">atau lanjutkan dengan</span>
          </div>
        </div>

        <button
          type="button"
          onClick={handleGoogleOAuth}
          className="w-full py-2 px-3 rounded-lg bg-neutral-800/90 hover:bg-neutral-750 border border-neutral-700 flex items-center justify-center gap-2 text-xs text-neutral-200 hover:text-white transition"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
            />
          </svg>
          <span>Masuk dengan Google</span>
        </button>

        <div className="mt-4 pt-3 border-t border-neutral-800 flex items-center justify-between text-xs text-neutral-400">
          <button
            type="button"
            onClick={continueAsGuest}
            className="hover:text-cyan-400 transition"
          >
            Lanjut sebagai Guest
          </button>

          <button
            type="button"
            onClick={openRegister}
            className="text-cyan-400 hover:text-cyan-300 font-medium transition"
          >
            Daftar Akun Gratis &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}
