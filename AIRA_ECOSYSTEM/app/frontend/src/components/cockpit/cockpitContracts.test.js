import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  ACTIVITY_STATE,
  CONNECTION_STATUS,
  STATUS_META,
  activityFromConnections,
  buildHeroContext,
  connectionsFromApi,
  deriveActivityState,
  heroSubtitle,
  heroTitle,
  isConnected,
  isWorking,
  normalizeConnection,
  normalizeHeroContext,
  normalizeRuntimeState,
  normalizeStatus,
  normalizeTool,
  timePeriodForHour,
} from "./cockpitContracts.js";
import { MOCK_CONNECTIONS, MOCK_ACTIVITY, MOCK_HERO_CONTEXT } from "./mockData.js";

// ---------------------------------------------------------------- status

test("normalizeStatus: closed -> disconnected, error -> failed, asing -> disconnected", () => {
  assert.equal(normalizeStatus("closed"), CONNECTION_STATUS.DISCONNECTED);
  assert.equal(normalizeStatus("error"), CONNECTION_STATUS.FAILED);
  assert.equal(normalizeStatus("BUSY"), CONNECTION_STATUS.BUSY);
  assert.equal(normalizeStatus("aneh"), CONNECTION_STATUS.DISCONNECTED);
  assert.equal(normalizeStatus(undefined), CONNECTION_STATUS.DISCONNECTED);
});

test("empat status wajib punya representasi visual berbeda", () => {
  const shapes = ["connecting", "connected", "busy", "failed"].map((s) => STATUS_META[s].shape);
  assert.equal(new Set(shapes).size, 4);
});

test("isConnected: hanya connected & busy", () => {
  assert.deepEqual(
    ["connected", "busy", "connecting", "failed", "closed"].map(isConnected),
    [true, true, false, false, false]
  );
});

// ------------------------------------------------------------ connection

test("skema Connection generik: type bebas, protocol hanya metadata", () => {
  for (const type of ["ssh", "docker", "api", "winbox", "serial", "sesuatu-baru"]) {
    const c = normalizeConnection({ id: "x", label: "X", type, status: "connected" });
    assert.equal(c.type, type);
  }

  const c = normalizeConnection({ id: "d", label: "Docker", type: "docker", metadata: { host: "h", kosong: null } });
  assert.deepEqual(c.metadata, { host: "h" });
});

test("normalizeConnection: tanpa type -> generic, id stabil dari label", () => {
  const c = normalizeConnection({ label: "R9" });
  assert.equal(c.type, "generic");
  assert.equal(c.id, "R9");
  assert.deepEqual(c.metadata, {});
});

test("connectionsFromApi memetakan /api/connections lama ke skema generik", () => {
  const [c] = connectionsFromApi([
    { session_id: "abc", device_name: "R1", host: "192.168.1.1", port: 22, username: "admin", status: "busy", idle_seconds: 12 },
  ]);

  assert.equal(c.id, "abc");
  assert.equal(c.label, "R1");
  assert.equal(c.type, "ssh");
  assert.equal(c.status, "busy");
  assert.equal(c.metadata.host, "192.168.1.1");
  assert.equal(c.metadata.idleSeconds, 12);
});

test("connectionsFromApi toleran terhadap input rusak", () => {
  assert.deepEqual(connectionsFromApi(null), []);
  assert.equal(connectionsFromApi([null])[0].status, "disconnected");
});

// -------------------------------------------------------------- activity

test("activityFromConnections membuang yang terputus, mempertahankan failed", () => {
  const act = activityFromConnections([
    { id: "r1", label: "R1", status: "connected" },
    { id: "r2", label: "R2", status: "closed" },
    { id: "olt", label: "OLT", status: "connecting" },
    { id: "nb", label: "NB", status: "error" },
  ]);
  assert.deepEqual(act.map((a) => a.targetId), ["r1", "olt", "nb"]);
  assert.equal(act[2].status, "failed");
});

test("isWorking", () => {
  assert.equal(isWorking([{ status: "busy" }]), true);
  assert.equal(isWorking([{ status: "connected" }]), false);
  assert.equal(isWorking(undefined), false);
});

// ------------------------------------------------------------------ hero

test("HeroContext: keempat activityState menghasilkan subtitle sesuai tabel", () => {
  const base = { displayName: "Lingga", timePeriod: "evening", workspaceLabel: "Network Engineering" };

  assert.equal(heroSubtitle({ ...base, activityState: "idle" }), "Ready for Network Engineering");
  assert.equal(heroSubtitle({ ...base, activityState: "working" }), "Working with connected devices");
  assert.equal(heroSubtitle({ ...base, activityState: "disconnected" }), "No active connections");
  assert.equal(heroSubtitle({ ...base, activityState: "maintenance" }), "Workspace unavailable");
});

