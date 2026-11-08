/**
 * cockpit/cockpitContracts.js — kontrak data cockpit + adapter MURNI.
 *
 * Tanpa React, tanpa ikon, tanpa fetch, tanpa timer: bisa diuji dengan
 * `node --test`. Cockpit TIDAK punya polling; data datang dari luar lewat
 * props (alur: ConnectionManager -> Event Bus -> WebSocket runtime ->
 * adapter milik W5 -> WorkspaceCockpit).
 *
 * Skema:
 *
 *   Connection   { id, label, type, status, metadata? }
 *                type: string bebas ("ssh" | "docker" | "api" | "winbox" | "serial" | ...)
 *                metadata: objek datar (host, port, username, idleSeconds, protocol, ...)
 *   Activity     { targetId, label, type, status }
 *   Tool         { id, label, icon, enabled, badge? }
 *   RuntimeState { streaming: boolean, thinking: boolean }      (placeholder, belum dipakai)
 *   HeroContext  { displayName, timePeriod, workspaceLabel, connectionCount, activityState }
 *
 *   status:        "connecting" | "connected" | "busy" | "failed" | "disconnected"
 *   timePeriod:    "morning" | "afternoon" | "evening" | "night"
 *   activityState: "idle" | "working" | "disconnected" | "maintenance"
 */

// ============================================================ STATUS

export const CONNECTION_STATUS = Object.freeze({
  CONNECTING: "connecting",
  CONNECTED: "connected",
  BUSY: "busy",
  FAILED: "failed",
  DISCONNECTED: "disconnected",
});

// shape: bentuk penanda di StatusDot (dibedakan bentuk, bukan hanya warna).
export const STATUS_META = Object.freeze({
  connecting: { label: "Connecting", tone: "accent", shape: "hollow", pulse: true },
  connected: { label: "Connected", tone: "ok", shape: "solid", pulse: false },
  busy: { label: "Running command", tone: "accent", shape: "ping", pulse: false },
  failed: { label: "Failed", tone: "err", shape: "diamond", pulse: false },
  disconnected: { label: "Disconnected", tone: "muted", shape: "hollow", pulse: false },
});

const VALID_STATUS = new Set(Object.values(CONNECTION_STATUS));

export function normalizeStatus(value) {
  const v = String(value || "").trim().toLowerCase();
  if (v === "closed") return CONNECTION_STATUS.DISCONNECTED;
  if (v === "error") return CONNECTION_STATUS.FAILED;
  return VALID_STATUS.has(v) ? v : CONNECTION_STATUS.DISCONNECTED;
}

/** Terhubung dan siap dipakai (dihitung sebagai "active connection"). */
export function isConnected(status) {
  const s = normalizeStatus(status);
  return s === CONNECTION_STATUS.CONNECTED || s === CONNECTION_STATUS.BUSY;
}

// ============================================================ CONNECTION

export const KNOWN_CONNECTION_TYPES = Object.freeze(["ssh", "docker", "api", "winbox", "serial"]);

function plainMetadata(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out = {};
  for (const [key, value] of Object.entries(raw)) {
    if (value !== null && value !== undefined) out[key] = value;
  }
  return out;
}

export function normalizeConnection(raw, index = 0) {
  const r = raw && typeof raw === "object" ? raw : {};
  const label = r.label ?? r.name ?? r.id ?? `Link ${index + 1}`;

  return {
    id: String(r.id ?? label),
    label: String(label),
    type: String(r.type || "generic").toLowerCase(),
    status: normalizeStatus(r.status),
    metadata: plainMetadata(r.metadata),
  };
}

/**
 * Adapter untuk bentuk /api/connections yang SUDAH ADA (session_state.py::to_dict).
 * Hanya pemetaan bentuk - tidak melakukan fetch. Dipakai adapter W5 untuk
 * snapshot awal maupun update dari event WebSocket.
 */
export function connectionsFromApi(list) {
  return (Array.isArray(list) ? list : []).map((item, i) => {
    const r = item && typeof item === "object" ? item : {};

    return normalizeConnection(
      {
        id: r.session_id ?? r.id,
        label: r.device_name ?? r.host,
        type: "ssh", // AKANE saat ini hanya SSH; protokol lain menyusul lewat `type`
        status: r.status,
        metadata: {
          protocol: "ssh",
          host: r.host,
          port: r.port,
          username: r.username,
          idleSeconds: r.idle_seconds,
        },
      },
      i
    );
  });
}

// ============================================================ ACTIVITY

export function normalizeActivity(raw, index = 0) {
  const r = raw && typeof raw === "object" ? raw : {};
  const label = r.label ?? r.targetId ?? `Target ${index + 1}`;

  return {
    targetId: String(r.targetId ?? label),
    label: String(label),
    type: r.type ? String(r.type).toLowerCase() : null,
    status: normalizeStatus(r.status),
  };
}

/** Connection[] -> Activity[] (semua kecuali yang sudah terputus; failed tetap tampil). */
export function activityFromConnections(connections) {
  return (Array.isArray(connections) ? connections : [])
    .map((c, i) => normalizeConnection(c, i))
    .filter((c) => c.status !== CONNECTION_STATUS.DISCONNECTED)
    .map((c) => ({ targetId: c.id, label: c.label, type: c.type, status: c.status }));
}

