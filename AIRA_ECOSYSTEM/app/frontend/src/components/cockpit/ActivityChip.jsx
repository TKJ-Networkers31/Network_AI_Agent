import StatusDot from "./StatusDot.jsx";
import { STATUS_META, normalizeActivity } from "./cockpitContracts.js";

/**
 * Indikator aktivitas runtime (satu target), tinggi satu baris teks:
 *   ● R1 SSH     ◉ R2 SSH Running command     ○ OLT SERIAL Connecting     ◆ NetBox API Failed
 *
 * Murni presentasi: menerima Activity { targetId, label, type, status }.
 * Teks status hanya muncul untuk keadaan non-stabil agar tetap ringkas.
 */
export default function ActivityChip({ activity, showStatusText }) {
  const a = normalizeActivity(activity);
  const meta = STATUS_META[a.status];
  const statusText = showStatusText ?? (a.status !== "connected" && a.status !== "disconnected");
  const failed = a.status === "failed";

  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[color:var(--ck-text)] whitespace-nowrap">
      <StatusDot status={a.status} size={7} />
      <span className="font-medium">{a.label}</span>
      {a.type && a.type !== "generic" && (
        <span className="text-[color:var(--ck-muted)]">{a.type.toUpperCase()}</span>
      )}
      {statusText && (
        <span className={failed ? "text-[color:var(--ck-err)]" : "text-[color:var(--ck-muted)]"}>
          {meta.label}
        </span>
      )}
    </span>
  );
}
