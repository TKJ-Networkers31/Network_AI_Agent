import { useMemo } from "react";
import { ACTIVITY_STATE, heroSubtitle, heroTitle, normalizeHeroContext } from "./cockpitContracts.js";

/**
 * Hero kompak dua baris, sepenuhnya dirender dari SATU objek `heroContext`:
 *
 *   heroContext = { displayName, timePeriod, workspaceLabel, connectionCount, activityState }
 *
 * Komponen ini tidak menerima string greeting/subtitle jadi. Teks disusun
 * dari context lewat heroTitle()/heroSubtitle() (cockpitContracts.js).
 * W4 mengisi `heroContext`; nilai yang hilang/rusak jatuh ke default aman.
 */
export default function DynamicHero({ heroContext }) {
  const ctx = useMemo(() => normalizeHeroContext(heroContext), [heroContext]);
  const working = ctx.activityState === ACTIVITY_STATE.WORKING;
  const maintenance = ctx.activityState === ACTIVITY_STATE.MAINTENANCE;

  return (
    <div className="px-3 sm:px-5 lg:px-6 py-2.5 min-w-0">
      <h2 className="text-base sm:text-lg font-semibold leading-snug text-[color:var(--ck-text)] truncate">
        {heroTitle(ctx)}
      </h2>
      <p className="text-xs sm:text-[13px] leading-snug text-[color:var(--ck-muted)] truncate flex items-center gap-1.5">
        {(working || maintenance) && (
          <span
            aria-hidden="true"
            className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
              working
                ? "bg-[color:var(--ck-accent)] motion-safe:animate-pulse"
                : "bg-[color:var(--ck-warn)]"
            }`}
          />
        )}
        <span className="truncate">{heroSubtitle(ctx)}</span>
      </p>
    </div>
  );
}
