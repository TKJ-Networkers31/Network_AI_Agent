import { useEffect, useState } from "react";

function greeting(hour) {
  if (hour < 5) return "Good night!";
  if (hour < 11) return "Good morning!";
  if (hour < 15) return "Good afternoon!";
  if (hour < 19) return "Good evening!";
  return "Good night!";
}

export default function TopBar({ title, subtitle, onMenuClick }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000 * 15);
    return () => clearInterval(timer);
  }, []);

  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");

  return (
    <div className="rounded-xl2 bg-hero-gradient border border-border p-4 sm:p-6 mb-4 sm:mb-6 flex items-center justify-between overflow-hidden relative gap-3 shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="md:hidden shrink-0 w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 border border-border text-white/70"
            aria-label="Buka menu sesi"
          >
            ☰
          </button>
        )}
        <div className="min-w-0">
          <h1 className="text-lg sm:text-2xl font-bold text-white truncate">
            {title}
          </h1>
          {subtitle && (
            <p className="text-white/50 text-xs sm:text-sm mt-1 truncate">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-2xl sm:text-4xl font-extrabold tracking-tight text-white">
          {hh}:{mm}
        </div>
        <div className="text-white/50 text-[10px] sm:text-sm mt-1">
          {greeting(now.getHours())}
        </div>
      </div>
    </div>
  );
}