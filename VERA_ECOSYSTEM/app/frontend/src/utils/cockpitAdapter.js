/**
 * utils/cockpitAdapter.js — adapter MURNI antara state AIRA yang sudah ada
 * dan kontrak data Workspace Cockpit (W3) / Greeting Resolver (W4).
 *
 * Tanpa React, tanpa fetch, tanpa timer: bisa diuji dengan `node --test`.
 * Cockpit sendiri tidak tahu apa-apa soal runtime; semua pemetaan ada di sini.
 *
 *   /api/connections        -> connectionsFromApi()          -> Connection[] (W3)
 *   useChatRuntime()        -> runtimeFromChatRuntime()      -> {streaming, thinking}
 *   connections + liveTools -> activityFromRuntime()         -> "idle" | "network_work" (W4)
 *   /api/settings           -> settingsSnapshotFromApi()     -> snapshot untuk W4
 *   whitelist               -> getWorkspaceTools()           -> Tool[] (W3)
 */

import {
  CONNECTION_STATUS,
  connectionsFromApi as contractConnectionsFromApi,
  isConnected,
  normalizeStatus,
  normalizeTool,
} from "../components/cockpit/cockpitContracts.js";
import { ACTIVITY_STATE } from "./greetingContext.js";

export const CONNECTIONS_CHANGED_EVENT = "aira:connections-changed";
export const NAVIGATE_EVENT = "aira:navigate";

export const GREETING_SETTING_KEYS = Object.freeze([
  "display_name",
  "nickname",
  "assistant_name",
  "timezone",
  "language",
  "theme",
  "greeting_style",
]);

// Kategori tool yang dianggap "pekerjaan jaringan" (lihat AKANE_TOOL_CATEGORY).
export const NETWORK_TOOL_CATEGORIES = Object.freeze(["network", "mikrotik", "snmp"]);

// ============================================================ CONNECTIONS

/** Menerima array mentah ATAU objek { connections: [...] } dari /api/connections. */
export function connectionsFromApi(apiConnections) {
  const list = Array.isArray(apiConnections)
    ? apiConnections
    : Array.isArray(apiConnections && apiConnections.connections)
    ? apiConnections.connections
    : [];

  return contractConnectionsFromApi(list);
}

/** Jumlah koneksi yang benar-benar aktif (connected/busy) - bukan yang error/putus. */
export function countActiveConnections(connections) {
  return (Array.isArray(connections) ? connections : []).filter((c) => isConnected(c && c.status)).length;
}

// ============================================================ RUNTIME

/** ctx: { loading, streaming } dari useChatRuntime(). thinking = loading && !streaming. */
export function runtimeFromChatRuntime(ctx) {
  const source = ctx && typeof ctx === "object" ? ctx : {};
  const streaming = Boolean(source.streaming);

  return { streaming, thinking: Boolean(source.loading) && !streaming };
}

/**
 * Activity untuk Greeting Resolver (W4): "network_work" kalau ada koneksi busy
 * atau tool jaringan yang SEDANG berjalan (liveTools[].success === null),
 * selain itu "idle".
 */
export function activityFromRuntime({ connections = [], liveTools = [] } = {}) {
  const hasBusyConnection = (Array.isArray(connections) ? connections : []).some(
    (c) => normalizeStatus(c && c.status) === CONNECTION_STATUS.BUSY
  );

  const hasRunningNetworkTool = (Array.isArray(liveTools) ? liveTools : []).some(
    (t) =>
      Boolean(t) &&
      t.success === null &&
      NETWORK_TOOL_CATEGORIES.includes(String(t.category || "").toLowerCase())
  );

  return hasBusyConnection || hasRunningNetworkTool ? ACTIVITY_STATE.NETWORK_WORK : ACTIVITY_STATE.IDLE;
}

// ============================================================ SETTINGS

/** Ambil hanya key yang dipakai layer greeting; nilai non-string dibuang. */
export function settingsSnapshotFromApi(raw) {
  const source =
    raw && typeof raw === "object"
      ? raw.settings && typeof raw.settings === "object"
        ? raw.settings
        : raw
      : {};

  const snapshot = {};

  for (const key of GREETING_SETTING_KEYS) {
    if (typeof source[key] === "string") snapshot[key] = source[key];
  }

  return Object.freeze(snapshot);
}

// ============================================================ TOOL DOCK

// Whitelist awal (bukan seluruh Tool Registry). Menambah tool = tambah id di
// sini + satu entri katalog. `enabled` = punya aksi UI saat diklik.
const WORKSPACE_TOOL_WHITELIST = Object.freeze(["ssh", "files", "history", "vision"]);

const TOOL_CATALOG = Object.freeze({
  ssh: { id: "ssh", label: "SSH", icon: "terminal", enabled: true },
  files: { id: "files", label: "Files", icon: "folder", enabled: true },
  history: { id: "history", label: "History", icon: "history", enabled: false },
  vision: { id: "vision", label: "Vision", icon: "eye", enabled: false },
});

const TOOL_NAV_TARGETS = Object.freeze({
  ssh: "akane",
  files: "workspace",
});

/** Selalu mengembalikan objek baru (aman dimutasi pemanggil). */
export function getWorkspaceTools() {
  return WORKSPACE_TOOL_WHITELIST.map((id) => normalizeTool({ ...TOOL_CATALOG[id] }));
}

/** id halaman tujuan untuk sebuah tool, atau null kalau tidak punya aksi. */
export function targetForTool(tool) {
  const id = typeof tool === "string" ? tool : tool && tool.id;
  const entry = TOOL_CATALOG[id];

  if (!entry || !entry.enabled) return null;

  return TOOL_NAV_TARGETS[id] || null;
}

export function navigateForTool(tool) {
  const target = targetForTool(tool);

  if (!target || typeof window === "undefined" || typeof window.dispatchEvent !== "function") return false;

  window.dispatchEvent(new CustomEvent(NAVIGATE_EVENT, { detail: target }));
  return true;
}

// ============================================================ EVENT

/** Beri tahu pendengar (useCockpitData) bahwa daftar koneksi berubah. */
export function notifyConnectionsChanged() {
  if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") return false;

  window.dispatchEvent(new CustomEvent(CONNECTIONS_CHANGED_EVENT));
  return true;
}