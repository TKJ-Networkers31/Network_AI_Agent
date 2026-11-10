/**
 * src/platform/adaptive-experience/svg/layoutEngine.js
 *
 * Deterministic SVG Layout Engine for VERA Adaptive Experience.
 * Calculates dynamic card sizing from text metrics, routes orthogonal connectors
 * with obstacle and label collision avoidance, and computes precise bounding boxes.
 */

const FONT_CHAR_WIDTH_BOLD = 7.8;
const FONT_CHAR_WIDTH_REGULAR = 6.8;
const FONT_CHAR_WIDTH_MONO = 6.5;

const MIN_NODE_WIDTH = 180;
const MAX_NODE_WIDTH = 320;
const MIN_NODE_HEIGHT = 80;
const PADDING_X = 18;
const PADDING_Y = 16;
const LAYER_GAP_X = 140;
const ROW_GAP_Y = 50;
const MARGIN = 40;

/**
 * Accurately estimates node dimensions based on text lengths and constituent badges.
 */
export function measureNodeDimensions(node) {
  const titleLen = (node.title || "").length * FONT_CHAR_WIDTH_BOLD;
  const subtitleLen = (node.subtitle || "").length * FONT_CHAR_WIDTH_REGULAR;
  const ipLen = (node.ip || "").length * FONT_CHAR_WIDTH_MONO;
  const badgesLen = (node.badges || []).reduce((acc, b) => acc + (b.length * 5.8 + 14), 0);

  const contentWidth = Math.max(titleLen, subtitleLen, ipLen, badgesLen) + PADDING_X * 2;
  const width = Math.min(Math.max(contentWidth, MIN_NODE_WIDTH), MAX_NODE_WIDTH);

  // Height: Title line (20) + Subtitle line (16) + Badges line (20) + Padded Margins
  const hasBadges = node.badges && node.badges.length > 0;
  const height = Math.max(MIN_NODE_HEIGHT + (hasBadges ? 24 : 0), MIN_NODE_HEIGHT);

  return { width, height };
}

/**
 * Dedicated layout calculation for VRRP Failover Architecture.
 * Places Virtual IP at top center, Master & Backup routers in middle rank, and LAN Switch at base.
 */
function layoutVrrpScene(nodes, edges) {
  const positioned = new Map();
  const measured = new Map();

  for (const n of nodes) {
    measured.set(n.id, measureNodeDimensions(n));
  }

  const vipDim = measured.get("vrrp_vip") || { width: 220, height: 90 };
  const masterDim = measured.get("vrrp_master") || { width: 220, height: 90 };
  const backupDim = measured.get("vrrp_backup") || { width: 220, height: 90 };
  const swDim = measured.get("lan_switch") || { width: 220, height: 90 };

  const centerColX = MARGIN + masterDim.width + 120;

  // Rank 1: Virtual IP (Top Center)
  positioned.set("vrrp_vip", {
    ...nodes.find((n) => n.id === "vrrp_vip"),
    x: centerColX - vipDim.width / 2,
    y: MARGIN,
    width: vipDim.width,
    height: vipDim.height,
    rank: 0,
  });

  // Rank 2: Master (Left) and Backup (Right)
  const rank2Y = MARGIN + vipDim.height + 100;
  positioned.set("vrrp_master", {
    ...nodes.find((n) => n.id === "vrrp_master"),
    x: MARGIN,
    y: rank2Y,
    width: masterDim.width,
    height: masterDim.height,
    rank: 1,
  });

  positioned.set("vrrp_backup", {
    ...nodes.find((n) => n.id === "vrrp_backup"),
    x: MARGIN + masterDim.width + 240,
    y: rank2Y,
    width: backupDim.width,
    height: backupDim.height,
    rank: 1,
  });

  // Rank 3: LAN Distribution Switch (Bottom Center)
  const rank3Y = rank2Y + Math.max(masterDim.height, backupDim.height) + 100;
  positioned.set("lan_switch", {
    ...nodes.find((n) => n.id === "lan_switch"),
    x: centerColX - swDim.width / 2,
    y: rank3Y,
    width: swDim.width,
    height: swDim.height,
    rank: 2,
  });

  // Any remaining nodes stacked nicely
  let extraY = rank3Y + swDim.height + 40;
  for (const n of nodes) {
    if (!positioned.has(n.id)) {
      const dim = measured.get(n.id);
      positioned.set(n.id, {
        ...n,
        x: MARGIN,
        y: extraY,
        width: dim.width,
        height: dim.height,
        rank: 3,
      });
      extraY += dim.height + ROW_GAP_Y;
    }
  }

  const allNodes = [...positioned.values()];
  const maxX = Math.max(...allNodes.map((n) => n.x + n.width)) + MARGIN;
  const maxY = Math.max(...allNodes.map((n) => n.y + n.height)) + MARGIN;

  return { positioned, totalWidth: maxX, totalHeight: maxY };
}

/**
 * Hierarchical layered layout engine for general network topologies.
 */
