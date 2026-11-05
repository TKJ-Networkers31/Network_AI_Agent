// src/pages/GatewaysPage.jsx
//
// AIRA OS — Hybrid Edge Gateway Management Console (Networking VIII / WP 8.4.9)
// Provides internal NOC operators and customer administrators with real-time
// visibility into edge collector health, token onboarding, and gateway lifecycle management.

import React, { useState, useEffect, useCallback } from "react";
import {
  Radio,
  Plus,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Server,
  Key,
  Clock,
  Layers,
  Activity,
  Trash2,
  Eye,
  Copy,
  Check,
} from "lucide-react";

export default function GatewaysPage() {
  const [gateways, setGateways] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal states
  const [tokenModalOpen, setTokenModalOpen] = useState(false);
  const [inspectModalOpen, setInspectModalOpen] = useState(false);
  const [selectedGateway, setSelectedGateway] = useState(null);

  // New token form
  const [targetTenant, setTargetTenant] = useState("tenant_default");
  const [targetSite, setTargetSite] = useState("site_default");
  const [tokenDuration, setTokenDuration] = useState(15);
  const [generatedToken, setGeneratedToken] = useState(null);
  const [copied, setCopied] = useState(false);
  const [tokenLoading, setTokenLoading] = useState(false);

  const fetchGateways = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/v1/gateways");
      if (!res.ok) throw new Error(`HTTP error: ${res.status}`);
      const data = await res.json();
      setGateways(data.gateways || []);
    } catch (err) {
      console.error("Failed to load edge gateways:", err);
      setError("Gagal memuat daftar Edge Gateway.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGateways();
    const interval = setInterval(fetchGateways, 15000);
    return () => clearInterval(interval);
  }, [fetchGateways]);

  const handleGenerateToken = async (e) => {
    e.preventDefault();
    try {
      setTokenLoading(true);
      const res = await fetch("/api/v1/gateways/tokens", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: targetTenant,
          site_id: targetSite,
          duration_minutes: Number(tokenDuration),
        }),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Gagal membuat token");
      }
      const data = await res.json();
      setGeneratedToken(data);
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      setTokenLoading(false);
    }
  };

  const handleCopyToken = () => {
    if (generatedToken?.enrollment_token) {
      navigator.clipboard.writeText(generatedToken.enrollment_token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleRevoke = async (gatewayId) => {
    if (!window.confirm(`Revoke gateway '${gatewayId}'? Koneksi edge akan segera diputus.`)) {
      return;
    }
    try {
      const res = await fetch(`/api/v1/gateways/${gatewayId}/revoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Manual revocation by operator" }),
      });
      if (!res.ok) throw new Error("Gagal merevoke gateway");
      fetchGateways();
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  };

  // Summary counts
  const totalCount = gateways.length;
  const onlineCount = gateways.filter((g) => g.status === "ACTIVE").length;
  const revokedCount = gateways.filter((g) => g.status === "REVOKED").length;

  return (
    <div className="flex-1 flex flex-col h-full bg-neutral-950 text-neutral-100 overflow-y-auto p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between pb-6 border-b border-neutral-800/80 gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Radio className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                Edge Gateways Console
                <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-800 text-neutral-400 border border-neutral-700 font-mono">
                  WP 8.4
                </span>
              </h1>
              <p className="text-xs sm:text-sm text-neutral-400 mt-0.5">
                Hybrid customer premises telemetry collectors & outbound ingestion hub.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchGateways}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg bg-neutral-900 hover:bg-neutral-800 border border-neutral-800 text-neutral-300 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
            Refresh
          </button>
          <button
            onClick={() => {
              setGeneratedToken(null);
              setTokenModalOpen(true);
            }}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-600/20 transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            Generate Enrollment Token
          </button>
        </div>
      </div>

      {/* KPI Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 my-6">
        <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800">
          <span className="text-xs text-neutral-400 uppercase tracking-wider font-semibold">Total Gateways</span>
          <div className="text-2xl font-bold text-white mt-1">{totalCount}</div>
        </div>
        <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800">
          <span className="text-xs text-emerald-400 uppercase tracking-wider font-semibold flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            Active Online
          </span>
          <div className="text-2xl font-bold text-emerald-400 mt-1">{onlineCount}</div>
        </div>
        <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800">
          <span className="text-xs text-rose-400 uppercase tracking-wider font-semibold">Revoked / Offline</span>
          <div className="text-2xl font-bold text-rose-400 mt-1">{revokedCount}</div>
        </div>
        <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800">
          <span className="text-xs text-neutral-400 uppercase tracking-wider font-semibold">Transport Security</span>
          <div className="text-sm font-mono text-cyan-400 mt-2 flex items-center gap-1">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            TLS 1.3 / WSS
          </div>
        </div>
      </div>

      {/* Gateways Table */}
      <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 overflow-hidden shadow-xl">
        <div className="px-5 py-3.5 border-b border-neutral-800/80 bg-neutral-900/80 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-200 flex items-center gap-2">
            <Server className="w-4 h-4 text-cyan-400" />
            Enrolled Customer Edge Gateways
          </h2>
          <span className="text-xs text-neutral-500">{gateways.length} records</span>
        </div>

        {loading && gateways.length === 0 ? (
          <div className="p-12 text-center text-neutral-500 text-sm">
            <RefreshCw className="w-6 h-6 mx-auto mb-2 animate-spin text-cyan-500" />
            Memuat data Edge Gateways...
          </div>
        ) : error ? (
          <div className="p-8 text-center text-rose-400 text-sm flex flex-col items-center gap-2">
            <AlertTriangle className="w-6 h-6 text-rose-500" />
            {error}
          </div>
        ) : gateways.length === 0 ? (
          <div className="p-12 text-center text-neutral-500">
            <Radio className="w-8 h-8 mx-auto mb-3 text-neutral-600" />
            <p className="text-sm font-medium text-neutral-400">Belum ada Edge Gateway yang terdaftar.</p>
            <p className="text-xs text-neutral-600 mt-1">
              Klik "Generate Enrollment Token" untuk mendaftarkan gateway di jaringan pelanggan.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-900/90 text-neutral-400 uppercase text-[10px] tracking-wider border-b border-neutral-800">
                <tr>
                  <th className="py-3 px-4">Gateway</th>
                  <th className="py-3 px-4">Tenant / Site</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Version</th>
                  <th className="py-3 px-4">Last Seen</th>
                  <th className="py-3 px-4">IP Address</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800/60 font-mono">
                {gateways.map((gw) => (
                  <tr key={gw.gateway_id} className="hover:bg-neutral-800/30 transition-colors">
                    <td className="py-3 px-4 font-sans">
                      <div className="font-semibold text-neutral-200">{gw.name}</div>
                      <div className="text-[11px] text-neutral-500 font-mono">{gw.gateway_id}</div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="text-cyan-400">{gw.tenant_id}</div>
                      <div className="text-neutral-500 text-[11px]">{gw.site_id}</div>
                    </td>
                    <td className="py-3 px-4 font-sans">
                      {gw.status === "ACTIVE" ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          <CheckCircle2 className="w-3 h-3" /> Active
                        </span>
                      ) : gw.status === "REVOKED" ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
                          <XCircle className="w-3 h-3" /> Revoked
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                          <AlertTriangle className="w-3 h-3" /> {gw.status}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-neutral-400">v{gw.version}</td>
                    <td className="py-3 px-4 text-neutral-400">
                      {gw.last_seen_at_utc ? gw.last_seen_at_utc.replace("T", " ").replace("Z", "") : "Never"}
                    </td>
                    <td className="py-3 px-4 text-neutral-400">{gw.last_ip || "—"}</td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => {
                            setSelectedGateway(gw);
                            setInspectModalOpen(true);
                          }}
                          className="p-1.5 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
                          title="Inspect Gateway"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        {gw.status === "ACTIVE" && (
                          <button
                            onClick={() => handleRevoke(gw.gateway_id)}
                            className="p-1.5 rounded hover:bg-rose-950/40 text-neutral-400 hover:text-rose-400 transition-colors"
                            title="Revoke Gateway"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal: Generate Enrollment Token */}
      {tokenModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-lg rounded-2xl bg-neutral-900 border border-neutral-800 p-6 shadow-2xl">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Key className="w-5 h-5 text-cyan-400" />
              Generate Single-Use Gateway Enrollment Token
            </h3>
            <p className="text-xs text-neutral-400 mt-1">
              Token ini digunakan sekali oleh Edge Gateway untuk mendaftarkan diri secara mutual-authenticated.
            </p>

            {!generatedToken ? (
              <form onSubmit={handleGenerateToken} className="mt-4 space-y-4 text-xs font-sans">
                <div>
                  <label className="block text-neutral-300 font-medium mb-1">Target Tenant ID</label>
                  <input
                    type="text"
                    value={targetTenant}
                    onChange={(e) => setTargetTenant(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-200 font-mono focus:border-cyan-500 focus:outline-none"
                    placeholder="tenant_..."
                  />
                </div>
                <div>
                  <label className="block text-neutral-300 font-medium mb-1">Target Site ID</label>
                  <input
                    type="text"
                    value={targetSite}
                    onChange={(e) => setTargetSite(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-200 font-mono focus:border-cyan-500 focus:outline-none"
                    placeholder="site_..."
                  />
                </div>
                <div>
                  <label className="block text-neutral-300 font-medium mb-1">Validitas Token (Menit)</label>
                  <select
                    value={tokenDuration}
                    onChange={(e) => setTokenDuration(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-200 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value="15">15 Menit (Direkomendasikan)</option>
                    <option value="30">30 Menit</option>
                    <option value="60">1 Jam</option>
                  </select>
                </div>
                <div className="flex justify-end gap-2 pt-2 border-t border-neutral-800">
                  <button
                    type="button"
                    onClick={() => setTokenModalOpen(false)}
                    className="px-4 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-300 font-medium"
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    disabled={tokenLoading}
                    className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold flex items-center gap-1.5"
                  >
                    {tokenLoading ? "Membuat..." : "Buat Token"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="mt-4 space-y-4 text-xs font-sans">
                <div className="p-3.5 rounded-xl bg-cyan-950/40 border border-cyan-800/60">
                  <span className="text-[11px] text-cyan-400 font-semibold uppercase tracking-wider block mb-1">
                    Token Onboarding (Hanya Ditampilkan Sekali)
                  </span>
                  <div className="flex items-center justify-between gap-2 p-2 rounded bg-neutral-950 border border-neutral-800">
                    <span className="font-mono text-cyan-300 break-all select-all text-xs">
                      {generatedToken.enrollment_token}
                    </span>
                    <button
                      type="button"
                      onClick={handleCopyToken}
                      className="p-1.5 rounded hover:bg-neutral-800 text-neutral-300 flex-shrink-0"
                      title="Salin Token"
                    >
                      {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  <p className="text-[11px] text-neutral-400 mt-2">
                    Kadaluarsa pada: <span className="font-mono text-neutral-200">{generatedToken.expires_at_utc}</span>
                  </p>
                </div>
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => setTokenModalOpen(false)}
                    className="px-4 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 font-semibold"
                  >
                    Selesai
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal: Inspect Gateway */}
      {inspectModalOpen && selectedGateway && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-xl rounded-2xl bg-neutral-900 border border-neutral-800 p-6 shadow-2xl">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Server className="w-5 h-5 text-cyan-400" />
              Gateway Specification: {selectedGateway.name}
            </h3>
            <div className="mt-4 space-y-3 text-xs font-mono">
              <div className="grid grid-cols-2 gap-2 p-3 rounded-lg bg-neutral-950 border border-neutral-800">
                <div>
                  <span className="text-neutral-500 block text-[10px] uppercase">Gateway ID</span>
                  <span className="text-neutral-200">{selectedGateway.gateway_id}</span>
                </div>
                <div>
                  <span className="text-neutral-500 block text-[10px] uppercase">Tenant / Site</span>
                  <span className="text-cyan-400">{selectedGateway.tenant_id} / {selectedGateway.site_id}</span>
                </div>
                <div>
                  <span className="text-neutral-500 block text-[10px] uppercase">Version</span>
                  <span className="text-neutral-200">v{selectedGateway.version}</span>
                </div>
                <div>
                  <span className="text-neutral-500 block text-[10px] uppercase">Status</span>
                  <span className="text-emerald-400 font-semibold">{selectedGateway.status}</span>
                </div>
              </div>
              <div>
                <span className="text-neutral-500 block text-[10px] uppercase mb-1">Metadata</span>
                <pre className="p-3 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-400 text-[11px] overflow-x-auto max-h-40">
                  {JSON.stringify(selectedGateway.metadata || {}, null, 2)}
                </pre>
              </div>
            </div>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setInspectModalOpen(false)}
                className="px-4 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 font-semibold text-xs"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
