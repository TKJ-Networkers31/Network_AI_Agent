import { useMemo } from "react";
import ConnectionDock from "./ConnectionDock.jsx";
import WorkspaceStatus from "./WorkspaceStatus.jsx";
import ToolDock from "./ToolDock.jsx";
import { COCKPIT_VARS } from "./tokens.js";
import { activityFromConnections, normalizeConnection } from "./cockpitContracts.js";

/**
 * ComposerCockpit — Sprint 2.6 post-integration UI fix.
 *
 * The instrument row (connections + activity + tools) used to live at the
 * TOP of the page, directly under TopBar, as part of WorkspaceCockpit. Per
 * the "Composer Cockpit" design intent, it now sits directly ABOVE
 * ChatInput, as part of the composer - not as a page header.
 *
 * DynamicHero (the greeting) stays in the conversation area and is NOT
 * part of this component - it is rendered separately by ChatPage, exactly
 * where the old inline "Hero" welcome screen used to live.
 *
 * Pure presentation, same data contract as WorkspaceCockpit's dock +
 * tool dock (no fetch/polling/WebSocket of its own - everything comes
 * from useCockpitData()/cockpitAdapter.js via props, same as before).
 */
export default function ComposerCockpit({
  connections = [],
  activity,
  tools = [],
  activeToolId = null,
  onToolSelect,
  iconRegistry,
  showToolDock = true,
  showType = false,
  onOpenManager,
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

  return (
    <section
      aria-label="AIRA composer cockpit"
      style={COCKPIT_VARS}
      className={`shrink-0 -mx-3 sm:-mx-5 lg:-mx-6
        bg-[color:var(--ck-bg)] text-[color:var(--ck-text)]
        border-t border-[color:var(--ck-border)] ${className}`}
    >
      <div className="h-[38px] px-3 sm:px-5 lg:px-6 flex items-center justify-between gap-3">
        <ConnectionDock connections={normalized} showType={showType} onOpenManager={onOpenManager} />
        <WorkspaceStatus activity={activityList} />
      </div>

      {showToolDock && (
        <ToolDock tools={tools} activeId={activeToolId} onSelect={onToolSelect} iconRegistry={iconRegistry} />
      )}
    </section>
  );
}