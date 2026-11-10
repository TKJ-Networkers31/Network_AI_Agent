import {
  RouterGenericSvg,
  MikrotikRouterGenericSvg,
  MikrotikHapAcLiteSvg,
  MikrotikRb951UiSvg,
  SwitchL2Svg,
  SwitchL3Svg,
  FirewallSvg,
  AccessPointSvg,
  AccessPointOutdoorSvg,
  WirelessBridgeSvg,
  ModemSvg,
  OntSvg,
  IspGatewaySvg,
  InternetCloudSvg,
  ServerRackSvg,
  ServerTowerSvg,
  ServerVirtualizationSvg,
  NasStorageSvg,
  ServerDatabaseSvg,
  WorkstationSvg,
  LaptopSvg,
  SmartphoneSvg,
  PrinterSvg,
  CctvCameraSvg,
  IotDeviceSvg,
  UnknownDeviceSvg,
  UnmanagedDeviceSvg,
  DEVICE_SVG_RAW,
} from "./deviceSvgCatalog.js";

/**
 * VERA Device Asset Registry
 * Centralized, model-aware, deterministic vector device asset library.
 * Designed for @xyflow/react interactive canvas & static SVG export.
 */

export const DEVICE_ASSET_REGISTRY = {
  // 1. Network Infrastructure
  "router-generic": {
    key: "router-generic",
    label: "Generic Router",
    category: "network",
    component: RouterGenericSvg,
    svgRaw: DEVICE_SVG_RAW["router-generic"],
    defaultPorts: 5,
    tags: ["router", "routing", "gateway", "cisco", "juniper", "generic_router", "edge"],
    isManagedDefault: true,
  },
  "mikrotik-router-generic": {
    key: "mikrotik-router-generic",
    label: "MikroTik Router",
    category: "network",
    component: MikrotikRouterGenericSvg,
    svgRaw: DEVICE_SVG_RAW["mikrotik-router-generic"],
    defaultPorts: 5,
    tags: ["mikrotik", "routeros", "ccr", "rb", "routerboard", "mikrotik_router"],
    isManagedDefault: true,
  },
  "mikrotik-hap-ac-lite": {
    key: "mikrotik-hap-ac-lite",
    label: "MikroTik hAP ac lite",
    category: "network",
    component: MikrotikHapAcLiteSvg,
    svgRaw: DEVICE_SVG_RAW["mikrotik-hap-ac-lite"],
    defaultPorts: 5,
    tags: ["mikrotik", "hap", "hap ac lite", "rb952ui-5ac2nd", "rb952", "dual-band"],
    isManagedDefault: true,
  },
  "mikrotik-rb951ui-2hnd": {
    key: "mikrotik-rb951ui-2hnd",
    label: "MikroTik RB951Ui-2HnD",
    category: "network",
    component: MikrotikRb951UiSvg,
    svgRaw: DEVICE_SVG_RAW["mikrotik-rb951ui-2hnd"],
    defaultPorts: 5,
    tags: ["mikrotik", "rb951", "rb951ui", "rb951ui-2hnd", "high-power", "soho"],
    isManagedDefault: true,
  },
  "switch-l2": {
    key: "switch-l2",
    label: "Generic L2 Switch",
    category: "network",
    component: SwitchL2Svg,
    svgRaw: DEVICE_SVG_RAW["switch-l2"],
    defaultPorts: 24,
    tags: ["switch", "l2", "layer2", "access_switch", "managed_switch", "switching"],
    isManagedDefault: true,
  },
  "switch-l3": {
    key: "switch-l3",
    label: "Generic L3 Switch",
    category: "network",
    component: SwitchL3Svg,
    svgRaw: DEVICE_SVG_RAW["switch-l3"],
    defaultPorts: 28,
    tags: ["switch_l3", "l3_switch", "multilayer", "core_switch", "distribution", "crs"],
    isManagedDefault: true,
  },
  "firewall": {
    key: "firewall",
    label: "Firewall Appliance",
    category: "network",
    component: FirewallSvg,
    svgRaw: DEVICE_SVG_RAW["firewall"],
    defaultPorts: 4,
    tags: ["firewall", "pfsense", "fortinet", "opnsense", "security", "utm", "appliance"],
    isManagedDefault: true,
  },
  "access-point": {
    key: "access-point",
    label: "Wireless Access Point",
    category: "network",
    component: AccessPointSvg,
    svgRaw: DEVICE_SVG_RAW["access-point"],
    defaultPorts: 1,
    tags: ["access_point", "ap", "wifi", "wlan", "unifi", "cap", "wireless_ap", "omada"],
    isManagedDefault: true,
  },
  "access-point-outdoor": {
    key: "access-point-outdoor",
    label: "Outdoor Access Point",
    category: "network",
    component: AccessPointOutdoorSvg,
    svgRaw: DEVICE_SVG_RAW["access-point-outdoor"],
    defaultPorts: 1,
    tags: ["outdoor_ap", "pole_ap", "wisp", "rugged_ap", "cap_outdoor", "mesh_outdoor"],
    isManagedDefault: true,
  },
  "wireless-bridge": {
    key: "wireless-bridge",
    label: "Wireless Bridge / Dish",
    category: "network",
    component: WirelessBridgeSvg,
    svgRaw: DEVICE_SVG_RAW["wireless-bridge"],
    defaultPorts: 1,
    tags: ["bridge", "wireless_bridge", "ptp", "ptmp", "dish", "airmax", "lhg", "sxt"],
    isManagedDefault: true,
  },
  "modem": {
    key: "modem",
    label: "Modem / DOCSIS",
    category: "network",
    component: ModemSvg,
    svgRaw: DEVICE_SVG_RAW["modem"],
    defaultPorts: 1,
    tags: ["modem", "cable_modem", "dsl", "docsis", "cpe", "broadband"],
    isManagedDefault: false,
  },
  "ont": {
    key: "ont",
    label: "Optical Network Terminal",
    category: "network",
    component: OntSvg,
    svgRaw: DEVICE_SVG_RAW["ont"],
    defaultPorts: 4,
    tags: ["ont", "onu", "gpon", "epon", "fiber", "ftth", "optical"],
    isManagedDefault: true,
  },
  "isp-gateway": {
    key: "isp-gateway",
    label: "ISP Gateway / Core Edge",
    category: "network",
    component: IspGatewaySvg,
    svgRaw: DEVICE_SVG_RAW["isp-gateway"],
    defaultPorts: 16,
    tags: ["isp_gateway", "bgp", "core_router", "upstream", "edge_router", "transit"],
    isManagedDefault: true,
  },
  "internet-cloud": {
    key: "internet-cloud",
    label: "Internet Cloud",
    category: "network",
    component: InternetCloudSvg,
    svgRaw: DEVICE_SVG_RAW["internet-cloud"],
    defaultPorts: 0,
    tags: ["internet", "cloud", "wan", "external", "public_network", "upstream_wan"],
    isManagedDefault: false,
  },

  // 2. Compute Infrastructure
  "server-rack": {
    key: "server-rack",
    label: "Rack Server",
    category: "compute",
    component: ServerRackSvg,
    svgRaw: DEVICE_SVG_RAW["server-rack"],
    defaultPorts: 4,
    tags: ["server", "rack_server", "compute", "blade", "dell_poweredge", "hpe_proliant"],
    isManagedDefault: true,
  },
  "server-tower": {
    key: "server-tower",
    label: "Tower Server",
    category: "compute",
    component: ServerTowerSvg,
    svgRaw: DEVICE_SVG_RAW["server-tower"],
    defaultPorts: 2,
    tags: ["server_tower", "tower", "office_server", "pedestal"],
    isManagedDefault: true,
  },
  "server-virtualization": {
    key: "server-virtualization",
    label: "Virtualization Host",
    category: "compute",
    component: ServerVirtualizationSvg,
    svgRaw: DEVICE_SVG_RAW["server-virtualization"],
    defaultPorts: 4,
    tags: ["hypervisor", "virtualization", "esxi", "proxmox", "kvm", "vmware", "xen"],
    isManagedDefault: true,
  },
  "nas-storage": {
    key: "nas-storage",
    label: "NAS / Storage Array",
    category: "compute",
    component: NasStorageSvg,
    svgRaw: DEVICE_SVG_RAW["nas-storage"],
    defaultPorts: 2,
    tags: ["nas", "storage", "synology", "qnap", "truenas", "san", "iscsi", "nfs"],
    isManagedDefault: true,
  },
  "server-database": {
    key: "server-database",
    label: "Database Server",
    category: "compute",
    component: ServerDatabaseSvg,
    svgRaw: DEVICE_SVG_RAW["server-database"],
    defaultPorts: 2,
    tags: ["database", "db_server", "sql", "postgres", "mysql", "mongodb", "oracle"],
    isManagedDefault: true,
  },

  // 3. End Devices
  "workstation": {
    key: "workstation",
    label: "Desktop Workstation",
    category: "endpoint",
    component: WorkstationSvg,
    svgRaw: DEVICE_SVG_RAW["workstation"],
    defaultPorts: 1,
    tags: ["workstation", "desktop", "pc", "client", "office_pc"],
    isManagedDefault: false,
  },
  "laptop": {
    key: "laptop",
    label: "Laptop",
    category: "endpoint",
    component: LaptopSvg,
    svgRaw: DEVICE_SVG_RAW["laptop"],
    defaultPorts: 1,
    tags: ["laptop", "notebook", "macbook", "portable", "wireless_client"],
    isManagedDefault: false,
  },
  "smartphone": {
    key: "smartphone",
    label: "Smartphone",
    category: "endpoint",
    component: SmartphoneSvg,
    svgRaw: DEVICE_SVG_RAW["smartphone"],
    defaultPorts: 0,
    tags: ["smartphone", "phone", "mobile", "android", "iphone", "byod"],
    isManagedDefault: false,
  },
  "printer": {
    key: "printer",
    label: "Network Printer",
    category: "endpoint",
    component: PrinterSvg,
    svgRaw: DEVICE_SVG_RAW["printer"],
    defaultPorts: 1,
    tags: ["printer", "mfd", "copier", "network_printer", "ipp"],
    isManagedDefault: false,
  },
  "cctv-camera": {
    key: "cctv-camera",
    label: "CCTV Camera",
    category: "endpoint",
    component: CctvCameraSvg,
    svgRaw: DEVICE_SVG_RAW["cctv-camera"],
    defaultPorts: 1,
    tags: ["cctv", "camera", "ipcam", "surveillance", "onvif", "security_camera"],
    isManagedDefault: false,
  },
  "iot-device": {
    key: "iot-device",
    label: "IoT / Embedded Device",
    category: "endpoint",
    component: IotDeviceSvg,
    svgRaw: DEVICE_SVG_RAW["iot-device"],
    defaultPorts: 1,
    tags: ["iot", "sensor", "esp32", "arduino", "raspberry", "embedded", "smart_device"],
    isManagedDefault: false,
  },

  // 4. Fallback Assets
  "unknown-device": {
    key: "unknown-device",
    label: "Unknown Network Device",
    category: "fallback",
    component: UnknownDeviceSvg,
    svgRaw: DEVICE_SVG_RAW["unknown-device"],
    defaultPorts: 0,
    tags: ["unknown", "generic", "unrecognized"],
    isManagedDefault: false,
  },
  "unmanaged-device": {
    key: "unmanaged-device",
    label: "Unmanaged Device",
    category: "fallback",
    component: UnmanagedDeviceSvg,
    svgRaw: DEVICE_SVG_RAW["unmanaged-device"],
    defaultPorts: 0,
    tags: ["unmanaged", "passive", "bypass", "third_party", "shadow_it"],
    isManagedDefault: false,
  },
};

