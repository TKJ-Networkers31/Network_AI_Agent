// src/features/topology/assets/deviceAssetRegistry.test.js
// Unit Test Suite for VERA Device Asset Library & Deterministic Resolution

import test from "node:test";
import assert from "node:assert/strict";

import {
  DEVICE_ASSET_REGISTRY,
  resolveDeviceAssetKey,
  resolveDeviceAsset,
  getDeviceAsset,
  listDeviceAssets,
  listDeviceAssetsByCategory,
  normalizeDeviceIdentity,
} from "./deviceAssetRegistry.js";

import {
  DEVICE_STATUSES,
  normalizeDeviceStatus,
  getDeviceStatusStyle,
} from "./deviceStatusCore.js";

import { generateTopologySvg } from "./svgTopologyExporter.js";

// -----------------------------------------------------------------------------
// 1. Device Catalog Completeness & Schema Integrity
// -----------------------------------------------------------------------------

test("DEVICE_ASSET_REGISTRY contains all 27 specified device assets", () => {
  const assets = listDeviceAssets();
  assert.equal(assets.length, 27, "Must contain exactly 27 cataloged assets");

  const expectedKeys = [
    // Network Infrastructure (14)
    "router-generic",
    "mikrotik-router-generic",
    "mikrotik-hap-ac-lite",
    "mikrotik-rb951ui-2hnd",
    "switch-l2",
    "switch-l3",
    "firewall",
    "access-point",
    "access-point-outdoor",
    "wireless-bridge",
    "modem",
    "ont",
    "isp-gateway",
    "internet-cloud",
    // Compute Infrastructure (5)
    "server-rack",
    "server-tower",
    "server-virtualization",
    "nas-storage",
    "server-database",
    // End Devices (6)
    "workstation",
    "laptop",
    "smartphone",
    "printer",
    "cctv-camera",
    "iot-device",
    // Fallbacks (2)
    "unknown-device",
    "unmanaged-device",
  ];

  for (const key of expectedKeys) {
    const asset = DEVICE_ASSET_REGISTRY[key];
    assert.ok(asset, `Asset key '${key}' must exist in registry`);
    assert.equal(asset.key, key);
    assert.ok(asset.label, `Asset '${key}' must have a label`);
    assert.ok(asset.category, `Asset '${key}' must have a category`);
    assert.equal(typeof asset.component, "function", `Asset '${key}' must have a React component`);
    assert.equal(typeof asset.svgRaw, "string", `Asset '${key}' must have an svgRaw XML string`);
    assert.ok(Array.isArray(asset.tags), `Asset '${key}' must have tags array`);
    assert.equal(typeof asset.isManagedDefault, "boolean");
  }
});

test("listDeviceAssetsByCategory returns correct partitions", () => {
  const network = listDeviceAssetsByCategory("network");
  const compute = listDeviceAssetsByCategory("compute");
  const endpoint = listDeviceAssetsByCategory("endpoint");
  const fallback = listDeviceAssetsByCategory("fallback");

  assert.equal(network.length, 14, "Network category must contain 14 assets");
  assert.equal(compute.length, 5, "Compute category must contain 5 assets");
  assert.equal(endpoint.length, 6, "Endpoint category must contain 6 assets");
  assert.equal(fallback.length, 2, "Fallback category must contain 2 assets");
});

// -----------------------------------------------------------------------------
// 2. Deterministic Resolution Pipeline Tests
// -----------------------------------------------------------------------------

test("resolveDeviceAssetKey resolves MikroTik exact models", () => {
  // hAP ac lite variations
  assert.equal(
    resolveDeviceAssetKey({ vendor: "MikroTik", model: "hAP ac lite" }),
    "mikrotik-hap-ac-lite"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "RB952Ui-5ac2nD" }),
    "mikrotik-hap-ac-lite"
  );
  assert.equal(
    resolveDeviceAssetKey({ name: "Core-hAP-ac-lite-01" }),
    "mikrotik-hap-ac-lite"
  );

  // RB951Ui-2HnD variations
  assert.equal(
    resolveDeviceAssetKey({ vendor: "MikroTik", model: "RB951Ui-2HnD" }),
    "mikrotik-rb951ui-2hnd"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "RB951-2n" }),
    "mikrotik-rb951ui-2hnd"
  );

  // Generic MikroTik Router
  assert.equal(
    resolveDeviceAssetKey({ vendor: "MikroTik", device_type: "router" }),
    "mikrotik-router-generic"
  );
  assert.equal(
    resolveDeviceAssetKey({ vendor: "RouterBOARD", model: "CCR1036-8G-2S+" }),
    "mikrotik-router-generic"
  );
});

test("resolveDeviceAssetKey resolves Switches (L2 vs L3)", () => {
  assert.equal(
    resolveDeviceAssetKey({ device_type: "switch" }),
    "switch-l2"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "l2_switch" }),
    "switch-l2"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "switch_l3" }),
    "switch-l3"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "switch", model: "Core L3 Switch" }),
    "switch-l3"
  );
});

