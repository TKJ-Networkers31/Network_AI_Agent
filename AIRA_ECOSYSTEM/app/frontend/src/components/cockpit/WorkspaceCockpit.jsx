import { useMemo } from "react";
import ConnectionDock from "./ConnectionDock.jsx";
import WorkspaceStatus from "./WorkspaceStatus.jsx";
import DynamicHero from "./DynamicHero.jsx";
import ToolDock from "./ToolDock.jsx";
import { COCKPIT_VARS } from "./tokens.js";
import { activityFromConnections, buildHeroContext, normalizeConnection } from "./cockpitContracts.js";

function hasHeroModel(model) {
  return Boolean(model) && typeof model.greeting === "string" && model.greeting.trim() !== "";
}

/**
 * WorkspaceCockpit — instrumentasi kompak di ATAS percakapan.
 *
 *   [ dock koneksi 42px ............ aktivitas ]
 *   [ hero 2 baris (opsional) ]
 *   [ tool dock 1 baris (opsional) ]
 *
 * MURNI PRESENTASI: props masuk, callback keluar. Tidak ada fetch, polling,
 * timer, atau akses ChatRuntimeContext. Alur data yang benar:
 *   sumber state -> adapter (utils/cockpitAdapter.js + hooks/useCockpitData.js) -> props.
 *
 * Props data:
 *  - connections  : Connection[]   { id, label, type, status, metadata? }
 *  - activity     : Activity[]     { targetId, label, type, status }   (default: diturunkan dari connections)
 *  - runtimeState : { streaming, thinking }  PLACEHOLDER - diterima tapi belum dipakai
 *  - heroModel    : { greeting, subtitle, time_period, status } dari Greeting Resolver (W4).
 *                   Jika ada, dirender apa adanya oleh DynamicHero.
 *  - heroContext  : jalur lama { displayName, timePeriod, workspaceLabel, connectionCount, activityState }
 *                   (default: dibangun dari connections/activity, HANYA bila heroModel tidak ada)
 * Props UI:
 *  - tools, activeToolId, onToolSelect, iconRegistry
 *  - showHero (true) · showToolDock (true) · showType (false) · onOpenManager
 *  - bleed (true): margin negatif seperti TopBar/ChatInput; HARUS sama dengan
 *    padding halaman di App.jsx (px-3 sm:px-5 lg:px-6).
 */
export default function WorkspaceCockpit({
  connections = [],
  activity,
  // eslint-disable-next-line no-unused-vars
  runtimeState,
  heroContext,
  heroModel,
  tools = [],
  activeToolId = null,
  onToolSelect,
  iconRegistry,
  showHero = true,
  showToolDock = true,
  showType = false,
  onOpenManager,
  bleed = true,
  className = "",
}) {
  const normalized = useMemo(
    () => (Array.isArray(connections) ? connections : []).map((c, i) => normalizeConnection(c, i)),
    [connections]
  );

  const activityList = useMemo(
    () => (Array.isArray(activity) ? activity : activityFromConnections(normalized)),
    [activity, normalized]
  );

  const hero = useMemo(() => {
    // heroModel dirender apa adanya: konteks lama tidak perlu dibangun.
    if (hasHeroModel(heroModel)) return heroContext;

    return heroContext || buildHeroContext({ connections: normalized, activity: activityList });
  }, [heroModel, heroContext, normalized, activityList]);

  return (
    <section
      aria-label="AIRA cockpit"
      style={COCKPIT_VARS}
      className={`shrink-0 ${bleed ? "-mx-3 sm:-mx-5 lg:-mx-6" : ""} mb-2 sm:mb-3
        bg-[color:var(--ck-bg)] text-[color:var(--ck-text)] border-b border-[color:var(--ck-border)] ${className}`}
    >
      <div className="h-[42px] px-3 sm:px-5 lg:px-6 flex items-center justify-between gap-3 border-b border-[color:var(--ck-border)]">
        <ConnectionDock connections={normalized} showType={showType} onOpenManager={onOpenManager} />
        <WorkspaceStatus activity={activityList} />
      </div>

      {showHero && <DynamicHero heroContext={hero} heroModel={heroModel} />}

      {showToolDock && (
        <div className={showHero ? "" : "pt-2"}>
          <ToolDock tools={tools} activeId={activeToolId} onSelect={onToolSelect} iconRegistry={iconRegistry} />
        </div>
      )}
    </section>
  );
}