import { resolveDeviceAssetKey, getDeviceAsset } from "./deviceAssetRegistry.js";
import { normalizeDeviceStatus, getDeviceStatusStyle } from "./deviceStatusCore.js";

/**
 * VERA Static SVG Topology Exporter
 * Generates production-ready standalone SVG XML diagrams reusing the exact same
 * vector asset definitions, layer color codes, and status taxonomy as the interactive canvas.
 */

// Edge layer colors and dash styles
const LAYER_STYLES = {
  physical: { color: "#38bdf8", strokeWidth: 2, dashArray: "" },
  layer2: { color: "#10b981", strokeWidth: 1.8, dashArray: "" },
  layer3: { color: "#a855f7", strokeWidth: 1.8, dashArray: "5 3" },
  logical: { color: "#f59e0b", strokeWidth: 1.5, dashArray: "3 3" },
  default: { color: "#64748b", strokeWidth: 1.5, dashArray: "" },
};

/**
 * Escapes XML strings for safe SVG attribute embedding
 */
function escapeXml(unsafe = "") {
  return String(unsafe)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

/**
 * Extracts inner XML elements from full SVG string
 */
function extractSvgInner(svgString = "") {
  if (!svgString) return "";
  const match = svgString.match(/<svg[^>]*>([\s\S]*?)<\/svg>/i);
  return match ? match[1].trim() : svgString;
}

/**
 * Generates an SVG string from nodes and links
 */
export function generateTopologySvg(nodes = [], links = [], options = {}) {
  const {
    title = "VERA Enterprise Network Topology",
    timestamp = new Date().toISOString(),
    cardWidth = 220,
    cardHeight = 84,
    padding = 80,
  } = options;

  if (!nodes || nodes.length === 0) {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" width="600" height="400">
      <rect width="100%" height="100%" fill="#030712"/>
      <text x="300" y="200" fill="#64748b" font-family="sans-serif" font-size="16" text-anchor="middle">No Topology Data Available</text>
    </svg>`;
  }

  // Build node lookup map and compute bounding box
  const nodeMap = new Map();
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  nodes.forEach((n, idx) => {
    const rawX = n.position?.x ?? n.pos_x ?? (100 + (idx % 4) * 260);
    const rawY = n.position?.y ?? n.pos_y ?? (80 + Math.floor(idx / 4) * 180);

    const x = Math.round(rawX);
    const y = Math.round(rawY);

    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + cardWidth);
    maxY = Math.max(maxY, y + cardHeight);

    nodeMap.set(n.id, {
      ...n,
      computedX: x,
      computedY: y,
      centerX: x + cardWidth / 2,
      centerY: y + cardHeight / 2,
    });
  });

  const viewBoxX = minX - padding;
  const viewBoxY = minY - padding - 40; // extra space for header
  const viewBoxWidth = Math.max(600, maxX - minX + padding * 2);
  const viewBoxHeight = Math.max(400, maxY - minY + padding * 2 + 50);

  // Render Edges
  const edgesSvg = links
    .map((link) => {
      const sourceId = link.source_node_id || link.source;
      const targetId = link.target_node_id || link.target;
      const srcNode = nodeMap.get(sourceId);
      const tgtNode = nodeMap.get(targetId);

      if (!srcNode || !tgtNode) return "";

      const layer = link.relationship_class || link.layer || "physical";
      const style = LAYER_STYLES[layer] || LAYER_STYLES.default;
      const operStatus = (link.oper_status || link.status || "up").toLowerCase();

      let strokeColor = style.color;
      if (operStatus === "down" || operStatus === "error") strokeColor = "#f43f5e";
      else if (operStatus === "degraded" || operStatus === "warning") strokeColor = "#f59e0b";

      const x1 = srcNode.centerX;
      const y1 = srcNode.centerY;
      const x2 = tgtNode.centerX;
      const y2 = tgtNode.centerY;

      // Gentle Bezier curve control points
      const dx = (x2 - x1) * 0.25;
      const dy = (y2 - y1) * 0.25;
      const cx1 = x1 + dx;
      const cy1 = y1 + dy;
      const cx2 = x2 - dx;
      const cy2 = y2 - dy;

      const pathData = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;

      return `
        <g class="topology-edge" data-edge-id="${escapeXml(link.id || "")}">
          <path d="${pathData}" stroke="${strokeColor}" stroke-width="${style.strokeWidth}" fill="none" ${
        style.dashArray ? `stroke-dasharray="${style.dashArray}"` : ""
      } opacity="0.85" />
        </g>`;
    })
    .join("\n");

  // Render Nodes
  const nodesSvg = nodes
    .map((n) => {
      const nodeData = nodeMap.get(n.id);
      if (!nodeData) return "";

      const { computedX: x, computedY: y } = nodeData;
      const assetKey = resolveDeviceAssetKey(n);
      const asset = getDeviceAsset(assetKey);
      const statusStyle = getDeviceStatusStyle(n.status || n.oper_status);

      const name = escapeXml(n.label || n.name || n.id);
      const ip = escapeXml(n.ip || n.management_ip || n.host || "-");
      const model = escapeXml(n.model || asset.label);
      const assetInnerXml = extractSvgInner(asset.svgRaw);

      return `
        <g class="topology-node" transform="translate(${x}, ${y})" data-node-id="${escapeXml(n.id)}">
          <!-- Card Background & Glow -->
          <rect width="${cardWidth}" height="${cardHeight}" rx="14" fill="#090d16" stroke="${statusStyle.hexColor}" stroke-width="1.2" opacity="0.95"/>
          <rect width="${cardWidth}" height="${cardHeight}" rx="14" fill="none" stroke="#1e293b" stroke-width="1"/>

          <!-- Embedded Device Vector Asset (40x40 at x=10, y=10) -->
          <g transform="translate(10, 10)">
            <rect width="40" height="40" rx="8" fill="#0f172a" stroke="#1e293b" stroke-width="1"/>
            <svg x="2" y="2" width="36" height="36" viewBox="0 0 64 64">
              ${assetInnerXml}
            </svg>
          </g>

          <!-- Status Indicator Pill Top Right -->
          <g transform="translate(${cardWidth - 65}, 12)">
            <rect width="53" height="16" rx="8" fill="${statusStyle.hexColor}" fill-opacity="0.15" stroke="${statusStyle.hexColor}" stroke-width="0.8"/>
            <circle cx="9" cy="8" r="3" fill="${statusStyle.hexColor}"/>
            <text x="18" y="11.5" fill="${statusStyle.hexColor}" font-family="monospace, sans-serif" font-size="8" font-weight="bold">${statusStyle.label}</text>
          </g>

          <!-- Device Model / Category Label -->
          <text x="58" y="22" fill="#38bdf8" font-family="monospace, sans-serif" font-size="8.5" font-weight="600" letter-spacing="0.5">${escapeXml(asset.category.toUpperCase())}</text>

          <!-- Device Display Name -->
          <text x="58" y="38" fill="#f8fafc" font-family="sans-serif" font-size="11" font-weight="600">${name}</text>

          <!-- Divider -->
          <line x1="10" y1="56" x2="${cardWidth - 10}" y2="56" stroke="#1e293b" stroke-width="1"/>

          <!-- IP Address & Model Footnote -->
          <text x="12" y="71" fill="#94a3b8" font-family="monospace, sans-serif" font-size="9">${ip}</text>
          <text x="${cardWidth - 12}" y="71" fill="#64748b" font-family="sans-serif" font-size="8" text-anchor="end">${model}</text>
        </g>`;
    })
    .join("\n");

  // Complete SVG Assembly with dark technical backdrop, grid pattern, and header
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBoxX} ${viewBoxY} ${viewBoxWidth} ${viewBoxHeight}" width="${viewBoxWidth}" height="${viewBoxHeight}">
  <defs>
    <!-- Background Grid Pattern -->
    <pattern id="vera-grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <circle cx="1" cy="1" r="1" fill="#1e293b" fill-opacity="0.5"/>
    </pattern>
    <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Deep Dark Slate Background -->
  <rect x="${viewBoxX}" y="${viewBoxY}" width="${viewBoxWidth}" height="${viewBoxHeight}" fill="#030712"/>
  <rect x="${viewBoxX}" y="${viewBoxY}" width="${viewBoxWidth}" height="${viewBoxHeight}" fill="url(#vera-grid)"/>

  <!-- Diagram Title Header -->
  <g transform="translate(${viewBoxX + 24}, ${viewBoxY + 30})">
    <text x="0" y="0" fill="#38bdf8" font-family="sans-serif" font-size="14" font-weight="700" letter-spacing="1">${escapeXml(title)}</text>
    <text x="0" y="16" fill="#64748b" font-family="monospace, sans-serif" font-size="9">Exported: ${escapeXml(timestamp)} | Nodes: ${nodes.length} | Links: ${links.length}</text>
  </g>

  <!-- Layer: Edges / Links -->
  <g id="topology-edges">
    ${edgesSvg}
  </g>

  <!-- Layer: Nodes -->
  <g id="topology-nodes">
    ${nodesSvg}
  </g>
</svg>`;
}

/**
 * Triggers client-side download of generated topology SVG
 */
export function downloadSvgTopology(nodes = [], links = [], filename = "network-topology.svg", options = {}) {
  const svgContent = generateTopologySvg(nodes, links, options);
  const blob = new Blob([svgContent], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
