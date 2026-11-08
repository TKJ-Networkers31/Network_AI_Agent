import { useEffect, useMemo, useRef, useState } from "react";
import ConnectionBadge from "./ConnectionBadge.jsx";
import StatusDot from "./StatusDot.jsx";
import { STATUS_META, normalizeConnection } from "./cockpitContracts.js";

function formatIdle(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

function humanizeKey(key) {
  const spaced = String(key).replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

// Metadata generik: hanya nilai primitif; tidak ada asumsi soal SSH.
function metadataRows(connection) {
  return Object.entries(connection.metadata)
    .filter(([key, value]) => typeof value !== "object" && !(key === "protocol" && value === connection.type))
    .map(([key, value]) => ({
      label: key === "idleSeconds" ? "Idle" : humanizeKey(key),
      value: key === "idleSeconds" ? formatIdle(value) : String(value),
    }));
}

function defaultOpenManager() {
  // Konvensi yang sudah ada (TopBar.jsx / App.jsx): event "aira:navigate".
  window.dispatchEvent(new CustomEvent("aira:navigate", { detail: "akane" }));
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-[color:var(--ck-muted)]">{label}</dt>
      <dd className="text-[color:var(--ck-text)] font-mono text-right break-all">{value}</dd>
    </div>
  );
}

function ConnectionPopover({ connection, onClose, onOpenManager }) {
  const rows = metadataRows(connection);

  return (
    <div
      role="dialog"
      aria-label={`Detail koneksi ${connection.label}`}
      className="absolute left-0 top-full mt-1.5 z-40 w-64 max-w-[calc(100vw-1.5rem)] rounded-lg border p-3 shadow-xl
        bg-[color:var(--ck-surface-2)] border-[color:var(--ck-border-strong)]"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <StatusDot status={connection.status} />
          <span className="text-sm font-semibold text-[color:var(--ck-text)] truncate">{connection.label}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Tutup"
          className="text-xs text-[color:var(--ck-muted)] hover:text-[color:var(--ck-text)]"
        >
          Close
        </button>
      </div>

      <dl className="text-xs space-y-1">
        <Row label="Status" value={STATUS_META[connection.status].label} />
        {connection.type !== "generic" && <Row label="Type" value={connection.type.toUpperCase()} />}
        {rows.map((r) => (
          <Row key={r.label} label={r.label} value={r.value} />
        ))}
      </dl>

      <button
        type="button"
        onClick={onOpenManager}
        className="mt-3 w-full h-7 rounded-md text-xs font-medium border transition
          border-[color:var(--ck-border-strong)] text-[color:var(--ck-accent)] hover:bg-[color:var(--ck-accent-soft)]"
      >
        Manage connections
      </button>
    </div>
  );
}

/**
 * Dock koneksi kompak. Strip bisa di-scroll horizontal (tinggi tetap);
 * popover berada di luar strip supaya tidak terpotong overflow.
 * Murni presentasi: tidak ada fetch/polling.
 *
 * Props: connections · showType · onOpenManager · emptyLabel
 */
export default function ConnectionDock({
  connections = [],
  showType = false,
  onOpenManager,
  emptyLabel = "No active connections",
}) {
  const list = useMemo(
    () => (Array.isArray(connections) ? connections : []).map((c, i) => normalizeConnection(c, i)),
    [connections]
  );
  const [openId, setOpenId] = useState(null);
  const rootRef = useRef(null);

  const selected = list.find((c) => c.id === openId) || null;

  useEffect(() => {
    if (!selected) return undefined;

    function onPointerDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpenId(null);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpenId(null);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [selected]);

  return (
    <div ref={rootRef} className="relative min-w-0 flex-1">
      <div
        className="flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        role="list"
        aria-label="Connections"
      >
        {list.length === 0 && (
          <span className="text-xs text-[color:var(--ck-muted)] truncate">{emptyLabel}</span>
        )}

        {list.map((c) => (
          <div role="listitem" key={c.id} className="shrink-0">
            <ConnectionBadge
              connection={c}
              showType={showType}
              active={openId === c.id}
              onClick={(conn) => setOpenId((cur) => (cur === conn.id ? null : conn.id))}
            />
          </div>
        ))}
      </div>

      {selected && (
        <ConnectionPopover
          connection={selected}
          onClose={() => setOpenId(null)}
          onOpenManager={() => {
            setOpenId(null);
            (onOpenManager || defaultOpenManager)();
          }}
        />
      )}
    </div>
  );
}