/**
 * Normalizes device properties into lowercase clean strings
 */
export function normalizeDeviceIdentity(device = {}) {
  if (!device || typeof device !== "object") {
    return {
      vendor: "",
      model: "",
      deviceType: "",
      name: "",
      isManaged: true,
      rawStatus: "unknown",
    };
  }

  const vendor = String(device.vendor || device.manufacturer || "").toLowerCase().trim();
  const model = String(device.model || device.hardware || device.device_model || "").toLowerCase().trim();
  const deviceType = String(
    device.device_type ||
      device.type ||
      device.category ||
      device.role ||
      device.classification ||
      ""
  )
    .toLowerCase()
    .trim();
  const name = String(device.name || device.label || device.hostname || device.id || "").toLowerCase().trim();

  // Check unmanaged signals
  const statusStr = String(device.status || device.oper_status || "").toLowerCase().trim();
  const isManaged =
    device.is_managed !== false &&
    device.managed !== false &&
    deviceType !== "unmanaged" &&
    deviceType !== "unmanaged_device" &&
    statusStr !== "unmanaged";

  return {
    vendor,
    model,
    deviceType,
    name,
    isManaged,
    rawStatus: statusStr,
  };
}

/**
 * Deterministic Device Asset Resolution Pipeline
 * Resolves any device metadata to the most accurate vector asset key.
 * Never throws, always returns a valid registered asset entry.
 *
 * Priority:
 * 1. Unmanaged override (if explicitly unmanaged)
 * 2. Exact Vendor + Model matching (e.g. MikroTik hAP ac lite, RB951Ui-2HnD)
 * 3. Model keyword matching (without vendor prefix)
 * 4. Vendor + Device Class matching (e.g. MikroTik + Router -> mikrotik-router-generic)
 * 5. Device Class / Category matching
 * 6. Fallback: unmanaged-device (if unmanaged) or unknown-device
 */
