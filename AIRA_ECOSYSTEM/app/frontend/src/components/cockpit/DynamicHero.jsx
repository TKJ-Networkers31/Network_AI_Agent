import { useMemo } from "react";
import { ACTIVITY_STATE, heroSubtitle, heroTitle, normalizeHeroContext } from "./cockpitContracts.js";

const NETWORK_WORK_STATUS = "network_work";

// heroModel = keluaran Greeting Resolver (W4): { greeting, subtitle, time_period, status }.
// Dipakai apa adanya. Tidak valid / tanpa greeting -> null -> jalur heroContext lama.
function readHeroModel(model) {
  if (!model || typeof model !== "object") return null;

  const greeting = typeof model.greeting === "string" ? model.greeting.trim() : "";
  if (!greeting) return null;

  const subtitle =
    typeof model.subtitle === "string" && model.subtitle.trim() ? model.subtitle.trim() : null;

  return { greeting, subtitle, status: typeof model.status === "string" ? model.status : null };
}

/**
 * Hero kompak dua baris.
 *
 *  - heroModel (disarankan): teks dirender APA ADANYA dari Greeting Resolver.
 *    Komponen ini tidak menghitung greeting, timezone, jumlah koneksi, atau state.
 *  - heroContext (jalur lama, tetap didukung): teks disusun lewat heroTitle()/heroSubtitle().
 *
 * Jika heroModel ada, heroContext diabaikan.
 */
export default function DynamicHero({ heroContext, heroModel }) {
  const model = useMemo(() => readHeroModel(heroModel), [heroModel]);
  const ctx = useMemo(() => (model ? null : normalizeHeroContext(heroContext)), [model, heroContext]);

  const title = model ? model.greeting : heroTitle(ctx);
  const subtitle = model ? model.subtitle : heroSubtitle(ctx);
  const working = model ? model.status === NETWORK_WORK_STATUS : ctx.activityState === ACTIVITY_STATE.WORKING;
  const maintenance = model ? false : ctx.activityState === ACTIVITY_STATE.MAINTENANCE;

  return (
    <div className="px-3 sm:px-5 lg:px-6 py-2.5 min-w-0">
      <h2 className="text-base sm:text-lg font-semibold leading-snug text-[color:var(--ck-text)] truncate">
        {title}
      </h2>
      {subtitle && (
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
          <span className="truncate">{subtitle}</span>
        </p>
      )}
    </div>
  );
}