export function isWorking(activity) {
  return (Array.isArray(activity) ? activity : []).some(
    (a) => normalizeStatus(a && a.status) === CONNECTION_STATUS.BUSY
  );
}

// ============================================================ TOOL

export function normalizeTool(raw, index = 0) {
  const r = raw && typeof raw === "object" ? raw : {};
  const id = String(r.id ?? `tool-${index}`);

  return {
    id,
    label: String(r.label ?? id),
    icon: r.icon ? String(r.icon) : "wrench",
    enabled: r.enabled !== false,
    badge: r.badge ?? null,
  };
}

// ============================================================ RUNTIME (placeholder)

/** Placeholder untuk W5. Belum dibaca komponen mana pun. */
export function normalizeRuntimeState(raw) {
  const r = raw && typeof raw === "object" ? raw : {};
  return { streaming: Boolean(r.streaming), thinking: Boolean(r.thinking) };
}

// ============================================================ HERO

export const TIME_PERIOD = Object.freeze({
  MORNING: "morning",
  AFTERNOON: "afternoon",
  EVENING: "evening",
  NIGHT: "night",
});

export const ACTIVITY_STATE = Object.freeze({
  IDLE: "idle",
  WORKING: "working",
  DISCONNECTED: "disconnected",
  MAINTENANCE: "maintenance",
});

const VALID_PERIOD = new Set(Object.values(TIME_PERIOD));
const VALID_ACTIVITY_STATE = new Set(Object.values(ACTIVITY_STATE));

const GREETING = Object.freeze({
  morning: "Good morning",
  afternoon: "Good afternoon",
  evening: "Good evening",
  night: "Good night",
});

export const DEFAULT_WORKSPACE_LABEL = "Network Engineering";

export function timePeriodForHour(hour) {
  if (hour < 5) return TIME_PERIOD.NIGHT;
  if (hour < 11) return TIME_PERIOD.MORNING;
  if (hour < 15) return TIME_PERIOD.AFTERNOON;
  if (hour < 22) return TIME_PERIOD.EVENING;
  return TIME_PERIOD.NIGHT;
}

/**
 * Turunkan activityState dari data koneksi. Hanya helper default:
 * pemilik `heroContext` sebenarnya (W4) boleh mengirim nilainya sendiri.
 */
export function deriveActivityState({ connections = [], activity, maintenance = false } = {}) {
  if (maintenance) return ACTIVITY_STATE.MAINTENANCE;

  const normalized = (Array.isArray(connections) ? connections : []).map((c, i) => normalizeConnection(c, i));
  const act = Array.isArray(activity) ? activity : activityFromConnections(normalized);

  if (isWorking(act)) return ACTIVITY_STATE.WORKING;
  if (!normalized.some((c) => isConnected(c.status))) return ACTIVITY_STATE.DISCONNECTED;
  return ACTIVITY_STATE.IDLE;
}

/** Bangun HeroContext default dari data yang ada (dipakai bila pemanggil tidak memberi heroContext). */
export function buildHeroContext({
  displayName = "",
  workspaceLabel = DEFAULT_WORKSPACE_LABEL,
  connections = [],
  activity,
  maintenance = false,
  hour,
} = {}) {
  const normalized = (Array.isArray(connections) ? connections : []).map((c, i) => normalizeConnection(c, i));

  return {
    displayName,
    timePeriod: timePeriodForHour(hour ?? new Date().getHours()),
    workspaceLabel,
    connectionCount: normalized.filter((c) => isConnected(c.status)).length,
    activityState: deriveActivityState({ connections: normalized, activity, maintenance }),
  };
}

/** Lengkapi/validasi HeroContext dari luar; nilai rusak jatuh ke default aman. */
export function normalizeHeroContext(raw) {
  const r = raw && typeof raw === "object" ? raw : {};
  const count = Number(r.connectionCount);

  return {
    displayName: r.displayName ? String(r.displayName).trim() : "",
    timePeriod: VALID_PERIOD.has(r.timePeriod) ? r.timePeriod : timePeriodForHour(new Date().getHours()),
    workspaceLabel: r.workspaceLabel ? String(r.workspaceLabel) : DEFAULT_WORKSPACE_LABEL,
    connectionCount: Number.isFinite(count) && count > 0 ? Math.floor(count) : 0,
    activityState: VALID_ACTIVITY_STATE.has(r.activityState) ? r.activityState : ACTIVITY_STATE.IDLE,
  };
}

export function heroTitle(ctx) {
  const c = normalizeHeroContext(ctx);
  return c.displayName ? `${GREETING[c.timePeriod]}, ${c.displayName}` : GREETING[c.timePeriod];
}

export function heroSubtitle(ctx) {
  const c = normalizeHeroContext(ctx);
  const count = c.connectionCount;

  switch (c.activityState) {
    case ACTIVITY_STATE.MAINTENANCE:
      return "Workspace unavailable";
    case ACTIVITY_STATE.DISCONNECTED:
      return "No active connections";
    case ACTIVITY_STATE.WORKING:
      return count > 0 ? `Working with connected devices · ${count} active` : "Working with connected devices";
    default:
      return count > 0 ? `Ready for ${c.workspaceLabel} · ${count} active` : `Ready for ${c.workspaceLabel}`;
  }
}