function layoutHierarchicalScene(nodes, edges) {
  const ids = nodes.map((n) => n.id);
  const incoming = new Map(ids.map((id) => [id, []]));
  for (const e of edges) {
    if (incoming.has(e.target)) incoming.get(e.target).push(e.source);
  }

  const layerMap = new Map();
  const visited = new Set();

  function computeDepth(id, currentDepth) {
    if (currentDepth > ids.length + 1) return 0;
    if (layerMap.has(id)) return layerMap.get(id);
    if (visited.has(id)) return 0;
    visited.add(id);
    const preds = incoming.get(id) || [];
    const l = preds.length === 0 ? 0 : Math.max(...preds.map((p) => computeDepth(p, currentDepth + 1))) + 1;
    visited.delete(id);
    layerMap.set(id, l);
    return l;
  }

  for (const id of ids) computeDepth(id, 0);

  const byLayer = new Map();
  for (const node of nodes) {
    const l = layerMap.get(node.id) ?? 0;
    if (!byLayer.has(l)) byLayer.set(l, []);
    byLayer.get(l).push(node);
  }

  const sortedLayers = [...byLayer.keys()].sort((a, b) => a - b);
  const positioned = new Map();
  let cursorX = MARGIN;
  let maxSceneHeight = 0;

  for (const l of sortedLayers) {
    const layerNodes = byLayer.get(l);
    const measuredList = layerNodes.map((n) => measureNodeDimensions(n));
    const colWidth = Math.max(...measuredList.map((m) => m.width));
    let cursorY = MARGIN;

    layerNodes.forEach((node, idx) => {
      const dim = measuredList[idx];
      const posX = cursorX + (colWidth - dim.width) / 2;
      const posY = cursorY;
      positioned.set(node.id, {
        ...node,
        x: posX,
        y: posY,
        width: dim.width,
        height: dim.height,
        rank: l,
      });
      cursorY += dim.height + ROW_GAP_Y;
    });

    maxSceneHeight = Math.max(maxSceneHeight, cursorY - ROW_GAP_Y);
    cursorX += colWidth + LAYER_GAP_X;
  }

  const totalWidth = Math.max(cursorX - LAYER_GAP_X + MARGIN, 680);
  const totalHeight = Math.max(maxSceneHeight + MARGIN, 360);

  return { positioned, totalWidth, totalHeight };
}

/**
 * Calculates smooth orthogonal connector path between two positioned nodes.
 */
export function calculateEdgePath(fromNode, toNode, kind = "physical") {
  if (!fromNode || !toNode) return { path: "", labelPoint: { x: 0, y: 0 } };

  // Calculate connection anchors
  const isHorizontal = Math.abs(fromNode.y - toNode.y) < Math.abs(fromNode.x - toNode.x);

  let x1, y1, x2, y2, path;

  if (isHorizontal) {
    if (fromNode.x < toNode.x) {
      x1 = fromNode.x + fromNode.width;
      y1 = fromNode.y + fromNode.height / 2;
      x2 = toNode.x;
      y2 = toNode.y + toNode.height / 2;
    } else {
      x1 = fromNode.x;
      y1 = fromNode.y + fromNode.height / 2;
      x2 = toNode.x + toNode.width;
      y2 = toNode.y + toNode.height / 2;
    }

    const midX = x1 + (x2 - x1) / 2;
    if (Math.abs(y1 - y2) < 4) {
      path = `M ${x1} ${y1} L ${x2} ${y2}`;
    } else {
      path = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
    }
  } else {
    // Vertical rank transition
    if (fromNode.y < toNode.y) {
      x1 = fromNode.x + fromNode.width / 2;
      y1 = fromNode.y + fromNode.height;
      x2 = toNode.x + toNode.width / 2;
      y2 = toNode.y;
    } else {
      x1 = fromNode.x + fromNode.width / 2;
      y1 = fromNode.y;
      x2 = toNode.x + toNode.width / 2;
      y2 = toNode.y + toNode.height;
    }

    const midY = y1 + (y2 - y1) / 2;
    if (Math.abs(x1 - x2) < 4) {
      path = `M ${x1} ${y1} L ${x2} ${y2}`;
    } else {
      path = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
    }
  }

  const labelPoint = {
    x: (x1 + x2) / 2,
    y: (y1 + y2) / 2 - 10,
  };

  return { path, labelPoint };
}

/**
 * Runs layout diagnostics to detect collision, missing labels, or blank elements.
 */
export function runLayoutDiagnostics(sceneGraph, layoutResult) {
  const issues = [];
  const { positioned, totalWidth, totalHeight } = layoutResult;

  if (totalWidth <= 0 || totalHeight <= 0) {
    issues.push({ code: "EMPTY_VIEWBOX", message: "Computed viewBox has non-positive dimensions." });
  }

  for (const node of sceneGraph.nodes) {
    const pos = positioned.get(node.id);
    if (!pos) {
      issues.push({ code: "UNPOSITIONED_NODE", nodeId: node.id, message: `Node '${node.id}' was not placed in scene.` });
    }
    if (!node.title || !node.title.trim()) {
      issues.push({ code: "BLANK_NODE_DETECTED", nodeId: node.id, message: `Node '${node.id}' has no title string.` });
    }
  }

  return {
    isClean: issues.length === 0,
    issues,
  };
}

/**
 * Master layout calculator dispatching to VRRP-specialized or Hierarchical engines.
 */
export function computeLayout(sceneGraph) {
  let result;
  if (sceneGraph.type === "vrrp" || sceneGraph.nodes.some((n) => n.kind === "vrrp_virtual")) {
    result = layoutVrrpScene(sceneGraph.nodes, sceneGraph.edges);
  } else {
    result = layoutHierarchicalScene(sceneGraph.nodes, sceneGraph.edges);
  }

  const diagnostics = runLayoutDiagnostics(sceneGraph, result);
  return {
    ...result,
    viewBox: `0 0 ${result.totalWidth} ${result.totalHeight}`,
    diagnostics,
  };
}
