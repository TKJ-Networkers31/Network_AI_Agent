/**
 * src/platform/adaptive-experience/svg/sceneGraph.js
 *
 * Declarative SVG Scene Graph Definition, Normalization & Blank-Node Protection.
 * Transforms raw diagram specifications, topology matrices, and protocol states (e.g. VRRP)
 * into a strongly-typed, validated scene graph ready for deterministic layout calculation.
 */

export const NODE_KINDS = Object.freeze({
  ROUTER: "router",
  SWITCH: "switch",
  SERVER: "server",
  CLOUD: "cloud",
  GATEWAY: "gateway",
  FIREWALL: "firewall",
  VRRP_VIRTUAL: "vrrp_virtual",
  CLUSTER: "cluster",
  GENERIC: "generic",
});

export const EDGE_KINDS = Object.freeze({
  PHYSICAL: "physical",
  LOGICAL: "logical",
  VRRP_ADVERTISEMENT: "vrrp_advertisement",
  FAILOVER_TRANSITION: "failover_transition",
  HEARTBEAT: "heartbeat",
  INFERRED: "inferred",
});

export const NODE_STATUSES = Object.freeze({
  ONLINE: "online",
  OFFLINE: "offline",
  DEGRADED: "degraded",
  MASTER: "master",
  BACKUP: "backup",
  UNKNOWN: "unknown",
});

/**
 * Validates and normalizes a single node with Blank Node Protection.
 */
export function normalizeNode(rawNode, index = 0) {
  if (!rawNode || typeof rawNode !== "object") {
    return {
      id: `node_gen_${index}`,
      kind: NODE_KINDS.GENERIC,
      title: `Node ${index + 1}`,
      subtitle: "Unspecified Node",
      status: NODE_STATUSES.UNKNOWN,
      icon: "server",
      badges: ["UNSPECIFIED"],
      metadata: {},
      isCluster: false,
    };
  }

  const id = String(rawNode.id || rawNode.name || `node_${index}`);
  
  // Blank Node Protection: Ensure title is never empty or unexplained
  let title = rawNode.title || rawNode.name || rawNode.label || "";
  let subtitle = rawNode.subtitle || rawNode.description || rawNode.ip || "";
  let status = (rawNode.status || NODE_STATUSES.ONLINE).toLowerCase();
  const badges = Array.isArray(rawNode.badges) ? [...rawNode.badges] : [];

  if (!title.trim()) {
    title = `Perangkat ${id}`;
    if (!badges.includes("FALLBACK_LABEL")) {
      badges.push("FALLBACK_LABEL");
    }
  }

  // Kind mapping
  let kind = (rawNode.kind || rawNode.type || NODE_KINDS.ROUTER).toLowerCase();
  if (kind.includes("vrrp") || kind.includes("virtual")) {
    kind = NODE_KINDS.VRRP_VIRTUAL;
  } else if (kind.includes("switch")) {
    kind = NODE_KINDS.SWITCH;
  } else if (kind.includes("server")) {
    kind = NODE_KINDS.SERVER;
  } else if (kind.includes("cluster") || rawNode.isCluster || (rawNode.members && rawNode.members.length > 0)) {
    kind = NODE_KINDS.CLUSTER;
  } else if (!Object.values(NODE_KINDS).includes(kind)) {
    kind = NODE_KINDS.ROUTER;
  }

  const isCluster = kind === NODE_KINDS.CLUSTER;
  const memberCount = Array.isArray(rawNode.members) ? rawNode.members.length : (rawNode.memberCount || 1);

  return {
    id,
    kind,
    title: title.trim(),
    subtitle: subtitle.trim(),
    status,
    ip: rawNode.ip || rawNode.host || "",
    vendor: rawNode.vendor || "MikroTik",
    model: rawNode.model || (kind === NODE_KINDS.VRRP_VIRTUAL ? "Virtual Router" : "RouterOS"),
    icon: rawNode.icon || (kind === NODE_KINDS.VRRP_VIRTUAL ? "shield" : kind),
    badges,
    isCluster,
    memberCount,
    members: Array.isArray(rawNode.members) ? rawNode.members : [],
    metadata: rawNode.metadata && typeof rawNode.metadata === "object" ? rawNode.metadata : {},
  };
}

/**
 * Validates and normalizes an edge connecting two nodes.
 */
export function normalizeEdge(rawEdge, validNodeIds, index = 0) {
  if (!rawEdge || typeof rawEdge !== "object") return null;

  const source = String(rawEdge.source || rawEdge.from || "");
  const target = String(rawEdge.target || rawEdge.to || "");

  if (!source || !target || !validNodeIds.has(source) || !validNodeIds.has(target)) {
    return null;
  }

  const id = String(rawEdge.id || `edge_${source}_${target}_${index}`);
  const label = String(rawEdge.label || rawEdge.title || "").trim();
  const kind = (rawEdge.kind || rawEdge.type || EDGE_KINDS.PHYSICAL).toLowerCase();
  const status = (rawEdge.status || "up").toLowerCase();
  const trafficFlow = Boolean(rawEdge.trafficFlow ?? rawEdge.animated ?? (status === "up"));
  const direction = rawEdge.direction || "forward"; // forward, bidirectional

  return {
    id,
    source,
    target,
    label,
    kind,
    status,
    trafficFlow,
    direction,
    metadata: rawEdge.metadata || {},
  };
}

/**
 * Builds a complete normalized Scene Graph from raw data.
 */
