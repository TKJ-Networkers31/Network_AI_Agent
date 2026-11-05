import { useCallback, useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import LocationPanel from "../components/location/LocationPanel.jsx";
import GlobalSettingsPanel from "../components/settings/GlobalSettingsPanel.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import {
  Award,
  CheckCircle2,
  Coins,
  CreditCard,
  Loader2,
  Lock,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

export default function SettingsPage({ onOpenMenu }) {
  const [usage, setUsage] = useState(null);
  const [credits, setCredits] = useState(null);
  const [entitlements, setEntitlements] = useState(null);
  const [balance, setBalance] = useState(null);
  const [approvalPref, setApprovalPref] = useState(null);
  const [savingPref, setSavingPref] = useState(false);

  const { notify } = useToast();

  const fetchEntitlements = useCallback(async () => {
    try {
      const res = await fetch("/api/settings/entitlements/summary");
      const data = await res.json();
      if (data.success) {
        setEntitlements(data.entitlements);
        setBalance(data.balance);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchApprovalPreferences = useCallback(async () => {
    try {
      const res = await fetch("/api/settings/approvals/preferences");
      const data = await res.json();
      if (data.success) {
        setApprovalPref(data.preferences);
      }
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    api.tokenUsage().then(setUsage).catch(() => {});
    api.credits().then(setCredits).catch(() => {});
    fetchEntitlements();
    fetchApprovalPreferences();
  }, [fetchEntitlements, fetchApprovalPreferences]);

  const handleUpdateApprovalMode = async (mode) => {
    setSavingPref(true);
    try {
      const res = await fetch("/api/settings/approvals/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          auto_approve_categories: mode === "ALWAYS_ASK" ? [] : ["A"],
          allowed_change_windows: [],
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || "Gagal memperbarui preferensi.");
      }
      setApprovalPref((prev) => ({ ...prev, mode }));
      notify({ type: "success", message: "Kebijakan persetujuan operasional disimpan!" });
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingPref(false);
    }
  };

  const currentBal = balance?.current_balance ?? 10000;
  const monthlyAllow = balance?.monthly_allowance ?? 10000;
  const usedTokens = balance?.tokens_used_this_period ?? 0;
  const usedPercent = Math.min(100, Math.round((usedTokens / Math.max(1, monthlyAllow)) * 100));

  return (
    <div className="space-y-6">
      <TopBar
        title="Settings & Entitlements"
        subtitle="Kuota token, hak akses paket langganan, preferensi otonomi, & konfigurasi sistem"
        onMenuClick={onOpenMenu}
      />

      {/* PLAN & TOKEN METERING CARD */}
      <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-white/[0.08]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <Coins size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white">Langganan & Kuota Token AIRA</h3>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    entitlements?.tier === "enterprise"
                      ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                      : entitlements?.tier === "pro"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      : "bg-neutral-800 text-neutral-300 border border-white/10"
                  }`}
                >
                  {entitlements?.tier || "FREE TIER"}
                </span>
                {entitlements?.has_networking_plus && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    <Sparkles size={11} />
                    <span>NETWORKING++ AKTIF</span>
                  </span>
                )}
              </div>
              <p className="text-xs text-neutral-400 mt-0.5">
                Pemakaian token dihitung secara real-time untuk reasoning model dan automasi teknis.
              </p>
            </div>
          </div>

          <button
            onClick={fetchEntitlements}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-300 border border-neutral-700 transition"
          >
            <RefreshCw size={12} />
            <span>Refresh Saldo</span>
          </button>
        </div>

        {/* Token Progress Bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-neutral-400 font-medium">Pemakaian Bulan Ini:</span>
            <span className="font-mono text-neutral-200">
              <span className="text-cyan-400 font-semibold">{usedTokens.toLocaleString()}</span> /{" "}
              {monthlyAllow.toLocaleString()} tokens ({usedPercent}%)
            </span>
          </div>

          <div className="w-full h-2 rounded-full bg-neutral-800 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                usedPercent > 85 ? "bg-rose-500" : usedPercent > 60 ? "bg-amber-500" : "bg-cyan-400"
              }`}
              style={{ width: `${usedPercent}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-400 pt-1">
            <span>Sisa Saldo Tersedia: <strong className="text-white font-mono">{currentBal.toLocaleString()}</strong></span>
            {balance?.period_ends_at && (
              <span>Reset Kuota: {new Date(balance.period_ends_at * 1000).toLocaleDateString()}</span>
            )}
          </div>
        </div>
      </div>

      {/* AUTONOMY & APPROVAL POLICY PREFERENCES */}
      <div className="bg-neutral-900/60 border border-white/[0.08] rounded-2xl p-5 space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <ShieldCheck size={16} className="text-cyan-400" />
            <span>Kebijakan Persetujuan Otonomi (Risk Approval Engine)</span>
          </h3>
          <p className="text-xs text-neutral-400 mt-1">
            Tentukan kapan AIRA diizinkan menjalankan konfigurasi atau remediasi jaringan secara mandiri vs meminta persetujuan teknis.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            {
              id: "ALWAYS_ASK",
              title: "Selalu Minta Izin (Strict)",
              desc: "Minta persetujuan eksplisit untuk semua perubahan konfigurasi jaringan (Category B).",
              icon: ShieldAlert,
              color: "text-amber-400",
            },
            {
              id: "ASK_HIGH_RISK",
              title: "Standar (Recommended)",
              desc: "Otomatis jalankan inspeksi & diagnostik (Cat A); minta izin untuk modifikasi rute/antarmuka (Cat B).",
              icon: ShieldCheck,
              color: "text-cyan-400",
            },
            {
              id: "AUTO_APPROVE_LOW_RISK",
              title: "Otonom Terkendali",
              desc: "Izinkan auto-remediasi low-risk di dalam boundary terdaftar tanpa interupsi.",
              icon: Sparkles,
              color: "text-emerald-400",
            },
          ].map((opt) => {
            const Icon = opt.icon;
            const isSelected = (approvalPref?.mode || "ALWAYS_ASK") === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                disabled={savingPref}
                onClick={() => handleUpdateApprovalMode(opt.id)}
                className={`p-4 rounded-xl border text-left transition flex flex-col justify-between space-y-2 ${
                  isSelected
                    ? "bg-cyan-500/10 border-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.1)]"
                    : "bg-neutral-950/60 border-white/[0.06] hover:border-white/20"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon size={16} className={opt.color} />
                    <span className="text-xs font-semibold text-white">{opt.title}</span>
                  </div>
                  {isSelected && <CheckCircle2 size={14} className="text-cyan-400" />}
                </div>
                <p className="text-[11px] text-neutral-400 leading-relaxed">{opt.desc}</p>
              </button>
            );
          })}
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl2 p-4 flex items-center gap-3">
        <span className="text-lg">🧩</span>
        <p className="text-sm text-white/60">
          Mau ganti model aktif, atur fallback, atau cek status online/offline model? Semua itu sekarang ada di
          halaman <span className="text-accent-light font-medium">Models</span>.
        </p>
      </div>

      <div>
        <GlobalSettingsPanel />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl2 p-5">
          <h3 className="font-semibold mb-2 text-white">Token Sesi Ini</h3>
          {usage ? (
            <div className="text-sm text-white/70 space-y-1">
              <div>Total: {usage.session_total_tokens}</div>
              <div>Prompt: {usage.session_prompt_tokens}</div>
              <div>Completion: {usage.session_completion_tokens}</div>
            </div>
          ) : (
            <p className="text-white/40 text-sm">Belum ada pemakaian.</p>
          )}
        </div>

        <div className="bg-card border border-border rounded-xl2 p-5">
          <h3 className="font-semibold mb-2 text-white">Saldo OpenRouter</h3>
          {credits?.success ? (
            <div className="text-sm text-white/70 space-y-1">
              <div>Total: {credits.total_credits}</div>
              <div>Terpakai: {credits.total_usage}</div>
              <div>Sisa: {credits.remaining}</div>
            </div>
          ) : (
            <p className="text-white/40 text-sm">
              {credits?.error || "Provider aktif (default) bukan API eksternal."}
            </p>
          )}
        </div>
      </div>

      <div>
        <LocationPanel />
      </div>
    </div>
  );
}
