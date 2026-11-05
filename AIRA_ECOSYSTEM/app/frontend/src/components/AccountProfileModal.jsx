// src/components/AccountProfileModal.jsx
// AIRA OS — User Profile, Security, MikroTik Group RBAC & Preferences Modal (Phase F.1)

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Key,
  Layers,
  Lock,
  LogOut,
  RefreshCw,
  Shield,
  ShieldCheck,
  Sliders,
  User,
  X,
  Zap,
} from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "./Toast.jsx";
import { getAuthHeaders } from "../api.js";

export default function AccountProfileModal({ isOpen, onClose }) {
  const { user: authUser, logout } = useAuth();
  const [activeTab, setActiveTab] = useState("profile");
  const [userProfile, setUserProfile] = useState(null);
  const [loading, setLoading] = useState(false);

  // Security state
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  const { notify } = useToast();

  useEffect(() => {
    if (isOpen) {
      loadProfile();
    }
  }, [isOpen]);

  async function loadProfile() {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const res = await fetch("/api/v1/auth/me", { headers });
      const data = await res.json();
      if (data.success) {
        setUserProfile(data);
      }
    } catch (err) {
      console.warn("Failed to load user profile:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    if (newPassword.length < 6) {
      notify({ type: "error", message: "Kata sandi baru minimal 6 karakter." });
      return;
    }
    if (newPassword !== confirmPassword) {
      notify({ type: "error", message: "Konfirmasi kata sandi tidak cocok." });
      return;
    }

    setSavingPassword(true);
    try {
      const res = await fetch("/api/v1/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ new_password: newPassword }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        notify({ type: "success", message: "Kata sandi berhasil diperbarui." });
        setNewPassword("");
        setConfirmPassword("");
      } else {
        notify({ type: "error", message: data.detail || data.message || "Gagal mengubah kata sandi." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingPassword(false);
    }
  }

  if (!isOpen) return null;

  const user = userProfile?.user || authUser;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-rose-500 flex items-center justify-center font-bold text-white shadow-lg">
              {user ? user.username.charAt(0).toUpperCase() : "U"}
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white leading-tight">
                {user?.display_name || user?.username || "Pengguna"}
              </h2>
              <p className="text-xs text-neutral-400">
                @{user?.username} &bull; {user?.email || "Akun Terverifikasi"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-neutral-400 hover:text-white hover:bg-white/10 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-white/10 bg-black/20 px-6 gap-2 text-xs">
          {[
            { id: "profile", label: "Profile", icon: User },
            { id: "security", label: "Account Security", icon: ShieldCheck },
            { id: "preferences", label: "Preferences", icon: Sliders },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 py-3 px-3 font-medium border-b-2 transition ${
                  active
                    ? "border-cyan-400 text-cyan-300 bg-cyan-500/5"
                    : "border-transparent text-neutral-400 hover:text-neutral-200"
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6 text-xs">
          {/* 1. PROFILE TAB */}
          {activeTab === "profile" && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5">
                  <div className="text-[11px] text-neutral-400">User ID</div>
                  <div className="text-xs font-mono text-white mt-1 select-all">{user?.user_id}</div>
                </div>
                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5">
                  <div className="text-[11px] text-neutral-400">Organisasi</div>
                  <div className="text-xs font-mono text-white mt-1 select-all">{user?.tenant_id || "Default Organization"}</div>
                </div>
              </div>

              {/* Group Memberships */}
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-2">
                <div className="text-neutral-400 font-medium flex items-center justify-between">
                  <span>Grup Akses (MikroTik RBAC)</span>
                  <Shield size={14} className="text-cyan-400" />
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  {(user?.groups || []).map((grp) => (
                    <span
                      key={grp}
                      className="px-2.5 py-1 rounded-lg text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 font-semibold"
                    >
                      {grp}
                    </span>
                  ))}
                  {(!user?.groups || user.groups.length === 0) && (
                    <span className="text-neutral-500 text-xs">Belum ada grup yang ditugaskan.</span>
                  )}
                </div>
              </div>

              {/* Effective Permissions Summary */}
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-2">
                <div className="text-neutral-400 font-medium flex items-center justify-between">
                  <span>Izin Efektif</span>
                  <span className="text-emerald-400 font-mono">{(user?.permissions || []).length} Izin Aktif</span>
                </div>
                <p className="text-[11px] text-neutral-400 leading-relaxed">
                  Izin ditentukan oleh gabungan seluruh grup Anda dengan prioritas <code className="text-red-400">DENY</code>.
                </p>
              </div>
            </div>
          )}

          {/* 2. SECURITY TAB */}
          {activeTab === "security" && (
            <div className="space-y-6">
              {/* Change Password Form */}
              <form onSubmit={handleChangePassword} className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-3">
                <h4 className="font-semibold text-white flex items-center gap-2">
                  <Lock size={14} className="text-cyan-400" />
                  Ganti Kata Sandi
                </h4>
                <div className="space-y-2">
                  <input
                    type="password"
                    placeholder="Kata Sandi Baru (min. 6 karakter)"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
                  />
                  <input
                    type="password"
                    placeholder="Konfirmasi Kata Sandi Baru"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div className="flex justify-end pt-1">
                  <button
                    type="submit"
                    disabled={savingPassword || !newPassword}
                    className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-white font-medium disabled:opacity-50 transition"
                  >
                    {savingPassword ? "Menyimpan..." : "Perbarui Kata Sandi"}
                  </button>
                </div>
              </form>

              {/* Logout button */}
              <div className="pt-2 flex justify-between items-center">
                <span className="text-neutral-400">Keluar dari sesi ini</span>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    logout();
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 transition"
                >
                  <LogOut size={13} />
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          )}

          {/* 3. PREFERENCES TAB (Phase F.2 - Real Navigation to Settings) */}
          {activeTab === "preferences" && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-2">
                <h4 className="font-semibold text-white flex items-center gap-2 text-sm">
                  <Sliders size={16} className="text-cyan-400" />
                  Preferensi & Personalisasi AI
                </h4>
                <p className="text-neutral-400 text-xs leading-relaxed">
                  Persona respons dan memori jangka panjang AI Anda disimpan dan diisolasi secara mandiri pada tingkat akun.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => {
                    try { sessionStorage.setItem("aira_settings_tab", "memory"); } catch {}
                    window.dispatchEvent(new CustomEvent("aira:navigate", { detail: "settings" }));
                    window.dispatchEvent(new CustomEvent("aira:settings-tab", { detail: "memory" }));
                    onClose();
                  }}
                  className="p-4 rounded-xl bg-black/40 hover:bg-cyan-500/10 border border-white/10 hover:border-cyan-500/40 text-left transition group space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-white group-hover:text-cyan-300 transition">Memori AI</span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400 font-mono">Isolated</span>
                  </div>
                  <p className="text-[11px] text-neutral-400 leading-snug">
                    Kelola fakta teknis, preferensi IP, dan batasan operasional yang diingat AIRA.
                  </p>
                  <span className="text-[11px] text-cyan-400 font-medium inline-flex items-center gap-1 group-hover:underline">
                    Buka Tab Memory &rarr;
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    try { sessionStorage.setItem("aira_settings_tab", "persona"); } catch {}
                    window.dispatchEvent(new CustomEvent("aira:navigate", { detail: "settings" }));
                    window.dispatchEvent(new CustomEvent("aira:settings-tab", { detail: "persona" }));
                    onClose();
                  }}
                  className="p-4 rounded-xl bg-black/40 hover:bg-purple-500/10 border border-white/10 hover:border-purple-500/40 text-left transition group space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-white group-hover:text-purple-300 transition">Persona AI</span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-400 font-mono">Customizable</span>
                  </div>
                  <p className="text-[11px] text-neutral-400 leading-snug">
                    Atur gaya bahasa, instruksi khusus, dan preset peran AIRA untuk akun Anda.
                  </p>
                  <span className="text-[11px] text-purple-400 font-medium inline-flex items-center gap-1 group-hover:underline">
                    Buka Tab Persona &rarr;
                  </span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
