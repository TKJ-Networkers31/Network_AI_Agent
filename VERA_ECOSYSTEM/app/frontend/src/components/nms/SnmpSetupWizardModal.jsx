// src/components/nms/SnmpSetupWizardModal.jsx
//
// Wizard Konfigurasi SNMP 5 Langkah Terpandu
// Membimbing administrator mengaktifkan dan memvalidasi monitoring SNMP
// pada perangkat MikroTik RouterOS dengan konfigurasi aman (read-only, terisolasi ke IP kolektor).

import { useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronRight,
  Copy,
  Cpu,
  HelpCircle,
  Loader2,
  Network,
  Radio,
  Server,
  Shield,
  ShieldCheck,
  X,
  Zap,
} from "lucide-react";

export default function SnmpSetupWizardModal({ device, onClose, onSuccess, pushToast }) {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // Form State
  const [host, setHost] = useState(device?.ip || "192.168.0.1");
  const [port, setPort] = useState(161);
  const [version, setVersion] = useState("v2c");
  const [community, setCommunity] = useState("aira-ro");
  const [collectorSubnet, setCollectorSubnet] = useState("192.168.0.0/24");
  const [useV3, setUseV3] = useState(false);
  const [v3User, setV3User] = useState("aira-mgr");
  const [v3AuthKey, setV3AuthKey] = useState("AiraAuthPass123");
  const [v3PrivKey, setV3PrivKey] = useState("AiraPrivPass123");

  // Step Results
  const [detectResult, setDetectResult] = useState(null);
  const [generatedCommands, setGeneratedCommands] = useState([]);
  const [verifyResult, setVerifyResult] = useState(null);

  // -------------------------------------------------------------------------
  // Langkah 1: Deteksi Akses SNMP Saat Ini
  // -------------------------------------------------------------------------
  const handleDetect = async () => {
    setLoading(true);
    setDetectResult(null);
    try {
      const res = await fetch("/api/nms/wizard/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ host, port: Number(port), community, version: useV3 ? "v3" : version }),
      });
      const json = await res.json();
      if (json.success) {
        setDetectResult(json.detection);
        if (json.detection.snmp_responding) {
          pushToast?.("SNMP aktif dan terdeteksi di perangkat!", "success");
        } else {
          pushToast?.(json.detection.message || "SNMP belum merespons.", "info");
        }
      } else {
        pushToast?.("Gagal melakukan deteksi SNMP.", "error");
      }
    } catch {
      pushToast?.("Gagal menghubungi endpoint deteksi SNMP.", "error");
    } finally {
      setLoading(false);
    }
  };

  // -------------------------------------------------------------------------
  // Langkah 3: Generate Perintah Konfigurasi RouterOS
  // -------------------------------------------------------------------------
  const handleGenerateCommands = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/nms/wizard/generate-commands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          community_name: community,
          allowed_collector_ip: collectorSubnet,
          use_v3: useV3,
          v3_user: v3User,
          v3_auth_key: v3AuthKey,
          v3_priv_key: v3PrivKey,
        }),
      });
      const json = await res.json();
      if (json.success) {
        setGeneratedCommands(json.commands || []);
        setStep(3);
      }
    } catch {
      pushToast?.("Gagal membuat perintah RouterOS.", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleCopyCommands = () => {
    const text = generatedCommands.join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    pushToast?.("Perintah disalin ke clipboard!", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  // -------------------------------------------------------------------------
  // Langkah 4: Uji dan Verifikasi Metrik
  // -------------------------------------------------------------------------
  const handleVerifyAndSave = async () => {
    setLoading(true);
    setVerifyResult(null);
    try {
      const res = await fetch("/api/nms/wizard/verify-and-save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: device.id,
          host,
          port: Number(port),
          community,
          version: useV3 ? "v3" : version,
        }),
      });
      const json = await res.json();
      if (json.success) {
        setVerifyResult(json);
        pushToast?.("Monitoring SNMP berhasil diverifikasi dan disimpan!", "success");
        setStep(5);
        onSuccess?.();
      } else {
        setVerifyResult(json);
        pushToast?.(json.error || "Verifikasi SNMP gagal.", "error");
      }
    } catch {
      pushToast?.("Gagal menghubungi endpoint verifikasi SNMP.", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl max-h-[90vh] flex flex-col bg-[#0b101b] border border-white/10 rounded-2xl shadow-2xl overflow-hidden text-white">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <ShieldCheck size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold">Wizard Konfigurasi SNMP</h2>
              <p className="text-xs text-white/50">
                Setup monitoring komprehensif untuk {device?.name || "Router"} ({host})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Stepper Progress Bar */}
        <div className="flex items-center justify-between px-6 py-3 bg-white/[0.01] border-b border-white/5 text-xs">
          {[
            { num: 1, label: "Deteksi" },
            { num: 2, label: "Kemampuan" },
            { num: 3, label: "Konfigurasi" },
            { num: 4, label: "Verifikasi" },
            { num: 5, label: "Aktif" },
          ].map((s, idx) => (
            <div key={s.num} className="flex items-center gap-2">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center font-medium text-[11px] ${
                  step === s.num
                    ? "bg-cyan-500 text-black font-bold shadow-sm shadow-cyan-500/50"
                    : step > s.num
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                    : "bg-white/5 text-white/40 border border-white/10"
                }`}
              >
                {step > s.num ? "✓" : s.num}
              </div>
              <span className={`hidden sm:inline ${step >= s.num ? "text-white" : "text-white/40"}`}>
                {s.label}
              </span>
              {idx < 4 && <ChevronRight size={14} className="text-white/20 ml-1" />}
            </div>
          ))}
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* STEP 1: DETEKSI */}
          {step === 1 && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-cyan-950/20 border border-cyan-500/30 text-xs text-cyan-200 leading-relaxed">
                <span className="font-semibold block mb-1">🔍 Langkah 1: Deteksi Akses Saat Ini</span>
                Memeriksa apakah port SNMP UDP 161 di perangkat sudah terbuka dan merespons query read-only.
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                <div>
                  <label className="block text-white/50 mb-1">Target Host / IP</label>
                  <input
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:border-cyan-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-white/50 mb-1">Port SNMP (UDP)</label>
                  <input
                    type="number"
                    value={port}
                    onChange={(e) => setPort(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:border-cyan-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-white/50 mb-1">Community String</label>
                  <input
                    value={community}
                    onChange={(e) => setCommunity(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:border-cyan-400 outline-none"
                    placeholder="mis. aira-ro"
                  />
                </div>
                <div>
                  <label className="block text-white/50 mb-1">Versi SNMP</label>
                  <select
                    value={version}
                    onChange={(e) => setVersion(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:border-cyan-400 outline-none"
                  >
                    <option value="v2c">SNMPv2c (Standar)</option>
                    <option value="v1">SNMPv1</option>
                  </select>
                </div>
              </div>

              <button
                onClick={handleDetect}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs transition shadow-lg shadow-cyan-500/20 disabled:opacity-50"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                <span>Uji Deteksi SNMP Sekarang</span>
              </button>

              {detectResult && (
                <div
                  className={`p-4 rounded-xl border text-xs space-y-2 ${
                    detectResult.snmp_responding
                      ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-200"
                      : "bg-amber-950/20 border-amber-500/30 text-amber-200"
                  }`}
                >
                  <div className="flex items-center gap-2 font-semibold">
                    {detectResult.snmp_responding ? (
                      <CheckCircle2 size={16} className="text-emerald-400" />
                    ) : (
                      <AlertCircle size={16} className="text-amber-400" />
                    )}
                    <span>{detectResult.message}</span>
                  </div>
                  {detectResult.sys_descr && (
                    <p className="font-mono text-[11px] text-white/80 bg-black/40 p-2 rounded-lg break-all">
                      {detectResult.sys_descr}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* STEP 2: PENJELASAN KEMAMPUAN */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-purple-950/20 border border-purple-500/30 text-xs text-purple-200 leading-relaxed">
                <span className="font-semibold block mb-1">📊 Langkah 2: Mengapa Memerlukan SNMP?</span>
                Monitoring dasar hanya memeriksa ICMP ping (UP/DOWN). Dengan mengaktifkan SNMP read-only, AIRA dapat mengumpulkan metrik performa mendalam:
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-1.5">
                  <div className="flex items-center gap-2 text-cyan-400 font-semibold">
                    <Cpu size={16} />
                    <span>CPU &amp; Memory Telemetry</span>
                  </div>
                  <p className="text-white/60 text-[11px]">
                    Memantau rata-rata beban prosesor per-core, penggunaan RAM, dan suhu operasional perangkat secara berkala.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-1.5">
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                    <Network size={16} />
                    <span>Interface Traffic &amp; Bandwidth</span>
                  </div>
                  <p className="text-white/60 text-[11px]">
                    Menghitung laju RX/TX bps real-time, utilisasi link port, serta mendeteksi packet error/discard.
                  </p>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-white/5 border border-white/10 text-xs space-y-2">
                <span className="font-semibold text-white">Kebijakan Keamanan:</span>
                <ul className="list-disc list-inside space-y-1 text-white/60 text-[11px]">
                  <li>Hanya menggunakan akses <span className="text-emerald-400 font-medium">Read-Only</span> (write-access=no).</li>
                  <li>Dibatasi hanya untuk subnet/IP manajemen server AIRA.</li>
                  <li>Komunitas bawaan 'public' wajib dinonaktifkan.</li>
                </ul>
              </div>
            </div>
          )}

          {/* STEP 3: GENERASI PERINTAH ROUTEROS */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-cyan-950/20 border border-cyan-500/30 text-xs text-cyan-200 leading-relaxed">
                <span className="font-semibold block mb-1">⚡ Langkah 3: Eksekusi Perintah di MikroTik</span>
                Jalankan perintah berikut di Terminal MikroTik (via Winbox, SSH, atau WebFig) untuk mengaktifkan SNMP read-only dengan aman:
              </div>

              <div className="relative">
                <pre className="p-4 rounded-xl bg-black/60 border border-white/10 text-xs text-cyan-300 font-mono overflow-x-auto leading-relaxed select-all">
                  {generatedCommands.join("\n")}
                </pre>
                <button
                  onClick={handleCopyCommands}
                  className="absolute top-3 right-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 text-xs transition font-medium"
                >
                  {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                  <span>{copied ? "Disalin!" : "Salin Perintah"}</span>
                </button>
              </div>

              <p className="text-[11px] text-white/50 italic">
                * Setelah mengeksekusi perintah di router, klik &ldquo;Lanjut ke Verifikasi&rdquo; di bawah untuk menguji metrik.
              </p>
            </div>
          )}

          {/* STEP 4: VERIFIKASI METRIK */}
          {step === 4 && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-purple-950/20 border border-purple-500/30 text-xs text-purple-200 leading-relaxed">
                <span className="font-semibold block mb-1">🔍 Langkah 4: Uji dan Verifikasi Metrik</span>
                Menguji pengambilan metrik nyata dari perangkat untuk memastikan bahwa konfigurasi SNMP berfungsi penuh sebelum diaktifkan dalam pemantauan berkala.
              </div>

              <button
                onClick={handleVerifyAndSave}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs transition shadow-lg shadow-emerald-500/20 disabled:opacity-50"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                <span>Verifikasi Metrik &amp; Simpan Profil</span>
              </button>

              {verifyResult && (
                <div
                  className={`p-4 rounded-xl border text-xs space-y-2 ${
                    verifyResult.success
                      ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-200"
                      : "bg-red-950/20 border-red-500/30 text-red-200"
                  }`}
                >
                  <div className="flex items-center gap-2 font-semibold">
                    {verifyResult.success ? (
                      <CheckCircle2 size={16} className="text-emerald-400" />
                    ) : (
                      <AlertCircle size={16} className="text-red-400" />
                    )}
                    <span>{verifyResult.message || verifyResult.error}</span>
                  </div>
                  {verifyResult.success && (
                    <div className="grid grid-cols-2 gap-2 pt-2 text-[11px] text-white/80">
                      <div>CPU Load: {verifyResult.cpu_load_percent ?? "-"}%</div>
                      <div>RAM Used: {verifyResult.memory_used_percent ?? "-"}%</div>
                      <div>Interfaces: {verifyResult.interfaces_count ?? 0} terdeteksi</div>
                      <div>Identity: {verifyResult.identity ?? host}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* STEP 5: SELESAI */}
          {step === 5 && (
            <div className="py-6 text-center space-y-3">
              <div className="w-14 h-14 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 mx-auto">
                <CheckCircle2 size={32} />
              </div>
              <h3 className="text-base font-semibold text-emerald-300">Monitoring Berhasil Dikonfigurasi!</h3>
              <p className="text-xs text-white/60 max-w-md mx-auto">
                Perangkat <span className="text-white font-medium">{device?.name}</span> sekarang berstatus{" "}
                <span className="text-cyan-400 font-medium">Managed</span>. Laju traffic antarmuka dan utilisasi resource akan dicatat otomatis secara berkala.
              </p>
            </div>
          )}
        </div>

        {/* Footer Navigation */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-white/10 bg-white/[0.02]">
          {step > 1 && step < 5 ? (
            <button
              onClick={() => setStep((s) => s - 1)}
              className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-white/70 hover:text-white text-xs transition"
            >
              Kembali
            </button>
          ) : (
            <div />
          )}

          {step === 1 && (
            <button
              onClick={() => setStep(2)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs transition"
            >
              <span>Lanjut ke Penjelasan</span>
              <ChevronRight size={14} />
            </button>
          )}

          {step === 2 && (
            <button
              onClick={handleGenerateCommands}
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs transition"
            >
              <span>Generate Perintah RouterOS</span>
              <ChevronRight size={14} />
            </button>
          )}

          {step === 3 && (
            <button
              onClick={() => setStep(4)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs transition"
            >
              <span>Lanjut ke Verifikasi</span>
              <ChevronRight size={14} />
            </button>
          )}

          {step === 5 && (
            <button
              onClick={onClose}
              className="px-5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs transition"
            >
              Selesai &amp; Tutup
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
