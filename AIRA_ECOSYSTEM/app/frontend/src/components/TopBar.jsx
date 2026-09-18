// app/frontend/src/components/TopBar.jsx
// UI Redesign Sprint (Worker C) — same props (title, subtitle,
// onMenuClick, wsStatus), same WsStatusBadge import. Visual only.
//
// Note on scope: the reference brief's top bar shows a "Companion
// Selector" (center) and Export/Profile actions (right). Those aren't
// backed by a route or handler anywhere in the current app, so adding
// them here would be dead UI. Left as a follow-up once
// agents/rei model-switching (already in ModelsPage) or an export
// action is wired to a prop this component receives.

import { useEffect, useState } from "react";
import WsStatusBadge from "./WsStatusBadge.jsx";

function greeting(hour) {
  if (hour < 5) return "Good night!";
  if (hour < 11) return "Good morning!";
  if (hour < 15) return "Good afternoon!";
  if (hour < 19) return "Good evening!";
  return "Good night!";
}

export default function TopBar({ title, subtitle, onMenuClick, wsStatus }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000 * 15);
    return () => clearInterval(timer);
  }, []);

  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");

  return (
    <div className="rounded-card bg-surface/70 backdrop-blur-xl border border-border p-4 sm:p-5 mb-4 sm:mb-6 flex items-center justify-between overflow-hidden relative gap-3 shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="md:hidden shrink-0 w-9 h-9 flex items-center justify-center rounded-pill bg-white/5 border border-border text-text-secondary"
            aria-label="Buka menu sesi"
          >
            ☰
          </button>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-h2 font-semibold text-text-primary truncate">{title}</h1>
            {wsStatus && <WsStatusBadge status={wsStatus} />}
          </div>
          {subtitle && (
            <p className="text-text-secondary text-caption mt-1 truncate">{subtitle}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <div className="text-right">
          <div className="text-xl sm:text-2xl font-semibold tracking-tight text-text-primary">
            {hh}:{mm}
          </div>
          <div className="text-text-secondary text-caption">{greeting(now.getHours())}</div>
        </div>
      </div>
    </div>
  );
}