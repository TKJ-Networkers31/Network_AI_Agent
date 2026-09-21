import { resolveIcon } from "../../shared/iconRegistry.js";
import { normalizeTool } from "./cockpitContracts.js";

/** Satu tombol tool: ikon (dari shared registry) + label. Tool nonaktif tetap terlihat. */
export default function ToolButton({ tool, active = false, iconRegistry, onSelect }) {
  const t = normalizeTool(tool);
  const Icon = resolveIcon(t.icon, iconRegistry);

  return (
    <button
      type="button"
      onClick={() => t.enabled && onSelect?.(t)}
      aria-disabled={!t.enabled}
      aria-pressed={active}
      title={t.enabled ? t.label : `${t.label} (tidak tersedia)`}
      className={`shrink-0 inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border text-xs font-medium transition
        focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[color:var(--ck-accent)]
        ${!t.enabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}
        ${
          active
            ? "bg-[color:var(--ck-accent-soft)] border-[color:var(--ck-border-strong)] text-[color:var(--ck-accent)]"
            : "bg-transparent border-[color:var(--ck-border)] text-[color:var(--ck-muted)] hover:text-[color:var(--ck-text)] hover:border-[color:var(--ck-border-strong)]"
        }`}
    >
      <Icon size={14} strokeWidth={1.9} />
      <span>{t.label}</span>
      {t.badge != null && (
        <span className="ml-0.5 px-1 rounded bg-[color:var(--ck-accent-soft)] text-[color:var(--ck-accent)] text-[10px]">
          {t.badge}
        </span>
      )}
    </button>
  );
}