test("resolveDeviceAssetKey resolves Network Gateways, Firewalls & Fiber", () => {
  assert.equal(
    resolveDeviceAssetKey({ device_type: "firewall" }),
    "firewall"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "pfSense SG-3100" }),
    "firewall"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "ont" }),
    "ont"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "GPON Terminal" }),
    "ont"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "modem" }),
    "modem"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "wireless_bridge" }),
    "wireless-bridge"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "Ubiquiti AirMax Dish" }),
    "wireless-bridge"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "isp_gateway" }),
    "isp-gateway"
  );
  assert.equal(
    resolveDeviceAssetKey({ name: "BGP-Transit-Edge" }),
    "isp-gateway"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "internet" }),
    "internet-cloud"
  );
});

test("resolveDeviceAssetKey resolves Wireless APs (Indoor vs Outdoor)", () => {
  assert.equal(
    resolveDeviceAssetKey({ device_type: "access_point" }),
    "access-point"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "UniFi U6-Pro" }),
    "access-point"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "outdoor_ap" }),
    "access-point-outdoor"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "access_point", name: "Outdoor Pole AP" }),
    "access-point-outdoor"
  );
});

test("resolveDeviceAssetKey resolves Compute Infrastructure", () => {
  assert.equal(
    resolveDeviceAssetKey({ device_type: "server", model: "Dell PowerEdge R740" }),
    "server-rack"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "Tower Server Pro" }),
    "server-tower"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "Proxmox VE Cluster Node" }),
    "server-virtualization"
  );
  assert.equal(
    resolveDeviceAssetKey({ model: "Synology DiskStation DS920+" }),
    "nas-storage"
  );
  assert.equal(
    resolveDeviceAssetKey({ name: "PostgreSQL Production DB" }),
    "server-database"
  );
});

test("resolveDeviceAssetKey resolves End Devices", () => {
  assert.equal(
    resolveDeviceAssetKey({ device_type: "workstation" }),
    "workstation"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "laptop" }),
    "laptop"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "smartphone" }),
    "smartphone"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "printer" }),
    "printer"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "cctv" }),
    "cctv-camera"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "iot" }),
    "iot-device"
  );
});

test("resolveDeviceAssetKey handles Unmanaged and Unknown Fallbacks safely", () => {
  // Explicit unmanaged flags
  assert.equal(
    resolveDeviceAssetKey({ is_managed: false }),
    "unmanaged-device"
  );
  assert.equal(
    resolveDeviceAssetKey({ device_type: "unmanaged" }),
    "unmanaged-device"
  );

  // Unknown devices
  assert.equal(
    resolveDeviceAssetKey({ device_type: "custom_mysterious_gadget_xyz" }),
    "unknown-device"
  );

  // Degraded inputs: null, undefined, empty object
  assert.equal(resolveDeviceAssetKey(null), "unknown-device");
  assert.equal(resolveDeviceAssetKey(undefined), "unknown-device");
  assert.equal(resolveDeviceAssetKey({}), "unknown-device");
  assert.equal(resolveDeviceAssetKey("not an object"), "unknown-device");
});

test("resolveDeviceAsset returns full valid object with unknown-device fallback", () => {
  const asset = resolveDeviceAsset({ vendor: "MikroTik", model: "hAP ac lite" });
  assert.equal(asset.key, "mikrotik-hap-ac-lite");
  assert.equal(asset.category, "network");

  const unknown = resolveDeviceAsset(null);
  assert.equal(unknown.key, "unknown-device");
  assert.equal(unknown.category, "fallback");
});

// -----------------------------------------------------------------------------
// 3. Operational Status Orthogonality Tests
// -----------------------------------------------------------------------------

test("Operational status changes do NOT alter the resolved vector asset", () => {
  const baseDevice = { vendor: "MikroTik", model: "hAP ac lite" };

  const statuses = ["up", "online", "down", "offline", "warning", "degraded", "pending", "unknown"];
  for (const st of statuses) {
    const resolved = resolveDeviceAssetKey({ ...baseDevice, status: st });
    assert.equal(
      resolved,
      "mikrotik-hap-ac-lite",
      `Status '${st}' must not change the base asset key`
    );
  }
});

test("normalizeDeviceStatus normalizes various status synonyms into 6 canonical states", () => {
  assert.equal(normalizeDeviceStatus("up"), DEVICE_STATUSES.ONLINE);
  assert.equal(normalizeDeviceStatus("reachable"), DEVICE_STATUSES.ONLINE);
  assert.equal(normalizeDeviceStatus("down"), DEVICE_STATUSES.OFFLINE);
  assert.equal(normalizeDeviceStatus("failed"), DEVICE_STATUSES.OFFLINE);
  assert.equal(normalizeDeviceStatus("warning"), DEVICE_STATUSES.WARNING);
  assert.equal(normalizeDeviceStatus("degraded"), DEVICE_STATUSES.WARNING);
  assert.equal(normalizeDeviceStatus("pending"), DEVICE_STATUSES.PENDING);
  assert.equal(normalizeDeviceStatus("unmanaged"), DEVICE_STATUSES.UNMANAGED);
  assert.equal(normalizeDeviceStatus("gibberish"), DEVICE_STATUSES.UNKNOWN);
  assert.equal(normalizeDeviceStatus(null), DEVICE_STATUSES.UNKNOWN);
});

