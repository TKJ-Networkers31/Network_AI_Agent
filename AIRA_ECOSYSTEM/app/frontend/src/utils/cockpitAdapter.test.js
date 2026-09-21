import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  CONNECTIONS_CHANGED_EVENT,
  GREETING_SETTING_KEYS,
  activityFromRuntime,
  connectionsFromApi,
  countActiveConnections,
  getWorkspaceTools,
  navigateForTool,
  notifyConnectionsChanged,
  runtimeFromChatRuntime,
  settingsSnapshotFromApi,
  targetForTool,
} from "./cockpitAdapter.js";
import { normalizeConnection } from "../components/cockpit/cockpitContracts.js";
import { resolveGreetingModel } from "./greetingResolver.js";

const SRC = new URL("../", import.meta.url);
const stripComments = (code) => code.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const source = (relative) => stripComments(readFileSync(new URL(relative, SRC), "utf8"));

const API_LIST = [
  { session_id: "a1", device_name: "R1", host: "192.168.1.1", port: 22, username: "admin", status: "connected", idle_seconds: 3 },
  { session_id: "a2", device_name: "R2", host: "192.168.1.2", port: 22, username: "admin", status: "busy" },
  { session_id: "a3", device_name: "R3", host: "192.168.1.3", port: 22, username: "admin", status: "error" },
];

// ---------------------------------------------------------------- connections

test("connectionsFromApi: array mentah -> bentuk Connection W3", () => {
  const [r1] = connectionsFromApi(API_LIST);

  assert.deepEqual(Object.keys(r1).sort(), ["id", "label", "metadata", "status", "type"]);
  assert.equal(r1.id, "a1");
  assert.equal(r1.label, "R1");
  assert.equal(r1.type, "ssh");
  assert.equal(r1.metadata.host, "192.168.1.1");
});

test("connectionsFromApi: menerima pembungkus { connections: [...] }", () => {
  assert.equal(connectionsFromApi({ connections: API_LIST }).length, 3);
});

test("connectionsFromApi: input rusak -> []", () => {
  for (const bad of [null, undefined, "x", 5, {}, { connections: "x" }]) {
    assert.deepEqual(connectionsFromApi(bad), [], String(bad));
  }
});

test("status API dipetakan ke status W3 (error -> failed)", () => {
  assert.deepEqual(connectionsFromApi(API_LIST).map((c) => c.status), ["connected", "busy", "failed"]);
});

test("countActiveConnections: hanya connected & busy", () => {
  assert.equal(countActiveConnections(connectionsFromApi(API_LIST)), 2);
  assert.equal(countActiveConnections([]), 0);
  assert.equal(countActiveConnections(null), 0);
});

// -------------------------------------------------------------------- runtime

test("runtimeFromChatRuntime: thinking = loading && !streaming", () => {
  assert.deepEqual(runtimeFromChatRuntime({ loading: false, streaming: false }), { streaming: false, thinking: false });
  assert.deepEqual(runtimeFromChatRuntime({ loading: true, streaming: false }), { streaming: false, thinking: true });
  assert.deepEqual(runtimeFromChatRuntime({ loading: true, streaming: true }), { streaming: true, thinking: false });
});

test("runtimeFromChatRuntime: input rusak -> semua false", () => {
  for (const bad of [null, undefined, "x", {}]) {
    assert.deepEqual(runtimeFromChatRuntime(bad), { streaming: false, thinking: false });
  }
});

// ------------------------------------------------------------------- activity

test("activityFromRuntime: koneksi busy -> network_work", () => {
  assert.equal(activityFromRuntime({ connections: connectionsFromApi(API_LIST) }), "network_work");
});

test("activityFromRuntime: tool jaringan yang SEDANG berjalan -> network_work", () => {
  for (const category of ["network", "mikrotik", "snmp"]) {
    assert.equal(
      activityFromRuntime({ liveTools: [{ name: "x", category, success: null }] }),
      "network_work",
      category
    );
  }
});

test("activityFromRuntime: tool selesai / bukan jaringan / tanpa data -> idle", () => {
  assert.equal(activityFromRuntime({ liveTools: [{ category: "mikrotik", success: true }] }), "idle");
  assert.equal(activityFromRuntime({ liveTools: [{ category: "mikrotik", success: false }] }), "idle");
  assert.equal(activityFromRuntime({ liveTools: [{ category: "web", success: null }] }), "idle");
  assert.equal(activityFromRuntime({ connections: [{ id: "a", label: "A", status: "connected" }] }), "idle");
  assert.equal(activityFromRuntime({}), "idle");
  assert.equal(activityFromRuntime(), "idle");
});

test("activityFromRuntime: input rusak tidak raise", () => {
  assert.equal(activityFromRuntime({ connections: null, liveTools: null }), "idle");
  assert.equal(activityFromRuntime({ connections: [null], liveTools: [null, undefined] }), "idle");
});

// ------------------------------------------------------------------ tool dock

test("getWorkspaceTools: whitelist berurutan, bentuk Tool W3", () => {
  const tools = getWorkspaceTools();

  assert.deepEqual(tools.map((t) => t.id), ["ssh", "files", "history", "vision"]);
  assert.deepEqual(tools.map((t) => t.enabled), [true, true, false, false]);

  for (const tool of tools) {
    assert.equal(typeof tool.label, "string");
    assert.equal(typeof tool.icon, "string");
  }
});

