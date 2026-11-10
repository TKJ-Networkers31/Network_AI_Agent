/**
 * VERA Device Status Core Taxonomy
 * Pure JavaScript module for operational status normalization and styling.
 * Node.js test-runner compatible (no JSX).
 */

export const DEVICE_STATUSES = {
  ONLINE: "online",
  OFFLINE: "offline",
  WARNING: "warning",
  UNKNOWN: "unknown",
  PENDING: "pending",
  UNMANAGED: "unmanaged",
};

/**
 * Normalizes any status input (e.g. "up", "UP", "active", "online", "down", "error")
 * to one of the 6 canonical statuses.
 */
export function normalizeDeviceStatus(rawStatus) {
  if (!rawStatus) return DEVICE_STATUSES.UNKNOWN;
  const s = String(rawStatus).toLowerCase().trim();

  if (s === "up" || s === "online" || s === "active" || s === "reachable" || s === "ready") {
    return DEVICE_STATUSES.ONLINE;
  }
  if (s === "down" || s === "offline" || s === "failed" || s === "error" || s === "unreachable") {
    return DEVICE_STATUSES.OFFLINE;
  }
  if (s === "degraded" || s === "warning" || s === "flapping" || s === "alert" || s === "unstable") {
    return DEVICE_STATUSES.WARNING;
  }
  if (s === "pending" || s === "provisioning" || s === "discovering" || s === "syncing") {
    return DEVICE_STATUSES.PENDING;
  }
  if (s === "unmanaged" || s === "passive" || s === "bypass") {
    return DEVICE_STATUSES.UNMANAGED;
  }
  return DEVICE_STATUSES.UNKNOWN;
}

/**
 * Returns complete visual styling parameters for a given status.
 * Used by node containers for halos, borders, glows, and pill indicators.
 */
export function getDeviceStatusStyle(rawStatus) {
  const status = normalizeDeviceStatus(rawStatus);

  switch (status) {
    case DEVICE_STATUSES.ONLINE:
      return {
        status,
        label: "ONLINE",
        badgeBg: "bg-emerald-500/10",
        badgeText: "text-emerald-400",
        badgeBorder: "border-emerald-500/30",
        dotBg: "bg-emerald-400",
        dotPing: "motion-safe:animate-ping",
        pulseGlow: "motion-safe:animate-pulse",
        containerRing: "ring-emerald-500/30",
        containerBorder: "border-emerald-500/40",
        haloShadow: "shadow-[0_0_20px_rgba(16,185,129,0.25)]",
        svgGlowColor: "#10b981",
        hexColor: "#10b981",
        iconName: "CheckCircle2",
      };

    case DEVICE_STATUSES.OFFLINE:
      return {
        status,
        label: "OFFLINE",
        badgeBg: "bg-rose-500/10",
        badgeText: "text-rose-400",
        badgeBorder: "border-rose-500/30",
        dotBg: "bg-rose-400",
        dotPing: "",
        pulseGlow: "",
        containerRing: "ring-rose-500/30",
        containerBorder: "border-rose-500/40",
        haloShadow: "shadow-[0_0_20px_rgba(244,63,94,0.25)]",
        svgGlowColor: "#f43f5e",
        hexColor: "#f43f5e",
        iconName: "XCircle",
      };

    case DEVICE_STATUSES.WARNING:
      return {
        status,
        label: "WARNING",
        badgeBg: "bg-amber-500/10",
        badgeText: "text-amber-400",
        badgeBorder: "border-amber-500/30",
        dotBg: "bg-amber-400",
        dotPing: "motion-safe:animate-ping",
        pulseGlow: "motion-safe:animate-pulse",
        containerRing: "ring-amber-500/30",
        containerBorder: "border-amber-500/40",
        haloShadow: "shadow-[0_0_20px_rgba(245,158,11,0.25)]",
        svgGlowColor: "#f59e0b",
        hexColor: "#f59e0b",
        iconName: "AlertTriangle",
      };

    case DEVICE_STATUSES.PENDING:
      return {
        status,
        label: "PENDING",
        badgeBg: "bg-sky-500/10",
        badgeText: "text-sky-400",
        badgeBorder: "border-sky-500/30",
        dotBg: "bg-sky-400",
        dotPing: "motion-safe:animate-ping",
        pulseGlow: "motion-safe:animate-spin",
        containerRing: "ring-sky-500/30",
        containerBorder: "border-sky-500/40",
        haloShadow: "shadow-[0_0_20px_rgba(56,189,248,0.25)]",
        svgGlowColor: "#38bdf8",
        hexColor: "#38bdf8",
        iconName: "Clock",
      };

    case DEVICE_STATUSES.UNMANAGED:
      return {
        status,
        label: "UNMANAGED",
        badgeBg: "bg-zinc-800/60",
        badgeText: "text-zinc-400",
        badgeBorder: "border-zinc-700/40",
        dotBg: "bg-zinc-500",
        dotPing: "",
        pulseGlow: "",
        containerRing: "ring-zinc-700/20",
        containerBorder: "border-zinc-700/30",
        haloShadow: "shadow-none",
        svgGlowColor: "#64748b",
        hexColor: "#64748b",
        iconName: "Slash",
      };

    case DEVICE_STATUSES.UNKNOWN:
    default:
      return {
        status,
        label: "UNKNOWN",
        badgeBg: "bg-white/5",
        badgeText: "text-white/40",
        badgeBorder: "border-white/10",
        dotBg: "bg-white/40",
        dotPing: "",
        pulseGlow: "",
        containerRing: "ring-white/10",
        containerBorder: "border-white/10",
        haloShadow: "shadow-none",
        svgGlowColor: "#94a3b8",
        hexColor: "#94a3b8",
        iconName: "HelpCircle",
      };
  }
}