export function buildSceneGraph(rawGraph) {
  if (!rawGraph || typeof rawGraph !== "object") {
    return { nodes: [], edges: [], title: "", type: "generic" };
  }

  const rawNodes = Array.isArray(rawGraph.nodes) ? rawGraph.nodes : [];
  const rawEdges = Array.isArray(rawGraph.edges) ? rawGraph.edges : [];

  const nodes = rawNodes.map((n, i) => normalizeNode(n, i));
  const validIds = new Set(nodes.map((n) => n.id));

  const edges = rawEdges
    .map((e, i) => normalizeEdge(e, validIds, i))
    .filter(Boolean);

  return {
    title: rawGraph.title || rawGraph.label || "Network Architecture & Topology",
    type: rawGraph.type || "topology",
    nodes,
    edges,
    clusters: nodes.filter((n) => n.isCluster),
  };
}

/**
 * Dedicated builder for high-fidelity VRRP Failover State Diagrams.
 * Resolves all requirements of Phase 2 & 3 for VRRP failover visualization.
 */
export function buildVrrpFailoverSceneGraph(options = {}) {
  const {
    masterName = "R1-Master",
    masterIp = "192.168.1.2",
    masterPriority = 150,
    backupName = "R2-Backup",
    backupIp = "192.168.1.3",
    backupPriority = 100,
    virtualIp = "192.168.1.1",
    vrid = 10,
    isMasterFailing = false,
  } = options;

  const nodes = [
    {
      id: "vrrp_vip",
      kind: NODE_KINDS.VRRP_VIRTUAL,
      title: `VRRP VIP: ${virtualIp}`,
      subtitle: `VRID ${vrid} | Active Gateway`,
      status: NODE_STATUSES.ONLINE,
      icon: "shield",
      badges: [`VRID: ${vrid}`, "VIP"],
      metadata: {
        virtual_ip: virtualIp,
        vrid,
        active_owner: isMasterFailing ? backupName : masterName,
      },
    },
    {
      id: "vrrp_master",
      kind: NODE_KINDS.ROUTER,
      title: masterName,
      subtitle: `${masterIp} (Pri: ${masterPriority})`,
      status: isMasterFailing ? NODE_STATUSES.OFFLINE : NODE_STATUSES.MASTER,
      icon: "router",
      badges: [isMasterFailing ? "FAILOVER" : "MASTER", `Pri: ${masterPriority}`],
      metadata: {
        priority: masterPriority,
        role: "MASTER",
        ip: masterIp,
        interface: "ether1",
        state: isMasterFailing ? "FAULT / DOWN" : "MASTER_ACTIVE",
      },
    },
    {
      id: "vrrp_backup",
      kind: NODE_KINDS.ROUTER,
      title: backupName,
      subtitle: `${backupIp} (Pri: ${backupPriority})`,
      status: isMasterFailing ? NODE_STATUSES.MASTER : NODE_STATUSES.BACKUP,
      icon: "router",
      badges: [isMasterFailing ? "NEW MASTER" : "BACKUP", `Pri: ${backupPriority}`],
      metadata: {
        priority: backupPriority,
        role: isMasterFailing ? "ELECTED_MASTER" : "BACKUP",
        ip: backupIp,
        interface: "ether1",
        preempt: true,
      },
    },
    {
      id: "lan_switch",
      kind: NODE_KINDS.SWITCH,
      title: "SW-LAN-Dist",
      subtitle: "VLAN 10 Distribution Switch",
      status: NODE_STATUSES.ONLINE,
      icon: "switch",
      badges: ["L2 CORE"],
      metadata: { vlan: 10 },
    },
  ];

  const edges = [
    {
      id: "edge_master_vip",
      source: "vrrp_master",
      target: "vrrp_vip",
      kind: EDGE_KINDS.LOGICAL,
      label: isMasterFailing ? "Link Down (Hold Expired)" : "Hosts VIP (Master Ownership)",
      status: isMasterFailing ? "down" : "up",
      trafficFlow: !isMasterFailing,
      direction: "forward",
    },
    {
      id: "edge_backup_vip",
      source: "vrrp_backup",
      target: "vrrp_vip",
      kind: EDGE_KINDS.LOGICAL,
      label: isMasterFailing ? "Assume Master (Gratuitous ARP)" : "Standby Route",
      status: "up",
      trafficFlow: isMasterFailing,
      direction: "forward",
    },
    {
      id: "edge_vrrp_heartbeat",
      source: "vrrp_master",
      target: "vrrp_backup",
      kind: EDGE_KINDS.VRRP_ADVERTISEMENT,
      label: isMasterFailing ? "Adv Lost (3x Interval)" : "VRRP Adv (Interval: 1s, Multicast 224.0.0.18)",
      status: isMasterFailing ? "down" : "up",
      trafficFlow: !isMasterFailing,
      direction: "forward",
    },
    {
      id: "edge_master_lan",
      source: "vrrp_master",
      target: "lan_switch",
      kind: EDGE_KINDS.PHYSICAL,
      label: "Trunk 1G",
      status: isMasterFailing ? "down" : "up",
      trafficFlow: !isMasterFailing,
      direction: "bidirectional",
    },
    {
      id: "edge_backup_lan",
      source: "vrrp_backup",
      target: "lan_switch",
      kind: EDGE_KINDS.PHYSICAL,
      label: "Trunk 1G",
      status: "up",
      trafficFlow: true,
      direction: "bidirectional",
    },
  ];

  return {
    title: `VRRP High-Availability Failover (${virtualIp})`,
    type: "vrrp",
    nodes,
    edges,
    metadata: {
      vrid,
      virtualIp,
      masterPriority,
      backupPriority,
      isMasterFailing,
    },
  };
}
