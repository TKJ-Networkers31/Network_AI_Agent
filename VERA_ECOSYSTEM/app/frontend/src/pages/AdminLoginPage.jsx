// src/pages/AdminLoginPage.jsx
// AIRA OS — Admin Site / Control Plane Dedicated Login View

import { useState } from "react";
import { ArrowLeft, Lock, ShieldCheck, ShieldAlert, Sparkles, User } from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "../components/Toast.jsx";

export default function AdminLoginPage({ onBackToWorkspace }) {
  const { login } = useAuth();
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
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
        adminOnly: true,
      });

      if (res?.mfa_required) {
        setMfaRequired(true);
        notify({ type: "info", message: "Masukkan 6-digit kode verifikasi 2FA (TOTP) administrator." });
      } else {
        notify({ type: "success", message: "Otorisasi Control Plane berhasil." });
      }
    } catch (err) {
      setErrorMessage(
        err.message || "Akses ditolak: Kredensial tidak valid atau akun tidak memiliki hak akses administrator."
      );
    } finally {
      setSubmitting(false);
    }
  }

  function handleBack() {
    if (typeof onBackToWorkspace === "function") {
      onBackToWorkspace();
    } else {
      window.dispatchEvent(new CustomEvent("aira:navigate", { detail: "workspace" }));
    }
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4 min-h-[80vh]">
      <div className="w-full max-w-md rounded-2xl bg-neutral-900/90 border border-neutral-800 p-8 shadow-2xl relative">
        <button
          onClick={handleBack}
          className="absolute top-5 left-5 flex items-center gap-1.5 text-xs text-neutral-400 hover:text-white transition"
        >
          <ArrowLeft size={14} />
          <span>Ke Workspace</span>
        </button>

        <div className="flex flex-col items-center text-center mt-4 mb-6">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-vera-cyan/20 to-vera-blue/20 border border-vera-cyan/30 flex items-center justify-center text-vera-cyan mb-3 shadow-lg">
            <ShieldCheck size={24} />
          </div>
          <h1 className="text-lg font-bold text-white tracking-wide">VERA Control Plane</h1>
          <p className="text-xs text-text-secondary mt-1">
            Platform Administration & Infrastructure Governance
          </p>
        </div>

        {errorMessage && (
          <div className="mb-5 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-start gap-2.5 text-xs text-rose-300">
            <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-400" />
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-neutral-300 mb-1">
              Admin Username / Email
            </label>
            <div className="relative">
              <input
                type="text"
                required
                value={usernameOrEmail}
                onChange={(e) => setUsernameOrEmail(e.target.value)}
                placeholder="mis. lingga_admin"
                className="w-full pl-9 pr-3 py-2.5 text-xs rounded-xl bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <User size={15} className="absolute left-3 top-3 text-neutral-400" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-300 mb-1">
              Admin Password
            </label>
            <div className="relative">
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full pl-9 pr-3 py-2.5 text-xs rounded-xl bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <Lock size={15} className="absolute left-3 top-3 text-neutral-400" />
            </div>
          </div>

          {mfaRequired && (
            <div className="pt-1">
              <label className="block text-xs font-medium text-cyan-300 mb-1">
                Security Token / TOTP Code
              </label>
              <input
                type="text"
                required
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                placeholder="000000"
                className="w-full px-3 py-2.5 text-center tracking-widest text-sm font-mono rounded-xl bg-neutral-800 border border-cyan-500/50 text-cyan-200 focus:outline-none focus:border-cyan-400"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full mt-2 py-3 px-4 rounded-xl bg-gradient-to-r from-cyan-600 to-sakura hover:from-cyan-500 hover:to-sakura text-xs font-semibold text-white shadow-lg shadow-cyan-600/20 transition disabled:opacity-50"
          >
            {submitting ? "Mengautentikasi..." : "Buka Control Plane"}
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-neutral-800/80 text-center">
          <p className="text-[11px] text-neutral-500">
            Akses ke sistem ini dibatasi untuk staf operasi berwenang. Semua aktivitas diaudit secara kriptografis.
          </p>
        </div>
      </div>
    </div>
  );
}
