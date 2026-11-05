// src/components/AccountProfileModal.jsx
// AIRA OS — User Profile, Security, Subscription & Plan, Token Metering & Preferences Modal
// Replaces dedicated Settings primary nav item (Directive Section 2.A)

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  Clock,
  Coins,
  CreditCard,
  Key,
  Layers,
  Lock,
  LogOut,
  QrCode,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  User,
  X,
  Zap,
} from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "./Toast.jsx";
import { getAuthHeaders } from "../api.js";

export default function AccountProfileModal({ isOpen, onClose }) {
  const { user: authUser, subscription: authSub, quota: authQuota, isGuest, logout, openLogin, openRegister } = useAuth();
  const [activeTab, setActiveTab] = useState("profile");
  const [userProfile, setUserProfile] = useState(null);
  const [loading, setLoading] = useState(false);

  // Security state
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  // MFA state
  const [mfaData, setMfaData] = useState(null);
  const [totpCode, setTotpCode] = useState("");
  const [settingUpMfa, setSettingUpMfa] = useState(false);
  const [verifyingMfa, setVerifyingMfa] = useState(false);

  // Billing & Checkout simulation state
  const [simulatingPlan, setSimulatingPlan] = useState(null);

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
    if (newPassword.length < 8) {
      notify({ type: "error", message: "Kata sandi baru minimal 8 karakter." });
      return;
    }
    if (newPassword !== confirmPassword) {
      notify({ type: "error", message: "Konfirmasi kata sandi tidak cocok." });
      return;
    }

    setSavingPassword(true);
    try {
      const res = await fetch("/api/v1/auth/change-password-mandatory", {
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

  async function handleInitMfa() {
    setSettingUpMfa(true);
    try {
      const res = await fetch("/api/v1/auth/mfa/setup", { headers: getAuthHeaders() });
      const data = await res.json();
      if (data.success) {
        setMfaData(data.mfa);
      } else {
        notify({ type: "error", message: data.detail || "Gagal inisialisasi MFA." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSettingUpMfa(false);
    }
  }

  async function handleVerifyMfa() {
    if (!mfaData || totpCode.trim().length !== 6) {
      notify({ type: "error", message: "Masukkan 6-digit kode verifikasi dari aplikasi authenticator." });
      return;
    }
    setVerifyingMfa(true);
    try {
      const res = await fetch("/api/v1/auth/mfa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ secret: mfaData.secret, code: totpCode.trim() }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        notify({ type: "success", message: "2FA (TOTP) berhasil diaktifkan!" });
        setMfaData(null);
        setTotpCode("");
        loadProfile();
      } else {
        notify({ type: "error", message: data.detail || data.message || "Kode TOTP tidak valid." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setVerifyingMfa(false);
    }
  }

  async function handleSimulateUpgrade(tier, hasNetplus) {
    setSimulatingPlan(tier);
    try {
      // Step 1: Create Invoice
      const invRes = await fetch("/api/v1/billing/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ plan_id: tier === "PRO" ? "plan_pro" : "plan_enterprise" }),
      });
      const invData = await invRes.json();
      if (!invData.success) throw new Error(invData.detail || "Gagal membuat invoice.");

      // Step 2: Simulate Payment & Webhook fulfillment
      const payRes = await fetch("/api/v1/billing/simulate-mock", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          invoice_id: invData.invoice.invoice_id,
          plan_tier: tier,
          has_networking_plus: hasNetplus,
        }),
      });
      const payData = await payRes.json();
      if (payData.success) {
        notify({ type: "success", message: `Berhasil upgrade ke AIRA ${tier} (${hasNetplus ? "+ Networking++" : ""})!` });
        loadProfile();
      } else {
        notify({ type: "error", message: payData.detail || "Simulasi pembayaran gagal." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSimulatingPlan(null);
    }
  }

  async function handleSignOut() {
    await logout();
    notify({ type: "info", message: "Sesi berhasil ditutup. Kembali ke Guest Mode." });
    onClose();
  }

  if (!isOpen) return null;

  const user = userProfile?.user || authUser || (isGuest ? { username: "Guest User", email: "guest@local", roles: ["GUEST"] } : null);
  const sub = userProfile?.subscription || authSub || { plan_id: isGuest ? "GUEST" : "FREE", subscription_status: "ACTIVE", has_networking_plus: false };
  const quota = userProfile?.quota || authQuota || { allocated_tokens: isGuest ? 15000 : 100000, used_tokens: 0, remaining_tokens: isGuest ? 15000 : 100000, next_reset_formatted: "1 Des 2026, 00:00 WIB" };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-sakura flex items-center justify-center font-bold text-white shadow-lg">
              {user ? user.username.charAt(0).toUpperCase() : "G"}
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white leading-tight">
                {user ? user.username : "Guest User"}
              </h2>
              <p className="text-xs text-neutral-400">
                {user ? user.email : "Akses Tamu (Tanpa Akun)"}
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
            { id: "subscription", label: "Subscription & Plan", icon: CreditCard },
            { id: "tokens", label: "Token Usage", icon: Coins },
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
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* 1. PROFILE TAB */}
          {activeTab === "profile" && (
            <div className="space-y-4">
              {isGuest ? (
                <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 space-y-3">
                  <div className="flex items-center gap-2 text-amber-400 text-xs font-semibold">
                    <AlertTriangle size={15} />
                    <span>Mode Tamu (Guest Session)</span>
                  </div>
                  <p className="text-xs text-neutral-300 leading-relaxed">
                    Anda sedang menggunakan AIRA OS tanpa akun terautentikasi. Anda memiliki kuota awal 15.000 token untuk eksplorasi AI. Untuk menyimpan riwayat perangkat secara permanen dan menjalankan playbook otomatisasi, silakan masuk atau daftar.
                  </p>
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={() => {
                        onClose();
                        openLogin();
                      }}
                      className="px-3.5 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-xs font-semibold text-white shadow-sm transition"
                    >
                      Masuk ke Akun
                    </button>
                    <button
                      onClick={() => {
                        onClose();
                        openRegister();
                      }}
                      className="px-3.5 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs font-medium text-neutral-200 border border-neutral-700 transition"
                    >
                      Daftar Akun Baru
                    </button>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5">
                    <div className="text-[11px] text-neutral-400">User ID</div>
                    <div className="text-xs font-mono text-white mt-1 select-all">{user?.user_id}</div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5">
                    <div className="text-[11px] text-neutral-400">Tenant / Organisasi ID</div>
                    <div className="text-xs font-mono text-white mt-1 select-all">{user?.tenant_id}</div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5">
                    <div className="text-[11px] text-neutral-400">Role / Hak Akses</div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {user?.roles?.map((r) => (
                        <span key={r} className="text-[10px] font-semibold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5">
                    <div className="text-[11px] text-neutral-400">Status Akun</div>
                    <div className="text-xs font-medium text-emerald-400 mt-1 flex items-center gap-1">
                      <CheckCircle2 size={13} /> Aktif Terverifikasi
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 2. SECURITY TAB */}
          {activeTab === "security" && (
            <div className="space-y-6">
              {isGuest ? (
                <p className="text-xs text-neutral-400">Pengaturan keamanan akun hanya tersedia untuk pengguna terdaftar.</p>
              ) : (
                <>
                  <form onSubmit={handleChangePassword} className="space-y-3 p-4 rounded-xl bg-white/[0.02] border border-white/5">
                    <h3 className="text-xs font-semibold text-white flex items-center gap-2">
                      <Key size={14} className="text-cyan-400" /> Ubah Kata Sandi
                    </h3>
                    <div className="grid grid-cols-2 gap-3">
                      <input
                        type="password"
                        placeholder="Kata sandi baru (min 8 char)"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        className="px-3 py-2 text-xs bg-black/50 border border-white/10 rounded-lg text-white"
                      />
                      <input
                        type="password"
                        placeholder="Ulangi kata sandi baru"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        className="px-3 py-2 text-xs bg-black/50 border border-white/10 rounded-lg text-white"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={savingPassword}
                      className="px-4 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition disabled:opacity-50"
                    >
                      {savingPassword ? "Menyimpan..." : "Perbarui Kata Sandi"}
                    </button>
                  </form>

                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-3">
                    <h3 className="text-xs font-semibold text-white flex items-center gap-2">
                      <ShieldCheck size={14} className="text-emerald-400" /> Autentikasi Dua Faktor (2FA / TOTP)
                    </h3>
                    <p className="text-xs text-neutral-400">
                      Amankan akun dengan autentikator standar Google Authenticator atau 1Password.
                    </p>
                    {mfaData ? (
                      <div className="p-3 bg-black/50 border border-cyan-500/30 rounded-lg space-y-2">
                        <div className="text-[11px] text-cyan-300 font-medium">TOTP Secret Key:</div>
                        <div className="p-2 bg-white rounded-lg inline-block text-black font-mono text-[10px] select-all">
                          {mfaData.secret}
                        </div>
                        <div className="flex gap-2 items-center">
                          <input
                            type="text"
                            maxLength={6}
                            value={totpCode}
                            onChange={(e) => setTotpCode(e.target.value)}
                            placeholder="6-digit kode"
                            className="w-32 px-3 py-1.5 text-xs font-mono tracking-widest text-center bg-black border border-white/20 rounded-lg text-white"
                          />
                          <button
                            onClick={handleVerifyMfa}
                            disabled={verifyingMfa}
                            className="px-4 py-1.5 text-xs font-medium rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 transition"
                          >
                            {verifyingMfa ? "Memverifikasi..." : "Verifikasi & Aktifkan"}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={handleInitMfa}
                        disabled={settingUpMfa}
                        className="px-4 py-1.5 text-xs font-medium rounded-lg bg-white/10 hover:bg-white/20 text-neutral-200 transition"
                      >
                        {settingUpMfa ? "Menyiapkan..." : "Setup Two-Factor Authentication"}
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* 3. SUBSCRIPTION & PLAN TAB */}
          {activeTab === "subscription" && (
            <div className="space-y-6">
              <div className="p-4 rounded-xl bg-gradient-to-r from-cyan-500/10 via-sakura/10 to-indigo-500/10 border border-cyan-500/20 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-cyan-500 text-white uppercase tracking-wider">
                      {sub.plan_id || "FREE"}
                    </span>
                    <span className="text-xs text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 size={12} /> {sub.subscription_status || "ACTIVE"}
                    </span>
                  </div>
                  <p className="text-xs text-neutral-300 mt-2">
                    {sub.has_networking_plus ? "Networking++ Add-on Aktif: Akses penuh NMS & Topologi AI." : "Tingkatkan ke Networking++ untuk otomasi playbook."}
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-[11px] text-neutral-400">Sisa Kuota Token</div>
                  <div className="text-base font-bold text-white">{(quota.remaining_tokens || 0).toLocaleString()}</div>
                </div>
              </div>

              {/* Upgrade Tiers */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-2">
                  <div className="text-xs font-semibold text-white">AIRA Pro</div>
                  <div className="text-sm font-bold text-cyan-400">Rp 250.000 / bln</div>
                  <ul className="text-[11px] text-neutral-400 space-y-1 list-disc list-inside">
                    <li>2.000.000 token per bulan</li>
                    <li>Multi-site network inventory</li>
                    <li>SLA prioritas AI reasoning</li>
                  </ul>
                  <button
                    onClick={() => handleSimulateUpgrade("PRO", true)}
                    disabled={simulatingPlan === "PRO"}
                    className="w-full mt-3 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 text-white hover:bg-cyan-500 transition"
                  >
                    {simulatingPlan === "PRO" ? "Memproses..." : "Upgrade ke Pro"}
                  </button>
                </div>

                <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-2">
                  <div className="text-xs font-semibold text-white">AIRA Enterprise</div>
                  <div className="text-sm font-bold text-purple-400">Rp 1.500.000 / bln</div>
                  <ul className="text-[11px] text-neutral-400 space-y-1 list-disc list-inside">
                    <li>10.000.000 token per bulan</li>
                    <li>Networking++ Add-on Included</li>
                    <li>Ansible automation playbook runner</li>
                  </ul>
                  <button
                    onClick={() => handleSimulateUpgrade("ENTERPRISE", true)}
                    disabled={simulatingPlan === "ENTERPRISE"}
                    className="w-full mt-3 py-1.5 text-xs font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-500 transition"
                  >
                    {simulatingPlan === "ENTERPRISE" ? "Memproses..." : "Upgrade Enterprise"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 4. TOKEN USAGE TAB — ChatGPT / Claude Style */}
          {activeTab === "tokens" && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-neutral-400">Paket Penggunaan:</span>
                  <span className="font-semibold text-cyan-400 uppercase tracking-wide">
                    AIRA {quota.tier || sub.plan_id || (isGuest ? "GUEST" : "FREE")}
                  </span>
                </div>

                <div className="w-full bg-white/10 rounded-full h-2.5 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-cyan-500 to-sakura h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min(100, Math.round(((quota.used_tokens || 0) / (quota.allocated_tokens || 1)) * 100))}%`,
                    }}
                  />
                </div>

                <div className="grid grid-cols-3 gap-2 pt-1 text-center">
                  <div className="p-2 rounded-lg bg-white/[0.02]">
                    <div className="text-[10px] text-neutral-500 uppercase">Alokasi Siklus</div>
                    <div className="text-xs font-bold text-white font-mono mt-0.5">
                      {(quota.allocated_tokens || 100000).toLocaleString()}
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/[0.02]">
                    <div className="text-[10px] text-neutral-500 uppercase">Terpakai</div>
                    <div className="text-xs font-bold text-rose-400 font-mono mt-0.5">
                      {(quota.used_tokens || 0).toLocaleString()}
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/[0.02]">
                    <div className="text-[10px] text-neutral-500 uppercase">Sisa Kuota</div>
                    <div className="text-xs font-bold text-emerald-400 font-mono mt-0.5">
                      {(quota.remaining_tokens || 0).toLocaleString()}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-white/5 text-[11px] text-neutral-400">
                  <span className="flex items-center gap-1.5">
                    <Clock size={12} className="text-cyan-400" />
                    <span>Reset Berikutnya:</span>
                  </span>
                  <span className="text-white font-medium">
                    {quota.next_reset_formatted || "1 Des 2026, 00:00 WIB"}
                  </span>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-[11px] text-neutral-400 leading-relaxed">
                ℹ️ <strong>Mekanisme Reset:</strong> Kuota token penggunaan Anda direset secara otomatis pada setiap awal siklus kalender (00:00 WIB) tanpa menghapus histori analisis atau rekaman audit infrastruktur Anda.
              </div>

              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-neutral-300">Biaya Internal Credits per Alat Operasional</h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5 flex justify-between">
                    <span className="text-neutral-400">Device Ping</span>
                    <span className="text-white font-mono">5 credits</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5 flex justify-between">
                    <span className="text-neutral-400">Diagnostics Check</span>
                    <span className="text-white font-mono">50 credits</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5 flex justify-between">
                    <span className="text-neutral-400">Config Synthesis</span>
                    <span className="text-white font-mono">100 credits</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5 flex justify-between">
                    <span className="text-neutral-400">Topology Discovery</span>
                    <span className="text-white font-mono">150 credits</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 5. PREFERENCES TAB */}
          {activeTab === "preferences" && (
            <div className="space-y-4">
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5 flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-white">Tema Antarmuka</div>
                  <div className="text-[11px] text-neutral-400">AIRA Obsidian Minimalist Dark</div>
                </div>
                <span className="text-xs text-cyan-400 font-semibold px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20">
                  Aktif
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5 flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-white">Audio Soundscape & Voice Feedback</div>
                  <div className="text-[11px] text-neutral-400">Notifikasi audio saat tugas selesai atau insiden kritis</div>
                </div>
                <input type="checkbox" defaultChecked className="toggle-checkbox accent-cyan-500" />
              </div>
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5 flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-white">NMS Live Telemetry Streaming</div>
                  <div className="text-[11px] text-neutral-400">Pembaruan websocket otomatis setiap 5 detik</div>
                </div>
                <input type="checkbox" defaultChecked className="toggle-checkbox accent-cyan-500" />
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-3 border-t border-white/10 bg-black/40 flex items-center justify-between">
          <div>
            {!isGuest && (
              <button
                onClick={handleSignOut}
                className="flex items-center gap-1.5 text-xs text-rose-400 hover:text-rose-300 font-medium transition"
              >
                <LogOut size={14} />
                <span>Keluar dari Sesi (Sign Out)</span>
              </button>
            )}
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs font-medium text-white border border-neutral-700 transition"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
