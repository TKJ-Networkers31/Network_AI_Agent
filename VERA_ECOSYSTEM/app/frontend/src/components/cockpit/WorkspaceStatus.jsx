import ActivityChip from "./ActivityChip.jsx";
import { normalizeActivity } from "./cockpitContracts.js";

/**
 * Ringkasan aktivitas runtime di sisi kanan dock (tidak menambah tinggi).
 *  - >= sm : sampai `maxVisible` chip + "+N"
 *  - < sm  : satu chip + "+N"
 * Props: activity: Activity[] · maxVisible (default 2)
 */
export default function WorkspaceStatus({ activity = [], maxVisible = 2 }) {
  const items = (Array.isArray(activity) ? activity : []).map((a, i) => normalizeActivity(a, i));

  if (items.length === 0) return null;

  const visible = items.slice(0, maxVisible);
  const hidden = items.length - visible.length;

  return (
    <div
      className="shrink-0 flex items-center gap-3 max-w-[55%] overflow-hidden"
      role="status"
      aria-live="polite"
      aria-label="Runtime activity"
    >
      {visible.map((a, i) => (
        <span key={a.targetId} className={i > 0 ? "hidden sm:inline-flex" : "inline-flex"}>
          <ActivityChip activity={a} />
        </span>
      ))}
      {hidden > 0 && <span className="text-xs text-[color:var(--ck-muted)]">+{hidden}</span>}
    </div>
  );
}
