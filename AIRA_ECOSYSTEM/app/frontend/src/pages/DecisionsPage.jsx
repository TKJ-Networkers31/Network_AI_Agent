import React, { useState, useEffect, useCallback } from 'react';
import { 
  ShieldCheck, AlertTriangle, AlertCircle, CheckCircle2, 
  HelpCircle, RefreshCw, Eye, ArrowRight, Activity, 
  CheckSquare, History, Layers, Sliders, Play, X
} from 'lucide-react';

const STATUS_BADGES = {
  GENERATED: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  UNDER_REVIEW: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  APPROVED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  REJECTED: 'bg-red-500/10 text-red-400 border-red-500/20',
  DEFERRED: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  EXPIRED: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  COMPLETED: 'bg-teal-500/10 text-teal-400 border-teal-500/20',
  VERIFIED: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
};

const RISK_BADGES = {
  CRITICAL: 'text-red-400 bg-red-950/40 border-red-800/40',
  WARNING: 'text-amber-400 bg-amber-950/40 border-amber-800/40',
  WATCH: 'text-yellow-300 bg-yellow-950/30 border-yellow-800/30',
  INFO: 'text-blue-400 bg-blue-950/30 border-blue-800/30',
};

export default function DecisionsPage() {
  const [tenantId, setTenantId] = useState('tenant_default');
  const [decisions, setDecisions] = useState([]);
  const [healthSummary, setHealthSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedDecision, setSelectedDecision] = useState(null);
  const [decisionHistory, setDecisionHistory] = useState([]);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [showSimModal, setShowSimModal] = useState(false);
  const [simResults, setSimResults] = useState(null);
  const [simDevice, setSimDevice] = useState('');

  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/decisions?tenant_id=${encodeURIComponent(tenantId)}`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      setDecisions(data.decisions || []);

      // Fetch health summary
      const hRes = await fetch(`/api/v1/decisions/health/summary?tenant_id=${encodeURIComponent(tenantId)}`);
      if (hRes.ok) {
        const hData = await hRes.json();
        setHealthSummary(hData);
      }
    } catch (err) {
      setError(err.message || 'Gagal mengambil keputusan operasional');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    fetchDecisions();
  }, [fetchDecisions]);

  const handleTransition = async (decisionId, newStatus) => {
    const reason = prompt(`Masukkan alasan transisi ke ${newStatus}:`, 'Konfirmasi tindakan operasional');
    if (!reason) return;

    try {
      const res = await fetch(`/api/v1/decisions/${encodeURIComponent(decisionId)}/transition?tenant_id=${encodeURIComponent(tenantId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_status: newStatus, reason }),
      });
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || 'Gagal mengubah status keputusan');
      }
      fetchDecisions();
      if (selectedDecision && selectedDecision.decision_id === decisionId) {
        const updated = await res.json();
        setSelectedDecision(updated);
      }
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  };

  const openHistory = async (decisionId) => {
    try {
      const res = await fetch(`/api/v1/decisions/${encodeURIComponent(decisionId)}/history?tenant_id=${encodeURIComponent(tenantId)}`);
      if (res.ok) {
        const data = await res.json();
        setDecisionHistory(data.history || []);
        setShowHistoryModal(true);
      }
    } catch (err) {
      alert(`Gagal mengambil riwayat: ${err.message}`);
    }
  };

  const runSimulation = async () => {
    if (!simDevice.trim()) return;
    try {
      const res = await fetch('/api/v1/decisions/simulations/risk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId,
          failed_devices: [simDevice.trim()],
          scenario_name: `Simulasi Gangguan Perangkat ${simDevice}`,
        }),
      });
      if (!res.ok) throw new Error(`Simulasi gagal: ${res.status}`);
      const data = await res.json();
      setSimResults(data);
    } catch (err) {
      alert(err.message);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 text-slate-100">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-600/10 border border-blue-500/20 rounded-xl">
              <ShieldCheck className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Decision Center & Operational Support</h1>
              <p className="text-sm text-slate-400">
                Pusat Intelijen Keputusan Operasional, Skor Kesehatan Multi-Dimensi & Penilaian Risiko (WP 8.5)
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="text"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder="Tenant ID..."
            className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-blue-500 font-mono text-slate-200"
          />
          <button
            onClick={() => setShowSimModal(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-sm font-medium transition"
          >
            <Play className="w-4 h-4 text-amber-400" />
            Simulasi Kegagalan
          </button>
          <button
            onClick={fetchDecisions}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Segarkan
          </button>
        </div>
      </div>

      {/* Multi-Dimensional Health Overview */}
      {healthSummary && healthSummary.tenant_health && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Kesehatan Tenant</div>
              <div className="text-2xl font-bold mt-1 text-slate-100">
                {healthSummary.tenant_health.score !== null ? `${healthSummary.tenant_health.score.toFixed(1)}%` : 'N/A'}
              </div>
              <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded font-mono border ${
                healthSummary.tenant_health.state === 'HEALTHY' ? 'text-emerald-400 border-emerald-800/40 bg-emerald-950/20' :
                healthSummary.tenant_health.state === 'CRITICAL' ? 'text-red-400 border-red-800/40 bg-red-950/20' :
                'text-amber-400 border-amber-800/40 bg-amber-950/20'
              }`}>
                {healthSummary.tenant_health.state}
              </span>
            </div>
            <Activity className="w-8 h-8 text-blue-400/40" />
          </div>

          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Keputusan Aktif</div>
              <div className="text-2xl font-bold mt-1 text-slate-100">{decisions.length}</div>
              <div className="text-xs text-slate-400 mt-1">Siap ditinjau oleh operator</div>
            </div>
            <CheckSquare className="w-8 h-8 text-amber-400/40" />
          </div>

          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Tingkat Keyakinan</div>
              <div className="text-2xl font-bold mt-1 text-emerald-400">
                {(healthSummary.tenant_health.confidence * 100).toFixed(0)}%
              </div>
              <div className="text-xs text-slate-400 mt-1">Integritas data terverifikasi</div>
            </div>
            <ShieldCheck className="w-8 h-8 text-emerald-400/40" />
          </div>

          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Kebijakan Operasi</div>
              <div className="text-sm font-bold mt-1 text-slate-200">100% Read-Only Live Network</div>
              <div className="text-xs text-slate-400 mt-1">Mutasi live router diblokir</div>
            </div>
            <Layers className="w-8 h-8 text-indigo-400/40" />
          </div>
        </div>
      )}

      {/* Decisions List Table */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-3.5 border-b border-slate-800 flex justify-between items-center bg-slate-900/60">
          <h2 className="font-semibold text-slate-200">Daftar Keputusan Operasional yang Diprioritaskan</h2>
          <span className="text-xs text-slate-400">Diurutkan berdasarkan skor prioritas deterministik</span>
        </div>

        {error && (
          <div className="p-4 bg-red-950/20 border-b border-red-900/30 text-red-400 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/40 text-slate-400 uppercase text-xs font-semibold border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Prioritas</th>
                <th className="py-3 px-4">Judul Masalah</th>
                <th className="py-3 px-4">Tingkat Risiko</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Perangkat Terdampak</th>
                <th className="py-3 px-4">Epistemik</th>
                <th className="py-3 px-4 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-10 text-slate-500">
                    Tidak ada rekomendasi operasional terbuka saat ini untuk tenant ini.
                  </td>
                </tr>
              ) : (
                decisions.map((dec) => (
                  <tr key={dec.decision_id} className="hover:bg-slate-800/30 transition">
                    <td className="py-3 px-4 font-mono font-bold text-amber-400">
                      {dec.priority_score.toFixed(1)}
                    </td>
                    <td className="py-3 px-4">
                      <div className="font-medium text-slate-100">{dec.title}</div>
                      <div className="text-xs text-slate-400 font-mono">{dec.decision_id}</div>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-mono font-medium border ${RISK_BADGES[dec.risk_level] || 'text-slate-400'}`}>
                        {dec.risk_level}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-mono border ${STATUS_BADGES[dec.status] || 'text-slate-400'}`}>
                        {dec.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-xs font-mono text-slate-400">
                      {dec.affected_devices.length > 0 ? dec.affected_devices.join(', ') : '-'}
                    </td>
                    <td className="py-3 px-4 text-xs">
                      <span className={`px-1.5 py-0.5 rounded font-mono ${
                        dec.assessment.epistemic_status === 'CONFIRMED_BY_EVIDENCE' ? 'text-emerald-400 bg-emerald-950/20' :
                        dec.assessment.epistemic_status === 'HYPOTHESIS_SUPPORTED' ? 'text-blue-400 bg-blue-950/20' :
                        'text-amber-400 bg-amber-950/20'
                      }`}>
                        {dec.assessment.epistemic_status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <button
                        onClick={() => setSelectedDecision(dec)}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded border border-slate-700 transition"
                      >
                        Inspeksi
                      </button>
                      <button
                        onClick={() => openHistory(dec.decision_id)}
                        className="px-2 py-1 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 text-xs rounded border border-slate-800 transition"
                        title="Lihat Riwayat Transisi"
                      >
                        <History className="w-3.5 h-3.5 inline" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Decision Detail Modal */}
      {selectedDecision && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-6">
            <div className="flex justify-between items-start border-b border-slate-800 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-mono border ${STATUS_BADGES[selectedDecision.status]}`}>
                    {selectedDecision.status}
                  </span>
                  <span className="text-xs text-slate-400 font-mono">ID: {selectedDecision.decision_id}</span>
                </div>
                <h2 className="text-xl font-bold mt-1 text-slate-100">{selectedDecision.title}</h2>
              </div>
              <button onClick={() => setSelectedDecision(null)} className="text-slate-400 hover:text-slate-100">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Assessment Section */}
            <div className="p-4 bg-slate-950/40 border border-slate-800 rounded-lg space-y-3">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-blue-400" />
                Penilaian Berbasis Bukti (Evidence Assessment)
              </h3>
              <p className="text-sm text-slate-300">{selectedDecision.assessment.problem_statement}</p>

              {selectedDecision.assessment.root_cause_hypotheses.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Hipotesis Akar Masalah (RCA)</div>
                  <div className="space-y-1.5">
                    {selectedDecision.assessment.root_cause_hypotheses.map((h, idx) => (
                      <div key={idx} className="p-2.5 bg-slate-900/80 border border-slate-800 rounded text-xs flex justify-between items-center">
                        <div>
                          <span className="font-semibold text-slate-200">{h.title}</span>
                          <p className="text-slate-400 mt-0.5">{h.summary}</p>
                        </div>
                        <span className="font-mono text-amber-400">{(h.probability * 100).toFixed(0)}% prob</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs pt-2">
                <div>
                  <span className="text-slate-400">Bukti Pendukung: </span>
                  <span className="font-mono text-emerald-400">
                    {selectedDecision.assessment.supporting_evidence_ids.length} bukti
                  </span>
                </div>
                <div>
                  <span className="text-slate-400">Bukti Kurang / Belum Ada: </span>
                  <span className="font-mono text-amber-400">
                    {selectedDecision.assessment.missing_evidence_ids.length > 0 ? selectedDecision.assessment.missing_evidence_ids.join(', ') : 'Lengkap'}
                  </span>
                </div>
              </div>
            </div>

            {/* Recommendations & Safest Action */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Tindakan Teraman yang Direkomendasikan
              </h3>
              <div className="p-3.5 bg-emerald-950/20 border border-emerald-800/40 rounded-lg text-sm text-emerald-200">
                {selectedDecision.recommendation.safest_action}
              </div>

              {/* Alternatives */}
              {selectedDecision.recommendation.alternatives.length > 0 && (
                <div className="space-y-2 pt-2">
                  <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Alternatif Solusi</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {selectedDecision.recommendation.alternatives.map((alt) => (
                      <div key={alt.alternative_id} className="p-3 bg-slate-950/50 border border-slate-800 rounded-lg text-xs space-y-1">
                        <div className="font-semibold text-slate-200 flex justify-between">
                          <span>{alt.title}</span>
                          {alt.is_preferred && <span className="text-emerald-400 font-mono">(Paling Disarankan)</span>}
                        </div>
                        <p className="text-slate-400">{alt.description}</p>
                        <div className="text-slate-500 pt-1">
                          Tradeoff: {alt.tradeoffs.join('; ')}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Human Verification Checklist */}
              {selectedDecision.recommendation.human_verification_checklist.length > 0 && (
                <div className="p-3 bg-slate-950/30 border border-slate-800 rounded-lg space-y-2 text-xs">
                  <div className="font-semibold text-slate-300">Daftar Verifikasi Operator (Human Checklist):</div>
                  <ul className="list-disc list-inside space-y-1 text-slate-400">
                    {selectedDecision.recommendation.human_verification_checklist.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Transition Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-4">
              <span className="text-xs text-slate-400">
                Transisi State Terikat: Hanya operator terotentikasi yang dapat menyetujui.
              </span>
              <div className="flex items-center gap-2">
                {selectedDecision.status === 'GENERATED' && (
                  <button
                    onClick={() => handleTransition(selectedDecision.decision_id, 'UNDER_REVIEW')}
                    className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded text-xs font-medium transition"
                  >
                    Tinjau (Under Review)
                  </button>
                )}
                {selectedDecision.status === 'UNDER_REVIEW' && (
                  <>
                    <button
                      onClick={() => handleTransition(selectedDecision.decision_id, 'APPROVED')}
                      className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium transition"
                    >
                      Setujui (Approve)
                    </button>
                    <button
                      onClick={() => handleTransition(selectedDecision.decision_id, 'DEFERRED')}
                      className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-xs font-medium transition"
                    >
                      Tunda (Defer)
                    </button>
                    <button
                      onClick={() => handleTransition(selectedDecision.decision_id, 'REJECTED')}
                      className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded text-xs font-medium transition"
                    >
                      Tolak (Reject)
                    </button>
                  </>
                )}
                {selectedDecision.status === 'APPROVED' && (
                  <button
                    onClick={() => handleTransition(selectedDecision.decision_id, 'COMPLETED')}
                    className="px-3 py-1.5 bg-teal-600 hover:bg-teal-500 text-white rounded text-xs font-medium transition"
                  >
                    Tandai Selesai (Complete)
                  </button>
                )}
                {selectedDecision.status === 'COMPLETED' && (
                  <button
                    onClick={() => handleTransition(selectedDecision.decision_id, 'VERIFIED')}
                    className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium transition"
                  >
                    Verifikasi Hasil (Verify)
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* History Modal */}
      {showHistoryModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <h3 className="font-semibold text-slate-100 flex items-center gap-2">
                <History className="w-4 h-4 text-blue-400" />
                Audit Trail Riwayat Transisi Keputusan
              </h3>
              <button onClick={() => setShowHistoryModal(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {decisionHistory.map((h) => (
                <div key={h.history_id} className="p-3 bg-slate-950/60 border border-slate-800 rounded-lg text-xs space-y-1">
                  <div className="flex justify-between items-center text-slate-300">
                    <span className="font-mono text-blue-400">{h.from_status} &rarr; {h.to_status}</span>
                    <span className="text-slate-500 font-mono">{h.created_at}</span>
                  </div>
                  <div className="text-slate-400">Aktor: <span className="text-slate-200 font-semibold">{h.actor}</span></div>
                  <div className="text-slate-300 italic">Alasan: {h.reason}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Virtual Failure Simulation Modal */}
      {showSimModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <h3 className="font-semibold text-slate-100 flex items-center gap-2">
                <Play className="w-4 h-4 text-amber-400" />
                Simulasi Kegagalan Virtual Non-Destruktif
              </h3>
              <button onClick={() => { setShowSimModal(false); setSimResults(null); }} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              <p className="text-xs text-slate-400">
                Simulasi ini berjalan secara virtual pada NetworkKnowledgeGraph tanpa mengubah konfigurasi live perangkat atau membuat duplikat memori graph.
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="ID Perangkat (misal: dev_core_01)..."
                  value={simDevice}
                  onChange={(e) => setSimDevice(e.target.value)}
                  className="flex-1 px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-amber-500"
                />
                <button
                  onClick={runSimulation}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-medium transition"
                >
                  Jalankan
                </button>
              </div>

              {simResults && (
                <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-lg space-y-2.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-slate-200">Skor Risiko Terhitung:</span>
                    <span className="font-mono font-bold text-amber-400 text-base">{simResults.risk_score.toFixed(1)} / 100</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Perangkat Terdampak Langsung: </span>
                    <span className="font-mono text-slate-200">{simResults.directly_affected_devices.join(', ') || 'None'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Perangkat Dependensi Transit Terputus: </span>
                    <span className="font-mono text-red-400">{simResults.transit_dependent_devices.join(', ') || 'None'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Layanan Bisnis Terimbas: </span>
                    <span className="font-mono text-amber-300">{simResults.affected_services.join(', ') || 'None'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Ketersediaan Redundansi: </span>
                    <span className={`font-mono font-semibold ${simResults.has_redundancy ? 'text-emerald-400' : 'text-red-400'}`}>
                      {simResults.has_redundancy ? 'Ada (Jalur Cadangan Aktif)' : 'Tidak Ada (Titik Kegagalan Tunggal)'}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