export function resolveDeviceAssetKey(device = {}) {
  const { vendor, model, deviceType, name, isManaged } = normalizeDeviceIdentity(device);

  // 1. Explicit unmanaged check
  if (!isManaged || deviceType === "unmanaged" || deviceType === "unmanaged_device") {
    return "unmanaged-device";
  }

  const combinedSearch = `${vendor} ${model} ${deviceType} ${name}`.toLowerCase();

  // 2. Exact Model Matching (High Specificity)
  // 2a. MikroTik hAP ac lite (or RB952)
  if (
    combinedSearch.includes("hap ac lite") ||
    combinedSearch.includes("hap_ac_lite") ||
    combinedSearch.includes("hap-ac-lite") ||
    combinedSearch.includes("rb952")
  ) {
    return "mikrotik-hap-ac-lite";
  }

  // 2b. MikroTik RB951Ui-2HnD (or RB951)
  if (
    combinedSearch.includes("rb951ui") ||
    combinedSearch.includes("rb951") ||
    combinedSearch.includes("rb-951")
  ) {
    return "mikrotik-rb951ui-2hnd";
  }

  // 3. Vendor + Device Class
  // MikroTik Routers
  if (
    vendor.includes("mikrotik") ||
    vendor.includes("routerboard") ||
    combinedSearch.includes("routeros") ||
    combinedSearch.includes("routerboard") ||
    combinedSearch.includes("ccr")
  ) {
    if (combinedSearch.includes("switch") || combinedSearch.includes("crs")) {
      return combinedSearch.includes("l3") ? "switch-l3" : "switch-l2";
    }
    if (combinedSearch.includes("ap") || combinedSearch.includes("wireless") || combinedSearch.includes("cap")) {
      return combinedSearch.includes("outdoor") ? "access-point-outdoor" : "access-point";
    }
    if (combinedSearch.includes("lhg") || combinedSearch.includes("sxt") || combinedSearch.includes("dish")) {
      return "wireless-bridge";
    }
    return "mikrotik-router-generic";
  }

  // 4. Device Class Resolution
  // 4a. Core Edge / ISP Gateway
  if (
    combinedSearch.includes("isp_gateway") ||
    combinedSearch.includes("isp gateway") ||
    combinedSearch.includes("bgp") ||
    combinedSearch.includes("core router") ||
    combinedSearch.includes("core_router") ||
    combinedSearch.includes("edge router") ||
    combinedSearch.includes("edge_router") ||
    combinedSearch.includes("upstream")
  ) {
    return "isp-gateway";
  }

  // 4b. Internet Cloud / External WAN
  if (
    deviceType === "internet" ||
    deviceType === "internet_gateway" ||
    deviceType === "cloud" ||
    deviceType === "wan" ||
    name === "internet" ||
    name === "wan" ||
    name === "cloud"
  ) {
    return "internet-cloud";
  }

  // 4c. Firewalls & Security
  if (
    deviceType === "firewall" ||
    combinedSearch.includes("firewall") ||
    combinedSearch.includes("pfsense") ||
    combinedSearch.includes("fortigate") ||
    combinedSearch.includes("fortinet") ||
    combinedSearch.includes("opnsense") ||
    combinedSearch.includes("security gateway")
  ) {
    return "firewall";
  }

  // 4d. Optical Network Terminal (ONT / GPON / Fiber)
  if (
    deviceType === "ont" ||
    deviceType === "onu" ||
    combinedSearch.includes("gpon") ||
    combinedSearch.includes("epon") ||
    combinedSearch.includes("ont") ||
    combinedSearch.includes("onu") ||
    combinedSearch.includes("fiber terminal")
  ) {
    return "ont";
  }

  // 4e. Broadband Modem
  if (
    deviceType === "modem" ||
    combinedSearch.includes("modem") ||
    combinedSearch.includes("docsis") ||
    combinedSearch.includes("dsl")
  ) {
    return "modem";
  }

  // 4f. Wireless Bridges / Dishes
  if (
    deviceType === "wireless_bridge" ||
    deviceType === "bridge" ||
    combinedSearch.includes("wireless bridge") ||
    combinedSearch.includes("dish") ||
    combinedSearch.includes("airmax") ||
    combinedSearch.includes("ptp") ||
    combinedSearch.includes("nanostation")
  ) {
    return "wireless-bridge";
  }

  // 4g. Outdoor Access Points
  if (
    deviceType === "access_point_outdoor" ||
    deviceType === "outdoor_ap" ||
    (combinedSearch.includes("outdoor") && (combinedSearch.includes("ap") || combinedSearch.includes("access point")))
  ) {
    return "access-point-outdoor";
  }

  // 4h. Standard Indoor Access Point
  if (
    deviceType === "access_point" ||
    deviceType === "ap" ||
    deviceType === "wifi" ||
    combinedSearch.includes("unifi") ||
    combinedSearch.includes("access point") ||
    combinedSearch.includes("access_point")
  ) {
    return "access-point";
  }

  // 4i. L3 Switches vs L2 Switches
  if (
    deviceType === "switch_l3" ||
    deviceType === "l3_switch" ||
    combinedSearch.includes("l3 switch") ||
    combinedSearch.includes("multilayer switch") ||
    combinedSearch.includes("core switch")
  ) {
    return "switch-l3";
  }

  if (
    deviceType === "switch" ||
    deviceType === "switch_l2" ||
    deviceType === "l2_switch" ||
    combinedSearch.includes("switch") ||
    combinedSearch.includes("switching")
  ) {
    return "switch-l2";
  }

  // 4j. Generic Routers
  if (
    deviceType === "router" ||
    deviceType === "generic_router" ||
    combinedSearch.includes("router") ||
    combinedSearch.includes("cisco") ||
    combinedSearch.includes("juniper") ||
    combinedSearch.includes("vyos")
  ) {
    return "router-generic";
  }

  // 4k. Compute Infrastructure
  if (
    combinedSearch.includes("database") ||
    combinedSearch.includes("db_server") ||
    combinedSearch.includes("postgres") ||
    combinedSearch.includes("mysql") ||
    combinedSearch.includes("mongodb") ||
    combinedSearch.includes("sql server")
  ) {
    return "server-database";
  }

  if (
    combinedSearch.includes("nas") ||
    combinedSearch.includes("storage") ||
    combinedSearch.includes("synology") ||
    combinedSearch.includes("qnap") ||
    combinedSearch.includes("truenas") ||
    combinedSearch.includes("san")
  ) {
    return "nas-storage";
  }

  if (
    combinedSearch.includes("hypervisor") ||
    combinedSearch.includes("virtualization") ||
    combinedSearch.includes("esxi") ||
    combinedSearch.includes("proxmox") ||
    combinedSearch.includes("vmware") ||
    combinedSearch.includes("kvm")
  ) {
    return "server-virtualization";
  }

  if (combinedSearch.includes("tower server") || combinedSearch.includes("server_tower")) {
    return "server-tower";
  }

  if (deviceType === "server" || combinedSearch.includes("server") || combinedSearch.includes("compute")) {
    return "server-rack";
  }

  // 4l. End Devices
  if (
    deviceType === "printer" ||
    combinedSearch.includes("printer") ||
    combinedSearch.includes("mfd") ||
    combinedSearch.includes("copier")
  ) {
    return "printer";
  }

  if (
    deviceType === "cctv" ||
    deviceType === "camera" ||
    combinedSearch.includes("cctv") ||
    combinedSearch.includes("camera") ||
    combinedSearch.includes("ipcam") ||
    combinedSearch.includes("surveillance")
  ) {
    return "cctv-camera";
  }

  if (
    deviceType === "iot" ||
    deviceType === "sensor" ||
    combinedSearch.includes("iot") ||
    combinedSearch.includes("sensor") ||
    combinedSearch.includes("esp32") ||
    combinedSearch.includes("arduino") ||
    combinedSearch.includes("raspberry")
  ) {
    return "iot-device";
  }

  if (
    deviceType === "smartphone" ||
    deviceType === "phone" ||
    deviceType === "mobile" ||
    combinedSearch.includes("phone") ||
    combinedSearch.includes("android") ||
    combinedSearch.includes("iphone")
  ) {
    return "smartphone";
  }

  if (
    deviceType === "laptop" ||
    combinedSearch.includes("laptop") ||
    combinedSearch.includes("notebook") ||
    combinedSearch.includes("macbook")
  ) {
    return "laptop";
  }

  if (
    deviceType === "workstation" ||
    deviceType === "desktop" ||
    deviceType === "client" ||
    deviceType === "pc" ||
    combinedSearch.includes("workstation") ||
    combinedSearch.includes("desktop") ||
    combinedSearch.includes("pc")
  ) {
    return "workstation";
  }

  // 5. Ultimate Fallback
  return "unknown-device";
}

/**
 * Resolves a device object to its full registered asset metadata
 * Guarantees a valid asset object is always returned.
 */
export function resolveDeviceAsset(device = {}) {
  const assetKey = resolveDeviceAssetKey(device);
  return getDeviceAsset(assetKey);
}

/**
 * Retrieves asset metadata by key, with unknown-device fallback
 */
export function getDeviceAsset(assetKey = "unknown-device") {
  if (assetKey && DEVICE_ASSET_REGISTRY[assetKey]) {
    return DEVICE_ASSET_REGISTRY[assetKey];
  }
  return DEVICE_ASSET_REGISTRY["unknown-device"];
}

/**
 * Returns array of all registered assets
 */
export function listDeviceAssets() {
  return Object.values(DEVICE_ASSET_REGISTRY);
}

/**
 * Returns array of assets filtered by category
 */
export function listDeviceAssetsByCategory(category) {
  return Object.values(DEVICE_ASSET_REGISTRY).filter((a) => a.category === category);
}