test("getDeviceStatusStyle returns distinct visual styles per status", () => {
  const onlineStyle = getDeviceStatusStyle("online");
  const offlineStyle = getDeviceStatusStyle("offline");
  const warningStyle = getDeviceStatusStyle("warning");

  assert.equal(onlineStyle.label, "ONLINE");
  assert.equal(onlineStyle.hexColor, "#10b981");

  assert.equal(offlineStyle.label, "OFFLINE");
  assert.equal(offlineStyle.hexColor, "#f43f5e");

  assert.equal(warningStyle.label, "WARNING");
  assert.equal(warningStyle.hexColor, "#f59e0b");
});

// -----------------------------------------------------------------------------
// 4. SVG Security & Vector Specification Compliance
// -----------------------------------------------------------------------------

test("All 27 assets pass vector security audit (no script, no javascript, no base64, viewBox 0 0 64 64)", () => {
  const assets = listDeviceAssets();

  for (const asset of assets) {
    const raw = asset.svgRaw;
    assert.ok(raw.includes('viewBox="0 0 64 64"'), `${asset.key} must have viewBox="0 0 64 64"`);
    assert.ok(!raw.toLowerCase().includes("<script"), `${asset.key} must not contain script tags`);
    assert.ok(!raw.toLowerCase().includes("javascript:"), `${asset.key} must not contain javascript: URIs`);
    assert.ok(!raw.toLowerCase().includes("base64"), `${asset.key} must not contain base64 payloads`);
    assert.ok(!raw.toLowerCase().includes("<img"), `${asset.key} must not contain <img> raster tags`);
    assert.ok(!raw.toLowerCase().includes("<foreignobject"), `${asset.key} must not contain foreignObject`);
  }
});

// -----------------------------------------------------------------------------
// 5. SVG Topology Exporter Tests
// -----------------------------------------------------------------------------

test("generateTopologySvg generates complete valid SVG document embedding device assets", () => {
  const mockNodes = [
    {
      id: "router-core",
      name: "Core-Router",
      ip: "192.168.88.1",
      vendor: "MikroTik",
      model: "hAP ac lite",
      status: "up",
      pos_x: 100,
      pos_y: 100,
    },
    {
      id: "sw-access",
      name: "Floor-Switch",
      ip: "192.168.88.2",
      device_type: "switch",
      status: "warning",
      pos_x: 400,
      pos_y: 100,
    },
    {
      id: "srv-db",
      name: "Database-Host",
      ip: "192.168.88.10",
      device_type: "server",
      model: "PostgreSQL Node",
      status: "down",
      pos_x: 400,
      pos_y: 300,
    },
  ];

  const mockLinks = [
    {
      id: "l1",
      source: "router-core",
      target: "sw-access",
      relationship_class: "physical",
      oper_status: "up",
    },
    {
      id: "l2",
      source: "sw-access",
      target: "srv-db",
      relationship_class: "layer2",
      oper_status: "down",
    },
  ];

  const svgXml = generateTopologySvg(mockNodes, mockLinks, {
    title: "Test Datacenter Topology",
  });

  assert.ok(svgXml.startsWith("<?xml version="), "Must begin with XML declaration");
  assert.ok(svgXml.includes("<svg xmlns="), "Must contain outer <svg> element");
  assert.ok(svgXml.includes('id="topology-edges"'), "Must contain topology-edges group");
  assert.ok(svgXml.includes('id="topology-nodes"'), "Must contain topology-nodes group");

  // Verify node cards are present
  assert.ok(svgXml.includes("Core-Router"), "Must contain node label Core-Router");
  assert.ok(svgXml.includes("Floor-Switch"), "Must contain node label Floor-Switch");
  assert.ok(svgXml.includes("Database-Host"), "Must contain node label Database-Host");

  // Verify status indicators are included
  assert.ok(svgXml.includes("ONLINE"), "Must contain ONLINE status");
  assert.ok(svgXml.includes("WARNING"), "Must contain WARNING status");
  assert.ok(svgXml.includes("OFFLINE"), "Must contain OFFLINE status");

  // Verify embedded device SVGs have 64x64 viewBox
  assert.ok(svgXml.includes('viewBox="0 0 64 64"'), "Must embed 64x64 device SVGs");
});

test("generateTopologySvg handles empty nodes array gracefully", () => {
  const emptySvg = generateTopologySvg([], []);
  assert.ok(emptySvg.includes("<svg"), "Must return valid SVG for empty graph");
  assert.ok(emptySvg.includes("No Topology Data Available"), "Must display placeholder message");
});
