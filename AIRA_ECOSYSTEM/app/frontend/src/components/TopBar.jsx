import WsStatusBadge from "./WsStatusBadge.jsx";

export default function TopBar({ title, subtitle, onMenuClick, wsStatus }) {
  return (
    <div className="aira-topbar rounded-xl2 p-4 sm:p-5 mb-4 sm:mb-6 flex items-center justify-between overflow-hidden relative gap-3 shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="md:hidden shrink-0 w-9 h-9 flex items-center justify-center rounded-lg bg-white/10 border border-sky-200/20 text-white/85"
            aria-label="Buka menu sesi"
          >
            ☰
          </button>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-lg sm:text-2xl font-bold text-white truncate">
              {title || "Chat baru"}
            </h1>
            {wsStatus && <WsStatusBadge status={wsStatus} />}
          </div>
          {subtitle && (
            <p className="text-sky-100/70 text-xs sm:text-sm mt-1 truncate">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      <div className="aira-topbar-status shrink-0 rounded-xl border border-sky-100/20 bg-sky-100/10 px-3 py-2 text-right">
        <div className="text-[10px] sm:text-xs font-semibold uppercase tracking-[0.16em] text-sky-100/80">
          AIRA OS
        </div>
        <div className="text-[10px] sm:text-xs text-white/60 mt-1">
          AI workspace
        </div>
      </div>
    </div>
  );
}
