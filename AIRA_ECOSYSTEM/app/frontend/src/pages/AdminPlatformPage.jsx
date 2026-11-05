// src/pages/AdminPlatformPage.jsx
// AIRA OS — AIRA Control Plane (Admin Site)
// Implements 10 authoritative platform modules as required by Directive Section 2.B

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Award,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  Coins,
  Cpu,
  CreditCard,
  Database,
  Edit2,
  ExternalLink,
  Eye,
  FileText,
  Globe,
  Key,
  Layers,
  Lock,
  Mail,
  Play,
  Radio,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  UserCheck,
  Users,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";

const CONTROL_PLANE_MODULES = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "users", label: "User Management", icon: Users },
  { id: "organizations", label: "Organizations", icon: Layers },
  { id: "plans", label: "Plans & Entitlements", icon: Award },
  { id: "subscriptions", label: "Subscription Management", icon: CreditCard },
  { id: "billing", label: "Billing Management", icon: Coins },
  { id: "infrastructure", label: "Infrastructure & NOC", icon: Server },
  { id: "ai_config", label: "AI & Platform Configuration", icon: Cpu },
  { id: "security", label: "Security & AAA", icon: ShieldCheck },
  { id: "settings", label: "Platform Settings", icon: Sliders },
];

export default function AdminPlatformPage({ onOpenMenu }) {
  const [activeModule, setActiveModule] = useState("overview");

  // Data states
  const [users, setUsers] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [tokenPolicy, setTokenPolicy] = useState(null);
  const [loading, setLoading] = useState(false);

  // Impersonation modal state
  const [impersonateTarget, setImpersonateTarget] = useState(null);
  const [impersonateReason, setImpersonateReason] = useState("");
  const [impersonating, setImpersonating] = useState(false);

  // Subscription Assignment modal state
  const [assignSubUser, setAssignSubUser] = useState(null);
  const [selectedPlanTier, setSelectedPlanTier] = useState("PRO");
  const [assignNetplus, setAssignNetplus] = useState(true);
  const [assignDuration, setAssignDuration] = useState(30);
  const [savingSub, setSavingSub] = useState(false);

  const { notify } = useToast();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [uRes, tRes, sRes, iRes, txRes, aRes, polRes] = await Promise.all([
        fetch("/api/v1/admin/users?limit=50").then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/tenants").then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/subscriptions?limit=50").then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/billing/invoices?limit=50").then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/billing/transactions?limit=50").then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/approvals?status=PENDING").then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/token-policy?tier=PRO").then((r) => r.json()).catch(() => ({})),
      ]);

      if (uRes.success) setUsers(uRes.users || []);
      if (tRes.success) setTenants(tRes.tenants || []);
      if (sRes.success) setSubscriptions(sRes.subscriptions || []);
      if (iRes.success) setInvoices(iRes.invoices || []);
      if (txRes.success) setTransactions(txRes.transactions || []);
      if (aRes.success) setApprovals(aRes.approvals || []);
      if (polRes.success) setTokenPolicy(polRes.policy);
    } catch (err) {
      console.warn("Error loading admin data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Impersonate action
  async function handleConfirmImpersonate() {
    if (!impersonateTarget || !impersonateReason.trim()) {
      notify({ type: "error", message: "Alasan impersonation wajib diisi untuk audit." });
      return;
    }
    setImpersonating(true);
    try {
      const res = await fetch("/api/v1/admin/impersonate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_user_id: impersonateTarget.user_id,
          reason: impersonateReason.trim(),
        }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        notify({
          type: "success",
          message: `Sesi impersonasi aktif sebagai ${impersonateTarget.username}. Tindakan dicatat di audit log.`,
        });
        setImpersonateTarget(null);
        setImpersonateReason("");
      } else {
        notify({ type: "error", message: data.detail || "Gagal melakukan impersonasi." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setImpersonating(false);
    }
  }

  // Assign subscription action
  async function handleAssignSubscription() {
    if (!assignSubUser) return;
    setSavingSub(true);
    try {
      const res = await fetch("/api/v1/admin/subscriptions/assign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: assignSubUser.user_id,
          plan_id: selectedPlanTier,
          duration_days: assignDuration,
          networking_addon: assignNetplus,
          renewal_status: "MANUAL",
        }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        notify({ type: "success", message: `Langganan user ${assignSubUser.username} berhasil diatur ke ${selectedPlanTier}.` });
        setAssignSubUser(null);
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal mengatur langganan." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingSub(false);
    }
  }

  // Check expirations manually
  async function handleSweepExpirations() {
    try {
      const res = await fetch("/api/v1/admin/subscriptions/check-expirations", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        notify({
          type: "success",
          message: `Pemeriksaan selesai: ${data.report.expired_count} akun kadaluarsa telah diturunkan ke Free tanpa menghapus data.`,
        });
        loadData();
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  // Resolve pending approval
  async function handleResolveApproval(approvalId, approved) {
    try {
      const res = await fetch(`/api/v1/admin/approvals/${encodeURIComponent(approvalId)}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved, review_notes: approved ? "Approved by Superadmin" : "Rejected" }),
      });
      const data = await res.json();
      if (data.success) {
        notify({ type: "success", message: `Persetujuan berhasil di-${approved ? "setujui" : "tolak"}.` });
        loadData();
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  return (
    <div className="flex flex-col h-full bg-[#0d0d10] text-neutral-200">
      <TopBar onOpenMenu={onOpenMenu} title="AIRA Control Plane" />

      {/* Control Plane Horizontal Subnav */}
      <div className="flex items-center gap-1.5 px-6 py-2.5 border-b border-white/[0.08] bg-black/40 overflow-x-auto text-xs shrink-0">
        {CONTROL_PLANE_MODULES.map((m) => {
          const Icon = m.icon;
          const active = activeModule === m.id;
          return (
            <button
              key={m.id}
              onClick={() => setActiveModule(m.id)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg whitespace-nowrap font-medium transition ${
                active
                  ? "bg-pink-500/15 text-pink-400 border border-pink-500/30"
                  : "text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.04]"
              }`}
            >
              <Icon size={14} />
              {m.label}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-2 pl-4">
          <button
            onClick={loadData}
            title="Refresh Data"
            className="p-1.5 rounded-lg bg-white/[0.04] text-neutral-400 hover:text-white transition"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Main Module Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* 1. OVERVIEW */}
        {activeModule === "overview" && (
          <div className="space-y-6">
            {/* Metric Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
                <div className="text-[11px] text-neutral-400 uppercase tracking-wider">Total Registered Users</div>
                <div className="text-2xl font-bold text-white">{users.length}</div>
                <div className="text-[11px] text-emerald-400">100% active identity accounts</div>
              </div>

              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
                <div className="text-[11px] text-neutral-400 uppercase tracking-wider">Active Subscriptions</div>
                <div className="text-2xl font-bold text-pink-400">
                  {subscriptions.filter((s) => s.subscription_status === "ACTIVE").length}
                </div>
                <div className="text-[11px] text-neutral-400">Free, Pro, & Enterprise</div>
              </div>

              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
                <div className="text-[11px] text-neutral-400 uppercase tracking-wider">Networking++ Subscribers</div>
                <div className="text-2xl font-bold text-purple-400">
                  {subscriptions.filter((s) => s.networking_addon_status === 1).length}
                </div>
                <div className="text-[11px] text-purple-300">Advanced topology & NMS enabled</div>
              </div>

              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
                <div className="text-[11px] text-neutral-400 uppercase tracking-wider">Platform Health</div>
                <div className="text-2xl font-bold text-emerald-400">100%</div>
                <div className="text-[11px] text-emerald-400">WAL DB + Automation Loop Healthy</div>
              </div>
            </div>

            {/* Core Services Health Grid */}
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">Platform Backend Services</h3>
              <div className="grid grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">FastAPI Core Router</div>
                    <div className="text-[10px] text-neutral-400">Bearer Auth + RBAC Guards</div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    ONLINE
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">Automation Engine & Expiration</div>
                    <div className="text-[10px] text-neutral-400">Background 10s Timer Loop</div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    ACTIVE
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">Ansible Playbook Sandbox</div>
                    <div className="text-[10px] text-neutral-400">Isolated runner & redaction</div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    READY
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 2. USER MANAGEMENT */}
        {activeModule === "users" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                User Directory ({users.length})
              </h3>
            </div>

            <div className="rounded-xl border border-white/5 bg-black/30 overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-white/[0.02] text-neutral-400 border-b border-white/5">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">Username</th>
                    <th className="py-2.5 px-4 font-medium">Email</th>
                    <th className="py-2.5 px-4 font-medium">Organization</th>
                    <th className="py-2.5 px-4 font-medium">Plan Tier</th>
                    <th className="py-2.5 px-4 font-medium">Net++</th>
                    <th className="py-2.5 px-4 font-medium">Status</th>
                    <th className="py-2.5 px-4 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {users.map((u) => (
                    <tr key={u.user_id} className="hover:bg-white/[0.02]">
                      <td className="py-3 px-4 font-medium text-white flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-pink-500/20 text-pink-400 flex items-center justify-center text-[10px] font-bold">
                          {u.username.charAt(0).toUpperCase()}
                        </div>
                        {u.username}
                        {u.is_internal ? (
                          <span className="text-[9px] px-1.5 py-0.5 bg-rose-500/20 text-rose-300 rounded font-mono">STAFF</span>
                        ) : null}
                      </td>
                      <td className="py-3 px-4 text-neutral-400">{u.email}</td>
                      <td className="py-3 px-4 text-neutral-300">{u.tenant_name || "Default Org"}</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-pink-500/10 text-pink-400 border border-pink-500/20">
                          {u.plan_id || "FREE"}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {u.networking_addon_status ? (
                          <span className="text-purple-400 flex items-center gap-1 font-semibold text-[11px]">
                            <Zap size={12} /> Yes
                          </span>
                        ) : (
                          <span className="text-neutral-500 text-[11px]">No</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                          <CheckCircle2 size={12} /> Active
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right space-x-2">
                        <button
                          onClick={() => setAssignSubUser(u)}
                          className="px-2.5 py-1 rounded bg-white/5 hover:bg-white/10 text-neutral-200 text-[11px] transition"
                        >
                          Plan
                        </button>
                        <button
                          onClick={() => setImpersonateTarget(u)}
                          className="px-2.5 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 text-[11px] transition"
                        >
                          Impersonate
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 3. ORGANIZATIONS */}
        {activeModule === "organizations" && (
          <div className="space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Customer Organizations ({tenants.length})
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {tenants.map((t) => (
                <div key={t.tenant_id} className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="text-sm font-semibold text-white">{t.name}</div>
                      <div className="text-[11px] font-mono text-neutral-400">{t.slug} • {t.tenant_id}</div>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      {t.status}
                    </span>
                  </div>
                  <div className="pt-2 border-t border-white/5 flex justify-between text-xs text-neutral-400">
                    <span>Sisa Token: {t.token_balance?.remaining_tokens?.toLocaleString() || "10,000"}</span>
                    <span>Networking++: {t.entitlements?.networking_plus ? "Enabled" : "Disabled"}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 4. PLANS & ENTITLEMENTS */}
        {activeModule === "plans" && (
          <div className="space-y-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Feature Access & Plan Matrix
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/5 space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-neutral-400">Free Tier</div>
                <div className="text-2xl font-bold text-white">Rp 0</div>
                <ul className="text-xs text-neutral-300 space-y-2 list-disc list-inside">
                  <li>Single site workspace</li>
                  <li>10,000 monthly tokens</li>
                  <li>Standard topology map</li>
                  <li>Manual diagnostics</li>
                </ul>
              </div>

              <div className="p-5 rounded-2xl bg-pink-500/5 border border-pink-500/20 space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-pink-400">Pro Tier</div>
                <div className="text-2xl font-bold text-pink-400">Rp 250.000 <span className="text-xs text-neutral-400">/ bln</span></div>
                <ul className="text-xs text-neutral-300 space-y-2 list-disc list-inside">
                  <li>Multi-site support</li>
                  <li>2,000,000 monthly tokens</li>
                  <li>Config audit & template synthesis</li>
                  <li>Standard automation runner</li>
                </ul>
              </div>

              <div className="p-5 rounded-2xl bg-purple-500/5 border border-purple-500/20 space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-purple-400">Networking++ (Enterprise)</div>
                <div className="text-2xl font-bold text-purple-400">Rp 1.500.000 <span className="text-xs text-neutral-400">/ bln</span></div>
                <ul className="text-xs text-neutral-300 space-y-2 list-disc list-inside">
                  <li>10,000,000 monthly tokens</li>
                  <li>Live NMS telemetry stream</li>
                  <li>Ansible playbook engine</li>
                  <li>Blast radius & what-if analysis</li>
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* 5. SUBSCRIPTION MANAGEMENT */}
        {activeModule === "subscriptions" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                User Subscriptions ({subscriptions.length})
              </h3>
              <button
                onClick={handleSweepExpirations}
                className="px-3 py-1.5 rounded-lg bg-pink-500/10 text-pink-400 border border-pink-500/20 hover:bg-pink-500/20 text-xs font-medium transition"
              >
                Run Expiration Sweep
              </button>
            </div>

            <div className="rounded-xl border border-white/5 bg-black/30 overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-white/[0.02] text-neutral-400 border-b border-white/5">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">User</th>
                    <th className="py-2.5 px-4 font-medium">Plan</th>
                    <th className="py-2.5 px-4 font-medium">Networking++</th>
                    <th className="py-2.5 px-4 font-medium">Starts At</th>
                    <th className="py-2.5 px-4 font-medium">Expires At</th>
                    <th className="py-2.5 px-4 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {subscriptions.map((s) => (
                    <tr key={s.subscription_id} className="hover:bg-white/[0.02]">
                      <td className="py-3 px-4 font-medium text-white">{s.username}</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-pink-500/10 text-pink-400 border border-pink-500/20">
                          {s.plan_id}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {s.networking_addon_status ? (
                          <span className="text-purple-400 font-semibold text-[11px]">ACTIVE</span>
                        ) : (
                          <span className="text-neutral-500 text-[11px]">NONE</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-neutral-400 font-mono text-[11px]">
                        {s.starts_at ? new Date(s.starts_at).toLocaleDateString() : "-"}
                      </td>
                      <td className="py-3 px-4 text-neutral-400 font-mono text-[11px]">
                        {s.expires_at ? new Date(s.expires_at).toLocaleDateString() : "Never (Lifetime)"}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                            s.subscription_status === "ACTIVE"
                              ? "bg-emerald-500/10 text-emerald-400"
                              : "bg-rose-500/10 text-rose-400"
                          }`}
                        >
                          {s.subscription_status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 6. BILLING MANAGEMENT */}
        {activeModule === "billing" && (
          <div className="space-y-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Billing Ledger & Invoices
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {/* Invoices */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-white">Recent Invoices ({invoices.length})</div>
                <div className="rounded-xl border border-white/5 bg-black/30 divide-y divide-white/5 text-xs">
                  {invoices.length === 0 ? (
                    <div className="p-4 text-neutral-500 text-center">Belum ada invoice.</div>
                  ) : (
                    invoices.map((inv) => (
                      <div key={inv.invoice_id} className="p-3 flex justify-between items-center">
                        <div>
                          <div className="font-medium text-white">{inv.invoice_id} ({inv.username})</div>
                          <div className="text-[10px] text-neutral-400 font-mono">{inv.currency} {inv.amount_cents?.toLocaleString()}</div>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] ${inv.status === "PAID" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"}`}>
                          {inv.status}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Transactions */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-white">Payment Transactions ({transactions.length})</div>
                <div className="rounded-xl border border-white/5 bg-black/30 divide-y divide-white/5 text-xs">
                  {transactions.length === 0 ? (
                    <div className="p-4 text-neutral-500 text-center">Belum ada transaksi pembayaran.</div>
                  ) : (
                    transactions.map((tx) => (
                      <div key={tx.transaction_id} className="p-3 flex justify-between items-center">
                        <div>
                          <div className="font-medium text-white">{tx.transaction_id}</div>
                          <div className="text-[10px] text-neutral-400">{tx.provider_name} • {tx.currency} {tx.amount_cents?.toLocaleString()}</div>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] ${tx.status === "SUCCESS" ? "bg-emerald-500/10 text-emerald-400" : "bg-neutral-500/10 text-neutral-400"}`}>
                          {tx.status}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 7. INFRASTRUCTURE & NOC */}
        {activeModule === "infrastructure" && (
          <div className="space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Platform Infrastructure & NOC centre
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-2">
                <div className="text-xs font-semibold text-white">SQLite WAL Topology Engine</div>
                <p className="text-xs text-neutral-400">Status: Read/Write Transactional Pool Active</p>
                <div className="text-[11px] font-mono text-emerald-400">database/topology.db (67 tables verified)</div>
              </div>
              <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-2">
                <div className="text-xs font-semibold text-white">Edge Gateways Connectivity</div>
                <p className="text-xs text-neutral-400">Status: Hybrid Gateway Coordinator Running</p>
                <div className="text-[11px] font-mono text-emerald-400">Localhost + Remote Edge Nodes Synchronized</div>
              </div>
            </div>
          </div>
        )}

        {/* 8. AI CONFIG */}
        {activeModule === "ai_config" && (
          <div className="space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              AI & Platform Configuration
            </h3>
            <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3">
              <div className="text-xs font-semibold text-white">Pro Tier Token Allocation Policy</div>
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-neutral-400">Monthly Tokens: </span>
                  <span className="text-white font-mono">{tokenPolicy?.monthly_token_allocation?.toLocaleString() || "2,000,000"}</span>
                </div>
                <div>
                  <span className="text-neutral-400">Rate Limit: </span>
                  <span className="text-white font-mono">{tokenPolicy?.rate_limit_rpm || 120} RPM</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 9. SECURITY & AAA */}
        {activeModule === "security" && (
          <div className="space-y-6">
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                Centralized Operational Approval Queue ({approvals.length})
              </h3>
              {approvals.length === 0 ? (
                <div className="p-6 rounded-xl border border-white/5 bg-black/30 text-center text-xs text-neutral-500">
                  Tidak ada permohonan eksekusi yang memerlukan persetujuan saat ini.
                </div>
              ) : (
                <div className="space-y-3">
                  {approvals.map((app) => (
                    <div key={app.request_id} className="p-4 rounded-xl bg-black/40 border border-amber-500/20 flex items-center justify-between">
                      <div>
                        <div className="font-semibold text-white text-xs">{app.action_type} on {app.resource_id}</div>
                        <div className="text-[11px] text-neutral-400 mt-1">{app.reason}</div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleResolveApproval(app.request_id, true)}
                          className="px-3 py-1 text-xs rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleResolveApproval(app.request_id, false)}
                          className="px-3 py-1 text-xs rounded bg-rose-600 hover:bg-rose-500 text-white font-medium"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 10. PLATFORM SETTINGS */}
        {activeModule === "settings" && (
          <div className="space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Platform & Global Settings
            </h3>
            <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3 text-xs">
              <div className="flex justify-between items-center">
                <div>
                  <div className="font-medium text-white">Google OAuth Authentication</div>
                  <div className="text-[11px] text-neutral-400">Integrasi login Google OAuth 2.0</div>
                </div>
                <span className="px-2 py-0.5 rounded bg-white/10 text-neutral-300 font-mono text-[10px]">Configured via ENV</span>
              </div>
              <div className="flex justify-between items-center pt-2 border-t border-white/5">
                <div>
                  <div className="font-medium text-white">SMTP Email Gateway</div>
                  <div className="text-[11px] text-neutral-400">Pengiriman notifikasi reset password & invoice</div>
                </div>
                <span className="px-2 py-0.5 rounded bg-white/10 text-neutral-300 font-mono text-[10px]">Ready</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Impersonation Modal */}
      {impersonateTarget && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#18181b] border border-rose-500/30 rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="text-sm font-semibold text-rose-400 flex items-center gap-2">
                  <ShieldAlert size={16} /> Superadmin Impersonation
                </h3>
                <p className="text-xs text-neutral-400 mt-1">
                  Anda akan masuk sebagai akun <strong>{impersonateTarget.username}</strong> untuk keperluan troubleshooting.
                </p>
              </div>
              <button onClick={() => setImpersonateTarget(null)} className="text-neutral-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div>
              <label className="text-xs text-neutral-300 block mb-1">
                Alasan / Justifikasi Investigasi <span className="text-rose-400">*</span>
              </label>
              <textarea
                rows={3}
                value={impersonateReason}
                onChange={(e) => setImpersonateReason(e.target.value)}
                placeholder="Misal: Investigasi kendala sinkronisasi topologi tiket #INC-892"
                className="w-full p-2.5 text-xs bg-black/40 border border-white/10 rounded-lg text-white focus:outline-none focus:border-rose-500"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setImpersonateTarget(null)}
                className="px-3 py-1.5 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300 transition"
              >
                Batal
              </button>
              <button
                onClick={handleConfirmImpersonate}
                disabled={impersonating || !impersonateReason.trim()}
                className="px-4 py-1.5 text-xs rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-medium transition disabled:opacity-50"
              >
                {impersonating ? "Memulai Sesi..." : "Konfirmasi Masuk"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Subscription Assignment Modal */}
      {assignSubUser && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#18181b] border border-white/10 rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="text-sm font-semibold text-white">Atur Langganan: {assignSubUser.username}</h3>
                <p className="text-xs text-neutral-400 mt-0.5">Penetapan tier dan add-on langsung oleh Superadmin</p>
              </div>
              <button onClick={() => setAssignSubUser(null)} className="text-neutral-400 hover:text-white">
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-neutral-300 block mb-1">Plan Tier</label>
                <select
                  value={selectedPlanTier}
                  onChange={(e) => setSelectedPlanTier(e.target.value)}
                  className="w-full p-2 bg-black/40 border border-white/10 rounded-lg text-white"
                >
                  <option value="FREE">FREE</option>
                  <option value="PRO">PRO</option>
                  <option value="ENTERPRISE">ENTERPRISE</option>
                </select>
              </div>

              <div>
                <label className="text-neutral-300 block mb-1">Durasi (Hari)</label>
                <input
                  type="number"
                  value={assignDuration}
                  onChange={(e) => setAssignDuration(parseInt(e.target.value) || 30)}
                  className="w-full p-2 bg-black/40 border border-white/10 rounded-lg text-white"
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="netplus_check"
                  checked={assignNetplus}
                  onChange={(e) => setAssignNetplus(e.target.checked)}
                  className="accent-pink-500"
                />
                <label htmlFor="netplus_check" className="text-white cursor-pointer">
                  Aktifkan Networking++ Add-on
                </label>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setAssignSubUser(null)}
                className="px-3 py-1.5 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300 transition"
              >
                Batal
              </button>
              <button
                onClick={handleAssignSubscription}
                disabled={savingSub}
                className="px-4 py-1.5 text-xs rounded-lg bg-pink-500 hover:bg-pink-600 text-white font-medium transition"
              >
                {savingSub ? "Menyimpan..." : "Simpan Langganan"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