test("getWorkspaceTools: selalu objek baru (mutasi pemanggil tidak bocor)", () => {
  const first = getWorkspaceTools();
  first[0].label = "DIUBAH";
  first.pop();

  const second = getWorkspaceTools();

  assert.equal(second.length, 4);
  assert.equal(second[0].label, "SSH");
});

test("targetForTool / navigateForTool: hanya tool ber-aksi; aman tanpa window", () => {
  assert.equal(targetForTool("ssh"), "akane");
  assert.equal(targetForTool({ id: "files" }), "workspace");

  for (const none of ["history", "vision", "tidak-ada", null, undefined, {}]) {
    assert.equal(targetForTool(none), null, String(none));
  }

  assert.equal(navigateForTool("ssh"), false); // node: tidak ada window
});

// ------------------------------------------------------------------- settings

test("settingsSnapshotFromApi: hanya key greeting yang berstring, beku", () => {
  const snapshot = settingsSnapshotFromApi({
    settings: {
      display_name: "Lingga", nickname: "Ling", assistant_name: "AIRA", timezone: "Asia/Jakarta",
      language: "id", theme: "arctic-blue", greeting_style: "default",
      voice_enabled: true, kunci_asing: "x",
    },
    updated_at: {},
  });

  assert.deepEqual(Object.keys(snapshot).sort(), [...GREETING_SETTING_KEYS].sort());
  assert.equal(Object.isFrozen(snapshot), true);
  assert.deepEqual(settingsSnapshotFromApi(null), {});
  assert.deepEqual(settingsSnapshotFromApi({ display_name: 5, timezone: "Asia/Tokyo" }), { timezone: "Asia/Tokyo" });
});

// ---------------------------------------------------------------------- event

test("notifyConnectionsChanged: nama event tetap; aman tanpa window", () => {
  assert.equal(CONNECTIONS_CHANGED_EVENT, "aira:connections-changed");
  assert.equal(notifyConnectionsChanged(), false);
});

// -------------------------------------------------------------- guard sumber

test("adapter & hook: tanpa polling/WebSocket/mock; tanpa fetch mentah", () => {
  for (const file of ["utils/cockpitAdapter.js", "hooks/useCockpitData.js", "hooks/useGlobalSettings.js"]) {
    const code = source(file);

    assert.doesNotMatch(code, /setInterval\s*\(/, `${file} memakai setInterval`);
    assert.doesNotMatch(code, /new WebSocket/, `${file} membuka WebSocket`);
    assert.doesNotMatch(code, /\bfetch\s*\(/, `${file} memakai fetch mentah`);
    assert.doesNotMatch(code, /MOCK_|mockData/, `${file} memakai mock`);
  }
});

test("ChatPage: tanpa mock, memakai heroModel W4 + cockpit, greeting lama tidak dipakai", () => {
  const code = source("pages/ChatPage.jsx");

  assert.doesNotMatch(code, /MOCK_|mockData/);
  assert.doesNotMatch(code, /cockpit\/index\.js/);
  assert.match(code, /resolveGreetingModel/);
  assert.match(code, /<WorkspaceCockpit/);
  assert.match(code, /heroModel=\{heroModel\}/);
  assert.match(code, /hideConnectionIndicator/);
  assert.doesNotMatch(code, /buildGreeting\s*\(/);
});

test("TopBar: periode dari util W4 (timezone Settings), indikator koneksi bisa disembunyikan", () => {
  const code = source("components/TopBar.jsx");

  assert.match(code, /buildGreetingContext/);
  assert.match(code, /hideConnectionIndicator/);
  assert.doesNotMatch(code, /function greeting\(hour\)/);
});

test("DynamicHero: heroModel additive, jalur heroContext lama masih ada", () => {
  const code = source("components/cockpit/DynamicHero.jsx");

  assert.match(code, /heroModel/);
  assert.match(code, /heroTitle/);
  assert.match(code, /heroSubtitle/);
});

// ----------------------------------------------------- integrasi W3-adapter-W4

const SETTINGS = { display_name: "Lingga", timezone: "Asia/Jakarta", language: "id" };
const NOW = new Date("2026-09-21T01:00:00Z"); // 08:00 WIB

test("adapter -> W4: koneksi busy + 2 aktif -> hero model network_work", () => {
  const connections = connectionsFromApi(API_LIST);

  const hero = resolveGreetingModel({
    settings: SETTINGS,
    workspace: null,
    connections: countActiveConnections(connections),
    activity: activityFromRuntime({ connections }),
    now: NOW,
  });

  assert.equal(hero.greeting, "Selamat pagi, Lingga");
  assert.equal(hero.status, "network_work");
  assert.equal(hero.fallback, false);
  assert.equal(typeof hero.subtitle, "string");
});

test("adapter -> W4: tanpa koneksi & tanpa workspace -> idle; output adapter valid untuk W3", () => {
  const connections = connectionsFromApi([]);

  const hero = resolveGreetingModel({
    settings: SETTINGS,
    workspace: null,
    connections: countActiveConnections(connections),
    activity: activityFromRuntime({ connections }),
    now: NOW,
  });

  assert.equal(hero.status, "idle");

  for (const c of connectionsFromApi(API_LIST)) {
    assert.deepEqual(normalizeConnection(c), c); // idempoten terhadap normalisasi W3
  }
});