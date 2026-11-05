// src/pages/OperationsPage.jsx
//
// AIRA OS — Proactive Network Operations Center (Networking VII / WP 7.10)
//
// Single pane of glass for:
// 1. Overview Scorecard
// 2. Predictive Operations & Saturation Horizons (WP 7.1)
// 3. Network Change Impact Simulator (WP 7.2)
// 4. Business Services & Dependency Intelligence (WP 7.3)
// 5. Operational Job Scheduler (WP 7.4)
// 6. Maintenance Calendar & RFC 5545 ICS Export (WP 7.5)
// 7. Proactive Incidents Board (WP 7.6)
// 8. Automated Reports Generator (WP 7.8)

import React, { useState, useEffect } from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  Compass,
  Download,
  FileText,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Shield,
  Sliders,
  TrendingUp,
  Zap,
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8000/api/operations";

export default function OperationsPage() {
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Data states
  const [predictiveReport, setPredictiveReport] = useState(null);
  const [services, setServices] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [jobRuns, setJobRuns] = useState([]);
  const [windows, setWindows] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [generatedReport, setGeneratedReport] = useState(null);

  // Simulation form state
  const [simTargetDevice, setSimTargetDevice] = useState("Core-1");
  const [simTargetEntity, setSimTargetEntity] = useState("sfp-sfpplus1");
  const [simChangeType, setSimChangeType] = useState("INTERFACE_DOWN");
  const [simResult, setSimResult] = useState(null);
  const [simulating, setSimulating] = useState(false);

  // Load overview data
  const loadOverviewData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [predRes, svcRes, jobRes, winRes, incRes] = await Promise.all([
        fetch(`${API_BASE}/predictive/overview`).then((r) => r.json()).catch(() => null),
        fetch(`${API_BASE}/services`).then((r) => r.json()).catch(() => []),
        fetch(`${API_BASE}/scheduler/jobs`).then((r) => r.json()).catch(() => []),
        fetch(`${API_BASE}/calendar/windows`).then((r) => r.json()).catch(() => []),
        fetch(`${API_BASE}/incidents`).then((r) => r.json()).catch(() => []),
      ]);
      setPredictiveReport(predRes);
      setServices(Array.isArray(svcRes) ? svcRes : []);
      setJobs(Array.isArray(jobRes) ? jobRes : []);
      setWindows(Array.isArray(winRes) ? winRes : []);
      setIncidents(Array.isArray(incRes) ? incRes : []);
    } catch (err) {
      setError(err.message || "Failed to load operational telemetry");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOverviewData();
  }, []);

  // Run change impact simulation
  const handleRunSimulation = async (e) => {
    e.preventDefault();
    setSimulating(true);
    try {
      const res = await fetch(`${API_BASE}/change-impact/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: `Simulation: ${simChangeType} on ${simTargetDevice} ${simTargetEntity}`,
          change_type: simChangeType,
          target_device: simTargetDevice,
          target_entity: simTargetEntity,
        }),
      });
      const data = await res.json();
      setSimResult(data);
    } catch (err) {
      alert("Simulation failed: " + err.message);
    } finally {
      setSimulating(false);
    }
  };

  // Run scheduled job now
  const handleTriggerJob = async (jobId) => {
    try {
      const res = await fetch(`${API_BASE}/scheduler/jobs/${jobId}/run`, { method: "POST" });
      const data = await res.json();
      alert(`Job run completed: ${data.status} (${data.duration_ms} ms)\n${data.result_summary}`);
      loadOverviewData();
    } catch (err) {
      alert("Job trigger failed: " + err.message);
    }
  };

  // Generate operational report
  const handleGenerateReport = async (period = "DAILY") => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/reports/generate?period=${period}`);
      const data = await res.json();
      setGeneratedReport(data);
    } catch (err) {
      alert("Report generation failed: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100 overflow-y-auto">
      {/* Header Bar */}
      <div className="bg-slate-800 border-b border-slate-700 px-6 py-4 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-20">
        <div>
          <div className="flex items-center gap-2">
            <Compass className="w-6 h-6 text-indigo-400" />
            <h1 className="text-xl font-bold tracking-tight text-white">Operations Center</h1>
            <span className="text-xs bg-indigo-500/20 text-indigo-300 font-semibold px-2 py-0.5 rounded border border-indigo-500/30">
              Networking VII
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Predictive operations, change impact simulations, service catalog & maintenance scheduler (Asia/Jakarta)
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadOverviewData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs font-medium transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <a
            href={`${API_BASE}/calendar/export.ics`}
            download="maintenance_windows.ics"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium transition shadow-sm"
          >
            <Download className="w-3.5 h-3.5" />
            Export ICS
          </a>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-slate-800/60 border-b border-slate-700/80 px-6 flex gap-1 overflow-x-auto text-xs font-medium">
        {[
          { id: "overview", label: "Overview", icon: Activity },
          { id: "predictive", label: "Predictive Forecasts", icon: TrendingUp },
          { id: "change_simulator", label: "Change Simulator", icon: Sliders },
          { id: "services", label: "Business Services", icon: Server },
          { id: "scheduler", label: "Job Scheduler", icon: Clock },
          { id: "calendar", label: "Maintenance Calendar", icon: Calendar },
          { id: "incidents", label: "Proactive Incidents", icon: Shield },
          { id: "reports", label: "Operational Reports", icon: FileText },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 border-b-2 transition whitespace-nowrap ${
                isActive
                  ? "border-indigo-400 text-indigo-300 bg-slate-800/80"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-600"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Main Content Area */}
      <div className="p-6 max-w-7xl mx-auto w-full space-y-6">
        {error && (
          <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-300 text-sm flex items-center gap-3">
            <AlertOctagon className="w-5 h-5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 1: OVERVIEW SCORECARD                                      */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
                <span className="text-xs text-slate-400 uppercase font-semibold">Service Health Score</span>
                <div className="text-3xl font-extrabold text-emerald-400 mt-2">
                  {services.length > 0
                    ? `${Math.round(
                        (services.filter((s) => s.status === "HEALTHY").length / services.length) * 100
                      )}%`
                    : "100%"}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  {services.filter((s) => s.status === "HEALTHY").length} of {services.length} services nominal
                </div>
              </div>

              <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
                <span className="text-xs text-slate-400 uppercase font-semibold">Predictive Warnings</span>
                <div className="text-3xl font-extrabold text-amber-400 mt-2">
                  {predictiveReport?.risk_counts?.WARNING || 0}
                </div>
                <div className="text-xs text-slate-400 mt-1">Breach projected in 1-7 days</div>
              </div>

              <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
                <span className="text-xs text-slate-400 uppercase font-semibold">Proactive Incidents</span>
                <div className="text-3xl font-extrabold text-indigo-400 mt-2">
                  {incidents.filter((i) => i.state !== "CLOSED").length}
                </div>
                <div className="text-xs text-slate-400 mt-1">Pre-impact mitigations active</div>
              </div>

              <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
                <span className="text-xs text-slate-400 uppercase font-semibold">Maintenance Windows</span>
                <div className="text-3xl font-extrabold text-sky-400 mt-2">
                  {windows.filter((w) => w.status === "SCHEDULED").length}
                </div>
                <div className="text-xs text-slate-400 mt-1">Scheduled in Asia/Jakarta</div>
              </div>
            </div>

            {/* Quick Status Lists */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-amber-400" />
                  Upcoming Capacity Horizons
                </h3>
                {predictiveReport?.projections && predictiveReport.projections.length > 0 ? (
                  <div className="space-y-3">
                    {predictiveReport.projections.slice(0, 4).map((p) => (
                      <div key={p.projection_id} className="p-3 bg-slate-900/60 rounded border border-slate-700/60 flex items-center justify-between text-xs">
                        <div>
                          <div className="font-medium text-slate-200">
                            {p.device_id} : {p.entity_id} ({p.metric_name})
                          </div>
                          <div className="text-slate-400 mt-0.5">
                            Rate: {p.slope_per_day}%/day | Horizon: {p.days_to_warning ? `${p.days_to_warning} days` : "Safe"}
                          </div>
                        </div>
                        <span className={`px-2 py-0.5 rounded font-semibold text-[11px] ${
                          p.risk_level === "CRITICAL" ? "bg-rose-500/20 text-rose-300" :
                          p.risk_level === "WARNING" ? "bg-amber-500/20 text-amber-300" :
                          "bg-emerald-500/20 text-emerald-300"
                        }`}>
                          {p.risk_level}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-400 py-6 text-center">
                    All interface and device metrics operate within safe headroom thresholds.
                  </div>
                )}
              </div>

              <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                  <Server className="w-4 h-4 text-indigo-400" />
                  Business Critical Services
                </h3>
                <div className="space-y-3">
                  {services.length > 0 ? (
                    services.slice(0, 4).map((s) => (
                      <div key={s.service_id} className="p-3 bg-slate-900/60 rounded border border-slate-700/60 flex items-center justify-between text-xs">
                        <div>
                          <div className="font-medium text-slate-200">{s.name}</div>
                          <div className="text-slate-400 mt-0.5">{s.criticality} | Team: {s.owner_team}</div>
                        </div>
                        <div className="text-right">
                          <span className="text-emerald-400 font-bold">{s.health_score}%</span>
                          <div className="text-[10px] text-slate-500">{s.status}</div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-slate-400 py-6 text-center">
                      No business services registered yet. Click Business Services tab to configure.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 2: PREDICTIVE FORECASTS                                    */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "predictive" && (
          <div className="space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-white mb-2">Predictive Horizon Analysis</h3>
              <p className="text-xs text-slate-400 mb-4">
                Forecasts saturation points across multi-window timelines using linear trend regressions and rolling median/MAD bounds.
              </p>

              {predictiveReport?.projections && predictiveReport.projections.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                      <tr>
                        <th className="p-3">Device / Entity</th>
                        <th className="p-3">Metric</th>
                        <th className="p-3">Current</th>
                        <th className="p-3">Growth / Day</th>
                        <th className="p-3">Warning Horizon</th>
                        <th className="p-3">Critical Horizon</th>
                        <th className="p-3">Confidence</th>
                        <th className="p-3">Risk Level</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700/60">
                      {predictiveReport.projections.map((p) => (
                        <tr key={p.projection_id} className="hover:bg-slate-700/30">
                          <td className="p-3 font-medium text-slate-200">{p.device_id} ({p.entity_id})</td>
                          <td className="p-3 text-slate-300">{p.metric_name}</td>
                          <td className="p-3 font-semibold text-slate-100">{p.current_value}%</td>
                          <td className="p-3 text-slate-300">{p.slope_per_day}%</td>
                          <td className="p-3 text-amber-300 font-medium">
                            {p.days_to_warning ? `${p.days_to_warning} days` : "N/A"}
                          </td>
                          <td className="p-3 text-rose-300 font-medium">
                            {p.days_to_critical ? `${p.days_to_critical} days` : "N/A"}
                          </td>
                          <td className="p-3 text-slate-400">{Math.round(p.confidence_score * 100)}% ({p.confidence_level})</td>
                          <td className="p-3">
                            <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                              p.risk_level === "CRITICAL" ? "bg-rose-500/20 text-rose-300" :
                              p.risk_level === "WARNING" ? "bg-amber-500/20 text-amber-300" :
                              p.risk_level === "WATCH" ? "bg-yellow-500/20 text-yellow-300" :
                              "bg-emerald-500/20 text-emerald-300"
                            }`}>
                              {p.risk_level}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-slate-400 text-xs">
                  No active predictive trends recorded. Telemetry history is clean and within nominal bounds.
                </div>
              )}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 3: CHANGE IMPACT SIMULATOR                                 */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "change_simulator" && (
          <div className="space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <Sliders className="w-4 h-4 text-indigo-400" />
                Pre-Change Analytical Simulation Workbench
              </h3>
              <p className="text-xs text-slate-400 mb-4">
                Execute safe, in-memory simulations against a deep-cloned topology graph. 100% read-only; no router changes.
              </p>

              <form onSubmit={handleRunSimulation} className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Scenario Type</label>
                  <select
                    value={simChangeType}
                    onChange={(e) => setSimChangeType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-xs text-slate-200"
                  >
                    <option value="INTERFACE_DOWN">Interface Down / Shutdown</option>
                    <option value="ROUTE_WITHDRAWAL">Route Withdrawal</option>
                    <option value="DEVICE_REBOOT">Device Reload / Reboot</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Target Device</label>
                  <input
                    type="text"
                    value={simTargetDevice}
                    onChange={(e) => setSimTargetDevice(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-xs text-slate-200"
                    placeholder="e.g. Core-1 or R-1"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Target Entity (Interface/CIDR)</label>
                  <input
                    type="text"
                    value={simTargetEntity}
                    onChange={(e) => setSimTargetEntity(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-xs text-slate-200"
                    placeholder="e.g. ether1 or 10.0.0.0/24"
                  />
                </div>

                <div className="sm:col-span-3">
                  <button
                    type="submit"
                    disabled={simulating}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium transition disabled:opacity-50 flex items-center gap-2"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    {simulating ? "Simulating In-Memory..." : "Simulate Change Blast Radius"}
                  </button>
                </div>
              </form>

              {simResult && (
                <div className="mt-6 border-t border-slate-700/80 pt-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-bold text-white">Simulation Assessment Results</h4>
                    <span className={`px-2.5 py-1 rounded text-xs font-bold ${
                      simResult.severity === "CRITICAL" ? "bg-rose-500/20 text-rose-300 border border-rose-500/40" :
                      simResult.severity === "HIGH" ? "bg-amber-500/20 text-amber-300 border border-amber-500/40" :
                      "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                    }`}>
                      Severity: {simResult.severity}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="p-4 bg-slate-900/60 rounded border border-slate-700/60">
                      <span className="font-semibold text-slate-300">Directly Impacted Devices:</span>
                      <div className="mt-1 text-slate-400">
                        {simResult.directly_impacted_devices?.length > 0
                          ? simResult.directly_impacted_devices.join(", ")
                          : "None (No direct peer severances)"}
                      </div>

                      <span className="font-semibold text-slate-300 block mt-3">Redundancy Losses:</span>
                      <div className="mt-1 text-rose-300">
                        {simResult.redundancy_losses?.length > 0
                          ? simResult.redundancy_losses.join(", ")
                          : "Zero single-point-of-failures introduced."}
                      </div>
                    </div>

                    <div className="p-4 bg-slate-900/60 rounded border border-slate-700/60">
                      <span className="font-semibold text-slate-300">Rollback Commands:</span>
                      <div className="mt-1 font-mono text-[11px] text-emerald-400 bg-slate-950 p-2 rounded">
                        {simResult.rollback_plan?.join("\n") || "No rollback commands required"}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 4: BUSINESS SERVICES                                       */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "services" && (
          <div className="space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-white">Business Services Catalog</h3>
                  <p className="text-xs text-slate-400">
                    Mappings from business applications down to endpoints, interfaces, and routers.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {services.map((svc) => (
                  <div key={svc.service_id} className="p-4 bg-slate-900/60 rounded border border-slate-700/60 space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-100 text-sm">{svc.name}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300">
                        {svc.status} ({svc.health_score}%)
                      </span>
                    </div>
                    <p className="text-slate-400">{svc.description}</p>
                    <div className="text-slate-300 flex items-center justify-between pt-2 border-t border-slate-800">
                      <span>Tier: <strong className="text-indigo-300">{svc.criticality}</strong></span>
                      <span>Owner: <strong>{svc.owner_team}</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 5: SCHEDULER & JOBS                                        */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "scheduler" && (
          <div className="space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-white mb-2">Operational Scheduled Jobs</h3>
              <p className="text-xs text-slate-400 mb-4">
                Timezone-aware (Asia/Jakarta) jobs executing maintenance reviews and compliance checks.
              </p>

              <div className="space-y-3">
                {jobs.map((job) => (
                  <div key={job.job_id} className="p-4 bg-slate-900/60 rounded border border-slate-700/60 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-bold text-slate-200 text-sm flex items-center gap-2">
                        {job.name}
                        <span className="text-[10px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400 font-mono">
                          {job.schedule_type}: {job.schedule_expression}
                        </span>
                      </div>
                      <div className="text-slate-400 mt-1">{job.description}</div>
                      <div className="text-[11px] text-slate-500 mt-1">
                        Next Due: {job.next_due_at ? new Date(job.next_due_at).toLocaleString() : "Manual only"} | Last Status: {job.last_status || "Never"}
                      </div>
                    </div>

                    <button
                      onClick={() => handleTriggerJob(job.job_id)}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium transition flex items-center gap-1.5"
                    >
                      <Play className="w-3 h-3" />
                      Run Now
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 6: MAINTENANCE CALENDAR                                    */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "calendar" && (
          <div className="space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-white mb-2">Maintenance Windows & RFC 5545 Calendar</h3>
              <p className="text-xs text-slate-400 mb-4">
                Active and scheduled maintenance windows. Telemetry collected during these intervals automatically suppresses alarms.
              </p>

              <div className="space-y-3">
                {windows.length > 0 ? (
                  windows.map((w) => (
                    <div key={w.window_id} className="p-4 bg-slate-900/60 rounded border border-slate-700/60 text-xs space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-100 text-sm">{w.title}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/20 text-sky-300">
                          {w.status}
                        </span>
                      </div>
                      <p className="text-slate-400">{w.description}</p>
                      <div className="flex items-center gap-4 text-slate-400 text-[11px] pt-1">
                        <span>Local (WIB): <strong>{w.start_time_local}</strong> to <strong>{w.end_time_local}</strong></span>
                        <span>Targets: {w.target_entities?.join(", ") || "Global"}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-slate-400 text-xs">
                    No scheduled maintenance windows found.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 7: PROACTIVE INCIDENTS                                     */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "incidents" && (
          <div className="space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-white mb-2">Proactive Incidents Board</h3>
              <p className="text-xs text-slate-400 mb-4">
                Automated preventative incident lifecycle triggered by predictive trend breaches.
              </p>

              <div className="space-y-3">
                {incidents.length > 0 ? (
                  incidents.map((inc) => (
                    <div key={inc.incident_id} className="p-4 bg-slate-900/60 rounded border border-slate-700/60 text-xs space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-200 text-sm">{inc.title}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300">
                          {inc.severity} - {inc.state}
                        </span>
                      </div>
                      <p className="text-slate-400">{inc.summary}</p>
                      {inc.remediation_plan && (
                        <div className="p-2 bg-slate-950 rounded text-emerald-400 font-mono text-[11px]">
                          Remediation: {inc.remediation_plan}
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-slate-400 text-xs">
                    Zero active proactive incidents. All services operating nominal.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* TAB 8: OPERATIONAL REPORTS                                     */}
        {/* ------------------------------------------------------------- */}
        {activeTab === "reports" && (
          <div className="space-y-6">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-white">Automated Operational Reports</h3>
                  <p className="text-xs text-slate-400">
                    Deterministic Markdown, JSON, and printable HTML operational reporting.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleGenerateReport("DAILY")}
                    className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium transition"
                  >
                    Daily Report
                  </button>
                  <button
                    onClick={() => handleGenerateReport("WEEKLY")}
                    className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-xs font-medium transition"
                  >
                    Weekly Report
                  </button>
                </div>
              </div>

              {generatedReport && (
                <div className="mt-4 p-4 bg-slate-950 rounded border border-slate-800 text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap">
                  {generatedReport.markdown}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
