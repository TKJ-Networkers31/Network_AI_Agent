import StatusDot from "./StatusDot.jsx";
import { STATUS_META, normalizeConnection } from "./cockpitContracts.js";

/**
 * Lencana koneksi generik: ● R1  atau  ● R1 · SSH
 * Tidak mengenal protokol tertentu - `type` hanyalah label.
 *
 * Props: connection ({id,label,type,status,metadata?}) · showType · active · onClick(connection)
 */
export default function ConnectionBadge({ connection, showType = false, active = false, onClick }) {
  const c = normalizeConnection(connection);
  const typeLabel = c.type && c.type !== "generic" ? c.type.toUpperCase() : null;

  return (
    <button
      type="button"
      onClick={() => onClick?.(c)}
      aria-haspopup="dialog"
      aria-expanded={active}
      title={`${c.label}${typeLabel ? ` · ${typeLabel}` : ""} · ${STATUS_META[c.status].label}`}
      className={`shrink-0 inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md border text-xs font-medium transition
        focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[color:var(--ck-accent)]
        ${
          active
            ? "bg-[color:var(--ck-accent-soft)] border-[color:var(--ck-border-strong)] text-[color:var(--ck-text)]"
            : "bg-[color:var(--ck-surface)] border-[color:var(--ck-border)] text-[color:var(--ck-text)] hover:border-[color:var(--ck-border-strong)]"
        }`}
    >
      <StatusDot status={c.status} />
      <span>{c.label}</span>
      {showType && typeLabel && <span className="text-[color:var(--ck-muted)]">· {typeLabel}</span>}
    </button>
  );
}
