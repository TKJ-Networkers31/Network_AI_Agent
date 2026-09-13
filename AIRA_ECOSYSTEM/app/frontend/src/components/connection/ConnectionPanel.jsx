import { useEffect, useState } from "react";
import { api } from "../../api.js";
import { useToast } from "../Toast.jsx";

function formatClock(ts) {
  if (!ts) return "--:--:--";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("id-ID", { hour12: false });
}

function formatDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const hh = String(Math.floor(s / 3600)).padStart(2, "0");
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

const STATUS_STYLE = {
  connected: { dot: "bg-emerald-400", label: "🟢 Connected", text: "text-emerald-300" },
  busy: { dot: "bg-amber-400", label: "⏳ Menjalankan command...", text: "text-amber-300" },
  error: { dot: "bg-red-400", label: "🔴 Error", text: "text-red-300" },
  closed: { dot: "bg-white/30", label: "Closed", text: "text-white/40" },
};

function ConnectionCard({ session, onClose, closing }) {
  const style = STATUS_STYLE[session.status] || STATUS_STYLE.connected;

  return (
    <div className="bg-card border border-border rounded-xl2 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${style.dot}`} />
          <span className={`text-sm font-semibold ${style.text}`}>{style.label}</span>
        </div>
        <span className="text-xs text-white/40 font-mono">
          {session.device_name || session.host}
        </span>
      </div>

      <dl className="text-sm space-y-1.5">
        <div className="flex justify-between">
          <dt className="text-white/50">Host</dt>
          <dd className="text-white/90 font-mono">{session.host}:{session.port}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/50">Username</dt>
          <dd className="text-white/90">{session.username}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/50">Connected Since</dt>
          <dd className="text-white/90 font-mono">{formatClock(session.connected_at)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/50">Uptime</dt>
          <dd className="text-white/90 font-mono">{formatDuration(session.uptime_seconds)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-white/50">Idle</dt>
          <dd className="text-white/90 font-mono">{formatDuration(session.idle_seconds)}</dd>
        </div>
        {session.last_error && (
          <div className="flex justify-between gap-2">
            <dt className="text-red-300 shrink-0">Last Error</dt>
            <dd className="text-red-300 text-right truncate">{session.last_error}</dd>
          </div>
        )}
      </dl>

      <button
        onClick={() => onClose(session.session_id)}
        disabled={closing === session.session_id}
        className="w-full text-xs px-3 py-2 rounded-lg bg-red-500/10 text-red-300 hover:bg-red-500/20 border border-red-500/20 disabled:opacity-50"
      >
        {closing === session.session_id ? "Menutup..." : "Close Connection"}
      </button>
    </div>
  );
}

export default function ConnectionPanel({ autoRefresh = true }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState(null);
  const { notify } = useToast();

  function load() {
    api.connections
      .list()
      .then((res) => setSessions(res.connections))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    if (!autoRefresh) return undefined;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh]);

  async function handleClose(sessionId) {
    setClosing(sessionId);
    try {
      await api.connections.close(sessionId);
      notify({ type: "success", message: "Koneksi ditutup.", duration: 2500 });
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setClosing(null);
    }
  }

  if (loading) return <p className="text-white/40 text-sm">Memuat koneksi...</p>;

  if (sessions.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl2 p-6 text-center">
        <p className="text-white/40 text-sm">Tidak ada koneksi SSH aktif.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {sessions.map((s) => (
        <ConnectionCard key={s.session_id} session={s} onClose={handleClose} closing={closing} />
      ))}
    </div>
  );
}