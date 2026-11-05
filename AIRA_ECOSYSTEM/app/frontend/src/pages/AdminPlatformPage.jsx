// src/pages/AdminPlatformPage.jsx
// AIRA OS - Multi-Site Identity & Platform Administration Workspace
// Mengelola Multi-Tenancy, Tier Langganan (Free/Pro/Networking++), Token Metering Engine,
// serta Antrean Sentral Persetujuan Operasional (Category B Risk Approvals).

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Award,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  Coins,
  CreditCard,
  Edit2,
  FileText,
  Key,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  Users,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";

const ADMIN_TABS = [
  { id: "tenants", label: "Tenant & Langganan", icon: Users },
  { id: "approvals", label: "Antrean Persetujuan", icon: ShieldAlert },
  { id: "policies", label: "Kebijakan Token", icon: Coins },
  { id: "audit", label: "Audit Ledger", icon: FileText },
];

export default function AdminPlatformPage({ onOpenMenu }) {
  const [activeTab, setActiveTab] = useState("tenants");
  const [tenants, setTenants] = useState([]);
  const [loadingTenants, setLoadingTenants] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState("tenant_default");

  // Approval queue state
  const [approvals, setApprovals] = useState([]);
  const [loadingApprovals, setLoadingApprovals] = useState(false);
  const [resolvingId, setResolvingId] = useState(null);

  // Edit Plan Modal state
  const [editingPlanTenant, setEditingPlanTenant] = useState(null);
  const [savingPlan, setSavingPlan] = useState(false);

  // Usage Ledger
  const [ledgerEntries, setLedgerEntries] = useState([]);
  const [loadingLedger, setLoadingLedger] = useState(false);

  const { notify } = useToast();

  const fetchTenants = useCallback(async () => {
    setLoadingTenants(true);
    try {
      const res = await fetch("/api/v1/admin/tenants");
      const data = await res.json();
      if (data.success) {
        setTenants(data.tenants || []);
      }
    } catch {
      // silent
    } finally {
      setLoadingTenants(false);
    }
  }, []);

  const fetchApprovals = useCallback(async () => {
    setLoadingApprovals(true);
    try {
      const res = await fetch("/api/v1/admin/approvals/pending");
      const data = await res.json();
      if (data.success) {
        setApprovals(data.pending_approvals || []);
      }
    } catch {
      // silent
    } finally {
      setLoadingApprovals(false);
    }
  }, []);

  const fetchLedger = useCallback(async (tenantId) => {
    setLoadingLedger(true);
    try {
      const res = await fetch(`/api/v1/admin/tenants/${encodeURIComponent(tenantId)}/usage-ledger`);
      const data = await res.json();
      if (data.success) {
        setLedgerEntries(data.ledger || []);
      }
    } catch {
      // silent
    } finally {
      setLoadingLedger(false);
    }
  }, []);

  useEffect(() => {
    fetchTenants();
    fetchApprovals();
  }, [fetchTenants, fetchApprovals]);

  useEffect(() => {
    if (activeTab === "audit" && selectedTenant) {
      fetchLedger(selectedTenant);
    }
  }, [activeTab, selectedTenant, fetchLedger]);

  const handleResolveApproval = async (approvalId, decision) => {
    setResolvingId(approvalId);
    try {
      const res = await fetch(`/api/v1/admin/approvals/${encodeURIComponent(approvalId)}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision: decision,
          notes: decision === "approved" ? "Disetujui oleh Administrator Platform" : "Ditolak oleh Administrator",
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || "Gagal memproses persetujuan.");
      }
      notify({
        type: "success",
        message: `Persetujuan berhasil di-${decision === "approved" ? "setujui" : "tolak"}.`,
      });
      fetchApprovals();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setResolvingId(null);
    }
  };

  const handleSavePlan = async (e) => {
    e.preventDefault();
    if (!editingPlanTenant) return;
    setSavingPlan(true);

    const form = e.target;
    const payload = {
      tier: form.tier.value,
      monthly_token_allowance: parseInt(form.allowance.value, 10),
      has_networking_plus: form.networking_plus.checked,
      expires_at: form.expires_at.value ? new Date(form.expires_at.value).toISOString() : undefined,
    };

    try {
      const res = await fetch(
        `/api/v1/admin/tenants/${encodeURIComponent(editingPlanTenant.tenant_id)}/assign-plan`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || "Gagal memperbarui langganan.");
      }
      notify({ type: "success", message: "Tier langganan & token berhasil diperbarui!" });
      setEditingPlanTenant(null);
      fetchTenants();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingPlan(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0 space-y-4">
      <TopBar
        title="AIRA Platform Administration"
        subtitle="Konsol Tata Kelola Multi-Tenant, Kebijakan Token Metering, & Persetujuan Sensitif"
        onOpenMenu={onOpenMenu}
      />

      {/* Admin Tab Navigation */}
      <div className="shrink-0 flex items-center justify-between border-b border-white/[0.08] pb-2">
        <div className="flex items-center gap-1.5 overflow-x-auto">
          {ADMIN_TABS.map((t) => {
            const Icon = t.icon;
            const isSelected = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium transition ${
                  isSelected
                    ? "bg-rose-500/15 text-rose-300 border border-rose-500/30 shadow-[0_0_12px_rgba(244,63,94,0.15)]"
                    : "text-neutral-400 hover:text-white hover:bg-white/[0.05] border border-transparent"
                }`}
              >
                <Icon size={14} className={isSelected ? "text-rose-400" : "text-neutral-400"} />
                <span>{t.label}</span>
                {t.id === "approvals" && approvals.length > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                    {approvals.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            ADMIN / HOST RESTRICTED
          </span>
        </div>
      </div>

      {/* TAB: TENANTS & PLANS */}
      {activeTab === "tenants" && (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Daftar Tenant & Organisasi</h3>
              <p className="text-xs text-neutral-400">
                Kelola hak akses langganan (Free, Pro, Enterprise) dan paket add-on Networking++.
              </p>
            </div>
            <button
              onClick={fetchTenants}
              disabled={loadingTenants}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 border border-neutral-700 transition"
            >
              <RefreshCw size={13} className={loadingTenants ? "animate-spin text-rose-400" : ""} />
              <span>Refresh Tenant</span>
            </button>
          </div>

          <div className="overflow-hidden rounded-xl border border-white/[0.08] bg-neutral-900/60">
            <table className="w-full text-left text-xs text-neutral-300">
              <thead className="bg-neutral-950/80 text-[11px] uppercase tracking-wider text-neutral-400 border-b border-white/[0.08]">
                <tr>
                  <th className="px-4 py-3">Tenant / Organisasi</th>
                  <th className="px-4 py-3">Tier Plan</th>
                  <th className="px-4 py-3">Networking++</th>
                  <th className="px-4 py-3">Saldo Token</th>
                  <th className="px-4 py-3">Batas Perangkat</th>
                  <th className="px-4 py-3 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {tenants.map((t) => (
                  <tr key={t.tenant_id} className="hover:bg-white/[0.02] transition">
                    <td className="px-4 py-3 font-medium text-white">
                      <div>{t.company_name || t.tenant_id}</div>
                      <div className="text-[10px] font-mono text-neutral-500">{t.tenant_id}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          t.tier === "enterprise"
                            ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                            : t.tier === "pro"
                            ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                            : "bg-neutral-700 text-neutral-300"
                        }`}
                      >
                        {t.tier || "FREE"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {t.has_networking_plus ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                          <Sparkles size={11} />
                          <span>AKTIF</span>
                        </span>
                      ) : (
                        <span className="text-neutral-500 text-[11px]">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      <span className="text-white font-semibold">
                        {(t.token_balance || 0).toLocaleString()}
                      </span>
                      <span className="text-neutral-500 text-[10px]">
                        {" "}/ {(t.monthly_allowance || 10000).toLocaleString()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-neutral-400">
                      {t.max_devices || (t.tier === "enterprise" ? "Unlimited" : t.tier === "pro" ? "50" : "5")}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setEditingPlanTenant(t)}
                        className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 border border-neutral-700 transition inline-flex items-center gap-1.5"
                      >
                        <Edit2 size={12} />
                        <span>Ubah Paket</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB: APPROVAL QUEUE (CATEGORY B RISK) */}
      {activeTab === "approvals" && (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Antrean Persetujuan Sensitif (Risk Category B)</h3>
              <p className="text-xs text-neutral-400">
                Operasi yang dapat mengubah konfigurasi perangkat atau mempengaruhi lalu lintas jaringan membutuhkan persetujuan operator.
              </p>
            </div>
            <button
              onClick={fetchApprovals}
              disabled={loadingApprovals}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 border border-neutral-700 transition"
            >
              <RefreshCw size={13} className={loadingApprovals ? "animate-spin text-rose-400" : ""} />
              <span>Refresh Antrean</span>
            </button>
          </div>

          {approvals.length === 0 ? (
            <div className="p-12 text-center border border-dashed border-white/10 rounded-2xl bg-neutral-900/30">
              <CheckCircle2 size={36} className="mx-auto text-emerald-400/80 mb-3" />
              <h4 className="text-sm font-medium text-white mb-1">Tidak Ada Persetujuan Tertunda</h4>
              <p className="text-xs text-neutral-400 max-w-sm mx-auto">
                Semua operasi berisiko tinggi telah dievaluasi atau dijalankan sesuai preferensi otonomi yang diizinkan.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {approvals.map((appr) => (
                <div
                  key={appr.approval_id}
                  className="p-4 rounded-xl bg-neutral-900/80 border border-white/[0.08] hover:border-rose-500/30 transition flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30 uppercase">
                        {appr.risk_category || "Category B"}
                      </span>
                      <span className="text-xs font-mono text-cyan-400 font-semibold">{appr.action_name}</span>
                      <span className="text-neutral-500 text-xs">•</span>
                      <span className="text-xs text-neutral-400">Target: {appr.target_device || "Network"}</span>
                    </div>
                    <p className="text-xs text-neutral-200">{appr.description || "Permintaan eksekusi perubahan konfigurasi jaringan."}</p>
                    <div className="text-[11px] font-mono text-neutral-500">
                      Operator: <span className="text-neutral-400">{appr.requested_by || "system"}</span> |
                      Waktu: <span className="text-neutral-400">{new Date(appr.created_at * 1000).toLocaleString()}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleResolveApproval(appr.approval_id, "rejected")}
                      disabled={resolvingId === appr.approval_id}
                      className="px-3 py-1.5 rounded-lg bg-red-500/15 hover:bg-red-500/25 text-red-300 border border-red-500/30 text-xs font-medium transition disabled:opacity-50 flex items-center gap-1.5"
                    >
                      <XCircle size={13} />
                      <span>Tolak</span>
                    </button>
                    <button
                      onClick={() => handleResolveApproval(appr.approval_id, "approved")}
                      disabled={resolvingId === appr.approval_id}
                      className="px-4 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-xs font-semibold transition disabled:opacity-50 flex items-center gap-1.5"
                    >
                      <CheckCircle2 size={13} />
                      <span>Setujui Eksekusi</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB: TOKEN POLICIES */}
      {activeTab === "policies" && (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-white">Matriks Kebijakan Biaya Token</h3>
            <p className="text-xs text-neutral-400">
              Biaya token per operasi teknis yang dimetering oleh AIRA Entitlement Engine.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { op: "Chat & Intent Reasoning", cost: 1, unit: "per query" },
              { op: "Topology Discovery Scan", cost: 10, unit: "per run" },
              { op: "Network Configuration Backup", cost: 5, unit: "per device" },
              { op: "CLI Command Execution", cost: 2, unit: "per command" },
              { op: "SNMP Bulk Telemetry Poll", cost: 3, unit: "per cycle" },
              { op: "Automated Workflow Trigger", cost: 4, unit: "per execution" },
            ].map((p, idx) => (
              <div key={idx} className="p-4 rounded-xl bg-neutral-900/60 border border-white/[0.08] flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-medium text-white">{p.op}</h4>
                  <span className="text-[11px] text-neutral-500">{p.unit}</span>
                </div>
                <div className="flex items-center gap-1 text-cyan-400 font-mono font-bold text-sm bg-cyan-500/10 px-2.5 py-1 rounded-lg border border-cyan-500/20">
                  <Coins size={13} />
                  <span>{p.cost}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB: AUDIT LEDGER */}
      {activeTab === "audit" && (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Audit Konsumsi Token & Aktivitas</h3>
              <p className="text-xs text-neutral-400">
                Log audit transaksi token untuk tenant terpilih ({selectedTenant}).
              </p>
            </div>
            <button
              onClick={() => fetchLedger(selectedTenant)}
              disabled={loadingLedger}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 border border-neutral-700 transition"
            >
              <RefreshCw size={13} className={loadingLedger ? "animate-spin text-rose-400" : ""} />
              <span>Refresh Log</span>
            </button>
          </div>

          <div className="overflow-hidden rounded-xl border border-white/[0.08] bg-neutral-900/60">
            <table className="w-full text-left text-xs text-neutral-300">
              <thead className="bg-neutral-950/80 text-[11px] uppercase tracking-wider text-neutral-400 border-b border-white/[0.08]">
                <tr>
                  <th className="px-4 py-3">Waktu</th>
                  <th className="px-4 py-3">Operasi</th>
                  <th className="px-4 py-3">Jumlah Token</th>
                  <th className="px-4 py-3">Operator</th>
                  <th className="px-4 py-3">Catatan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {ledgerEntries.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-neutral-500">
                      Belum ada catatan transaksi token untuk tenant ini.
                    </td>
                  </tr>
                ) : (
                  ledgerEntries.map((l, i) => (
                    <tr key={i} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-3 text-neutral-400 font-mono text-[11px]">
                        {new Date(l.timestamp * 1000).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 font-semibold text-white">{l.operation_type}</td>
                      <td className="px-4 py-3 font-mono text-cyan-400">-{l.tokens_consumed}</td>
                      <td className="px-4 py-3 text-neutral-300">{l.actor || "system"}</td>
                      <td className="px-4 py-3 text-neutral-400 text-[11px]">{l.metadata || "-"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODAL EDIT PLAN */}
      {editingPlanTenant && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-neutral-900 border border-white/10 rounded-2xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <CreditCard size={18} className="text-rose-400" />
                <h3 className="text-sm font-semibold text-white">Ubah Paket Langganan Tenant</h3>
              </div>
              <button onClick={() => setEditingPlanTenant(null)} className="text-neutral-400 hover:text-white">
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleSavePlan} className="space-y-3">
              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">Tenant ID</label>
                <input
                  type="text"
                  disabled
                  defaultValue={editingPlanTenant.tenant_id}
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950/50 border border-white/5 text-xs text-neutral-500 font-mono"
                />
              </div>

              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">Tier Langganan</label>
                <select
                  name="tier"
                  defaultValue={editingPlanTenant.tier || "free"}
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-rose-500"
                >
                  <option value="free">Free (Dasar / Pemula)</option>
                  <option value="pro">Pro (Profesional)</option>
                  <option value="enterprise">Enterprise (Organisasi Besar)</option>
                </select>
              </div>

              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">Jatah Token Bulanan</label>
                <input
                  type="number"
                  name="allowance"
                  defaultValue={editingPlanTenant.monthly_allowance || 10000}
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white font-mono focus:outline-none focus:border-rose-500"
                />
              </div>

              <div className="flex items-center gap-2 pt-1 pb-1">
                <input
                  type="checkbox"
                  id="networking_plus"
                  name="networking_plus"
                  defaultChecked={editingPlanTenant.has_networking_plus}
                  className="rounded border-white/20 text-rose-500 focus:ring-0"
                />
                <label htmlFor="networking_plus" className="text-xs text-white font-medium cursor-pointer">
                  Aktifkan Entitlement Networking++ (Fitur Lanjut Topologi & NMS)
                </label>
              </div>

              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">Tanggal Kedaluwarsa (Opsional)</label>
                <input
                  type="date"
                  name="expires_at"
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white font-mono focus:outline-none focus:border-rose-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditingPlanTenant(null)}
                  className="px-3.5 py-2 rounded-lg text-xs text-neutral-400 hover:text-white transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={savingPlan}
                  className="px-4 py-2 rounded-lg bg-rose-500 hover:bg-rose-400 text-white font-semibold text-xs transition disabled:opacity-50 flex items-center gap-1.5"
                >
                  {savingPlan ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      <span>Menyimpan...</span>
                    </>
                  ) : (
                    <span>Simpan Perubahan</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
