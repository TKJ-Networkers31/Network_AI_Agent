// src/components/TopBar.jsx
//
// PERUBAHAN (UI Layout): bar menempel ke tepi atas/kiri/kanan area konten (full-bleed), sticky.
// - -mx-3 sm:-mx-5 lg:-mx-6 HARUS sama dengan padding horizontal wrapper halaman di App.jsx.
//
// PERUBAHAN (Sprint 2.6 / W5):
// - Prop `hideConnectionIndicator`: dipakai ChatPage karena WorkspaceCockpit sudah
//   menampilkan ConnectionDock. Komponen ConnectionIndicator TIDAK dihapus; halaman
//   lain tetap menampilkannya seperti biasa.
// - Label sapaan memakai periode dari util W4 (buildGreetingContext) dengan timezone
//   dari Global Settings, bukan jam timezone browser. Jam (hh:mm) di kanan tetap
//   jam lokal perangkat.

import { useEffect, useMemo, useState } from "react";
import { Menu } from "lucide-react";
import WsStatusBadge from "./WsStatusBadge.jsx";
import ConnectionIndicator from "./connection/ConnectionIndicator.jsx";
import { useGlobalSettings } from "../hooks/useGlobalSettings.js";
import { TIME_PERIOD, buildGreetingContext } from "../utils/greetingContext.js";

const GREETING_LABEL = {
  [TIME_PERIOD.MORNING]: "Good morning!",
  [TIME_PERIOD.AFTERNOON]: "Good afternoon!",
  [TIME_PERIOD.EVENING]: "Good evening!",
  [TIME_PERIOD.NIGHT]: "Good night!",
};

function goToAkane() {
  window.dispatchEvent(new CustomEvent("aira:navigate", { detail: "akane" }));
}

export default function TopBar({
  title,
  subtitle,
  onMenuClick,
  wsStatus,
  hideConnectionIndicator = false,
}) {
  const [now, setNow] = useState(new Date());
  const settings = useGlobalSettings();

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000 * 15);
    return () => clearInterval(timer);
  }, []);

  const period = useMemo(() => buildGreetingContext({ settings, now }).time_period, [settings, now]);

  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");

  return (
    <header className="sticky top-0 z-30 shrink-0 -mx-3 sm:-mx-5 lg:-mx-6 mb-3 sm:mb-4 bg-surface/80 backdrop-blur-xl border-b border-border">
      <div className="h-14 px-3 sm:px-5 lg:px-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {onMenuClick && (
            <button
              onClick={onMenuClick}
              className="md:hidden shrink-0 w-9 h-9 flex items-center justify-center rounded-control bg-white/5 border border-border text-text-secondary hover:text-text-primary transition"
              aria-label="Buka menu"
            >
              <Menu size={18} strokeWidth={1.9} />
            </button>
          )}

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-semibold text-text-primary truncate leading-tight">
                {title}
              </h1>
              {wsStatus && <WsStatusBadge status={wsStatus} />}
            </div>
            {subtitle && (
              <p className="text-text-secondary text-[11px] sm:text-xs truncate leading-tight mt-0.5">
                {subtitle}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {!hideConnectionIndicator && <ConnectionIndicator onClick={goToAkane} />}

          <div className="text-right leading-tight">
            <div className="text-base sm:text-lg font-semibold tracking-tight text-text-primary tabular-nums">
              {hh}:{mm}
            </div>
            <div className="hidden sm:block text-text-secondary text-[11px]">
              {GREETING_LABEL[period] || "Hello!"}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}