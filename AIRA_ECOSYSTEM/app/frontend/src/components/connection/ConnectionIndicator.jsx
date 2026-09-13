import { useEffect, useState } from "react";
import { api } from "../../api.js";

function formatDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const hh = String(Math.floor(s / 3600)).padStart(2, "0");
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export default function ConnectionIndicator({ onClick }) {
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    let cancelled = false;

    function load() {
      api.connections
        .list()
        .then((res) => {
          if (!cancelled) setSessions(res.connections);
        })
        .catch(() => {});
    }

    load();
    const timer = setInterval(load, 3000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (sessions.length === 0) return null;

  const primary = sessions[0];
  const title =
    `Router : ${primary.device_name || primary.host}\n` +
    `Host : ${primary.host}\n` +
    `Duration : ${formatDuration(primary.uptime_seconds)}\n` +
    `Idle : ${formatDuration(primary.idle_seconds)}`;

  return (
    <button
      onClick={onClick}
      title={title}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs font-medium shrink-0"
    >
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 status-blink" />
      🟢 {primary.device_name || primary.host}
      {sessions.length > 1 && <span className="text-emerald-300/60">+{sessions.length - 1}</span>}
    </button>
  );
}