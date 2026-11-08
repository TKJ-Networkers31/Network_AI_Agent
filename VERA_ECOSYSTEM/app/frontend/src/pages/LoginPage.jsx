// src/pages/LoginPage.jsx
// AIRA OS — Enterprise-Grade Dedicated Authentication Page (Phase F.1)
// Username and Password only. Zero Sign Up, Zero Guest Access, Zero OAuth.
// Centralized Identity Managed by Root Administrator (lingga_admin).

import { useState } from "react";
import { Eye, EyeOff, Lock, ShieldAlert, Sparkles, User } from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "../components/Toast.jsx";

export default function LoginPage() {
  const { login } = useAuth();
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [totpCode, setTotpCode] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const { notify } = useToast();

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
        notify({
          type: "info",
          message: "Masukkan 6-digit kode verifikasi 2FA (TOTP) dari aplikasi authenticator Anda.",
        });
      } else {
        notify({
          type: "success",
          message: `Selamat datang kembali, ${res?.user?.display_name || res?.user?.username || "Engineer"}!`,
        });
      }
    } catch (err) {
      setErrorMessage(err.message || "Gagal masuk. Periksa kembali username dan kata sandi Anda.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen w-screen flex flex-col items-center justify-center p-4 bg-app text-white select-none relative overflow-hidden">
      {/* Background ambient lighting */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-[400px] h-[400px] bg-sakura/10 rounded-full blur-[140px] pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-vera-cyan/20 to-vera-blue/20 border border-vera-cyan/30 flex items-center justify-center text-vera-cyan mb-4 shadow-xl shadow-vera-cyan/10">
            <Sparkles size={28} />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>VERA</span>
            <span className="text-[10px] font-mono tracking-widest uppercase px-2 py-0.5 rounded-full bg-vera-cyan/10 border border-vera-cyan/30 text-vera-cyan font-medium">
              ENTERPRISE
            </span>
          </h1>
          <p className="text-xs text-text-secondary mt-1">
            Enterprise Network Intelligence Platform · Understand. Monitor. Automate.
          </p>
        </div>

        {/* Login Card */}
        <div className="rounded-2xl bg-neutral-900/90 border border-neutral-800/90 backdrop-blur-xl p-7 shadow-2xl">
          <div className="mb-5 pb-4 border-b border-white/[0.06]">
            <h2 className="text-sm font-semibold text-white">Masuk ke Workspace</h2>
            <p className="text-[11px] text-neutral-400 mt-0.5">
              Gunakan kredensial yang telah didaftarkan oleh administrator sistem.
            </p>
          </div>

          {errorMessage && (
            <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-start gap-2.5 text-xs text-rose-300 animate-in fade-in duration-200">
              <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-400" />
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-neutral-300 mb-1.5">
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
                  className="w-full pl-9 pr-3 py-2.5 text-xs rounded-xl bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/40 transition"
                />
                <User size={15} className="absolute left-3 top-3 text-neutral-400" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-neutral-300 mb-1.5">
                Kata Sandi
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full pl-9 pr-10 py-2.5 text-xs rounded-xl bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/40 transition"
                />
                <Lock size={15} className="absolute left-3 top-3 text-neutral-400" />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="absolute right-3 top-2.5 text-neutral-400 hover:text-white transition p-0.5"
                  tabIndex={-1}
                  aria-label="Toggle password visibility"
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {mfaRequired && (
              <div className="pt-2 animate-in fade-in duration-200">
                <label className="block text-xs font-medium text-cyan-300 mb-1.5">
                  Kode Autentikasi 2FA (TOTP)
                </label>
                <input
                  type="text"
                  required
                  maxLength={6}
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  className="w-full px-3 py-2.5 text-center tracking-widest text-base font-mono rounded-xl bg-neutral-800/90 border border-cyan-500/50 text-cyan-200 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition"
                />
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full mt-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-sakura hover:from-cyan-400 hover:to-sakura text-xs font-semibold text-white shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/30 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Memverifikasi kredensial...</span>
                </>
              ) : mfaRequired ? (
                "Verifikasi 2FA & Masuk"
              ) : (
                "Masuk ke Sistem"
              )}
            </button>
          </form>

          {/* Centralized Policy Notice */}
          <div className="mt-6 pt-4 border-t border-white/[0.06] text-center">
            <p className="text-[11px] text-neutral-400 leading-relaxed">
              Autentikasi terkelola secara terpusat oleh root administrator (<span className="text-cyan-400 font-mono">lingga_admin</span>).
              Pembuatan akun baru dan pengaturan hak akses grup dikonfigurasi melalui panel admin.
            </p>
          </div>
        </div>

        {/* Footer info */}
        <p className="text-center text-[11px] text-neutral-400 mt-4">
          Sesi aktif tersimpan secara aman pada perangkat ini.
        </p>
      </div>
    </div>
  );
}
