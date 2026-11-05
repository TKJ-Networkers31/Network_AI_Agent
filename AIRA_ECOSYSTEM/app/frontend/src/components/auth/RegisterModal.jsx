// src/components/auth/RegisterModal.jsx
// AIRA OS — User Registration Modal (provisions Free plan by default)

import { useState } from "react";
import { Building, Lock, Mail, ShieldAlert, Sparkles, User, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext.jsx";
import { useToast } from "../Toast.jsx";

export default function RegisterModal() {
  const { isRegisterModalOpen, setIsRegisterModalOpen, register, openLogin, continueAsGuest } = useAuth();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const { notify } = useToast();

  if (!isRegisterModalOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMessage("");

    if (password.length < 8) {
      setErrorMessage("Kata sandi minimal 8 karakter.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMessage("Konfirmasi kata sandi tidak cocok.");
      return;
    }

    setSubmitting(true);
    try {
      await register({
        username: username.trim(),
        email: email.trim(),
        password,
        organizationName: orgName.trim() || null,
      });

      notify({
        type: "success",
        message: "Pendaftaran berhasil! Akun Anda aktif dengan paket Free (100.000 token/bln).",
      });
      setIsRegisterModalOpen(false);
    } catch (err) {
      setErrorMessage(err.message || "Pendaftaran gagal. Periksa data Anda.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-md rounded-2xl bg-neutral-900 border border-neutral-800 p-6 shadow-2xl">
        <button
          onClick={() => setIsRegisterModalOpen(false)}
          className="absolute top-4 right-4 text-neutral-400 hover:text-white p-1 rounded-lg hover:bg-neutral-800 transition"
        >
          <X size={18} />
        </button>

        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500/20 to-sakura/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Sparkles size={20} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Buat Akun AIRA OS</h2>
            <p className="text-xs text-neutral-400">Dapatkan kuota 100.000 token bulanan gratis</p>
          </div>
        </div>

        {errorMessage && (
          <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-start gap-2.5 text-xs text-rose-300">
            <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-400" />
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-neutral-300 mb-1">
              Username
            </label>
            <div className="relative">
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="nama_engineer"
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <User size={14} className="absolute left-3 top-2.5 text-neutral-400" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-300 mb-1">
              Email
            </label>
            <div className="relative">
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="engineer@company.com"
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <Mail size={14} className="absolute left-3 top-2.5 text-neutral-400" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-300 mb-1">
              Nama Organisasi / Jaringan (Opsional)
            </label>
            <div className="relative">
              <input
                type="text"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="mis. PT Solusi Jaringan Nusantara"
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <Building size={14} className="absolute left-3 top-2.5 text-neutral-400" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
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
                  placeholder="Min 8 char"
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
                />
                <Lock size={14} className="absolute left-3 top-2.5 text-neutral-400" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-neutral-300 mb-1">
                Konfirmasi
              </label>
              <div className="relative">
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Ulangi"
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 transition"
                />
                <Lock size={14} className="absolute left-3 top-2.5 text-neutral-400" />
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full mt-3 py-2.5 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-sakura hover:from-cyan-400 hover:to-sakura text-xs font-semibold text-white shadow-md transition disabled:opacity-50"
          >
            {submitting ? "Mendaftarkan..." : "Daftar & Masuk Workspace"}
          </button>
        </form>

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
            onClick={openLogin}
            className="text-cyan-400 hover:text-cyan-300 font-medium transition"
          >
            Sudah punya akun? Masuk &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}
