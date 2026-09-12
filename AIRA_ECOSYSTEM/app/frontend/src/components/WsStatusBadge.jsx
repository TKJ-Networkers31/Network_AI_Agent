// AIRA_ECOSYSTEM/app/frontend/src/components/WsStatusBadge.jsx
const STATUS_CONFIG = {
  open:       { label: "Live",        dot: "bg-emerald-400", text: "text-emerald-300", blink: false },
  connecting: { label: "Menyambung…", dot: "bg-amber-400",   text: "text-amber-300",   blink: true },
  closed:     { label: "Terputus",    dot: "bg-red-400",     text: "text-red-300",     blink: true },
  idle:       { label: "Offline",     dot: "bg-white/30",    text: "text-white/40",    blink: false },
};

export default function WsStatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  return (
    <div
      title={`WebSocket: ${cfg.label}`}
      className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-white/5 border border-border shrink-0"
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} ${cfg.blink ? "status-blink" : ""}`} />
      <span className={`text-[10px] font-medium uppercase tracking-wide ${cfg.text}`}>
        {cfg.label}
      </span>
    </div>
  );
}