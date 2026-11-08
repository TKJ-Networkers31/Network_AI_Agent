/**
 * cockpit/mockData.js — data contoh. Bentuknya SAMA dengan kontrak final
 * (lihat cockpitContracts.js). Abaikan/hapus setelah W5 menyambungkan data nyata.
 */

export const MOCK_CONNECTIONS = [
  { id: "r1", label: "R1", type: "ssh", status: "connected", metadata: { host: "192.168.1.1", port: 22, username: "admin" } },
  { id: "r2", label: "R2", type: "ssh", status: "busy", metadata: { host: "192.168.1.2", port: 22, idleSeconds: 4 } },
  { id: "olt", label: "OLT", type: "serial", status: "connecting", metadata: { device: "COM3", baud: 115200 } },
  { id: "netbox", label: "NetBox", type: "api", status: "failed", metadata: { host: "netbox.lan", note: "401 Unauthorized" } },
];

export const MOCK_TOOLS = [
  { id: "ssh", label: "SSH", icon: "terminal", enabled: true },
  { id: "web", label: "Web", icon: "globe", enabled: true },
  { id: "files", label: "Files", icon: "folder", enabled: true },
  { id: "conversation_history", label: "History", icon: "history", enabled: true },
  { id: "vision", label: "Vision", icon: "eye", enabled: false },
];

export const MOCK_ACTIVITY = [
  { targetId: "r1", label: "R1", type: "ssh", status: "connected" },
  { targetId: "r2", label: "R2", type: "ssh", status: "busy" },
  { targetId: "olt", label: "OLT", type: "serial", status: "connecting" },
  { targetId: "netbox", label: "NetBox", type: "api", status: "failed" },
];

export const MOCK_HERO_CONTEXT = {
  displayName: "Lingga",
  timePeriod: "evening",
  workspaceLabel: "Network Engineering",
  connectionCount: 2,
  activityState: "working",
};

export const MOCK_RUNTIME_STATE = { streaming: false, thinking: false };