test("heroSubtitle menambahkan jumlah koneksi hanya untuk idle/working", () => {
  assert.equal(
    heroSubtitle({ activityState: "idle", connectionCount: 2 }),
    "Ready for Network Engineering · 2 active"
  );
  assert.equal(heroSubtitle({ activityState: "maintenance", connectionCount: 2 }), "Workspace unavailable");
  assert.equal(heroSubtitle({ activityState: "disconnected", connectionCount: 2 }), "No active connections");
});

test("heroTitle dari timePeriod + displayName (bukan string greeting jadi)", () => {
  assert.equal(heroTitle(MOCK_HERO_CONTEXT), "Good evening, Lingga");
  assert.equal(heroTitle({ timePeriod: "morning" }), "Good morning");
  assert.equal(heroTitle({ timePeriod: "night", displayName: "  " }), "Good night");
});

test("normalizeHeroContext: nilai rusak jatuh ke default aman", () => {
  const c = normalizeHeroContext({ timePeriod: "senja", activityState: "??", connectionCount: -3, displayName: null });
  assert.equal(c.activityState, ACTIVITY_STATE.IDLE);
  assert.equal(c.connectionCount, 0);
  assert.equal(c.displayName, "");
  assert.equal(c.workspaceLabel, "Network Engineering");
  assert.ok(["morning", "afternoon", "evening", "night"].includes(c.timePeriod));
  assert.deepEqual(Object.keys(normalizeHeroContext(null)).sort(), [
    "activityState", "connectionCount", "displayName", "timePeriod", "workspaceLabel",
  ]);
});

test("timePeriodForHour", () => {
  assert.deepEqual([3, 8, 13, 20, 23].map(timePeriodForHour), ["night", "morning", "afternoon", "evening", "night"]);
});

test("deriveActivityState / buildHeroContext dari data koneksi", () => {
  assert.equal(deriveActivityState({ connections: [] }), "disconnected");
  assert.equal(deriveActivityState({ connections: [{ id: "a", status: "connected" }] }), "idle");
  assert.equal(deriveActivityState({ connections: MOCK_CONNECTIONS }), "working");
  assert.equal(deriveActivityState({ connections: MOCK_CONNECTIONS, maintenance: true }), "maintenance");

  const ctx = buildHeroContext({ displayName: "Lingga", connections: MOCK_CONNECTIONS, hour: 20 });
  assert.equal(ctx.connectionCount, 2); // r1 connected + r2 busy
  assert.equal(ctx.timePeriod, "evening");
  assert.equal(ctx.activityState, "working");
});

// --------------------------------------------------- tool / runtime / mock

test("normalizeTool: default aman", () => {
  const t = normalizeTool({ id: "x", label: "X" });
  assert.equal(t.enabled, true);
  assert.equal(t.icon, "wrench");
  assert.equal(normalizeTool({ id: "y", enabled: false }).enabled, false);
});

test("runtimeState placeholder ternormalisasi, default false", () => {
  assert.deepEqual(normalizeRuntimeState(undefined), { streaming: false, thinking: false });
  assert.deepEqual(normalizeRuntimeState({ streaming: 1 }), { streaming: true, thinking: false });
});

test("mock data konsisten dengan kontrak (semua status terwakili)", () => {
  assert.deepEqual(
    new Set(MOCK_ACTIVITY.map((a) => a.status)),
    new Set(["connecting", "connected", "busy", "failed"])
  );
  assert.equal(MOCK_CONNECTIONS.length, MOCK_ACTIVITY.length);
});

// ------------------------------------------------ guard arsitektur (W3 Rev A)

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCES = readdirSync(HERE)
  .filter((f) => /\.(jsx?|mjs)$/.test(f) && !f.endsWith(".test.js"))
  .map((f) => [f, readFileSync(join(HERE, f), "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "")]);

test("cockpit tidak punya polling/fetch/WebSocket sendiri", () => {
  for (const [file, code] of SOURCES) {
    assert.doesNotMatch(code, /setInterval\s*\(/, `${file} memakai setInterval`);
    assert.doesNotMatch(code, /\bfetch\s*\(/, `${file} memakai fetch`);
    assert.doesNotMatch(code, /new WebSocket|api\.connections/, `${file} mengakses API/WS`);
  }
});

test("cockpit tidak mengimpor domain W2/W4/W5 (runtime/streaming/thinking)", () => {
  for (const [file, code] of SOURCES) {
    assert.doesNotMatch(code, /ChatRuntimeContext|runLifecycle|useAiraSocket/, `${file} mengimpor domain lain`);
  }
});

test("ToolDock/ToolButton memakai shared registry, bukan folder cockpit", () => {
  const tool = SOURCES.find(([f]) => f === "ToolButton.jsx")[1];
  assert.match(tool, /shared\/iconRegistry\.js/);
  assert.equal(SOURCES.some(([f]) => f === "iconRegistry.js"), false);
});
