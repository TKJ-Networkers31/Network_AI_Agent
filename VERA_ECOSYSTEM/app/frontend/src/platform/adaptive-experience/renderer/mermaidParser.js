/**
 * src/platform/adaptive-experience/renderer/mermaidParser.js
 *
 * Lightweight Mermaid Flowchart / Graph parser and SVG generator.
 * Produces deterministic, secure SVG representations for common Mermaid graphs
 * without any heavy external libraries.
 */

/**
 * Parses Mermaid code into nodes, edges, and graph metadata.
 *
 * @param {string} code - Raw Mermaid graph/flowchart code
 * @returns {{ direction: string, nodes: Map<string, { id: string, label: string, shape: string }>, edges: Array<{ from: string, to: string, label?: string, style: string }> }}
 */
export function parseMermaidCode(code) {
  if (!code || typeof code !== "string") {
    return { direction: "TD", nodes: new Map(), edges: [] };
  }

  const lines = code
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("%%"));

  let direction = "TD";
  const nodes = new Map();
  const edges = [];

  // 1. Detect header direction
  const firstLine = lines[0] || "";
  const headerMatch = /^(?:graph|flowchart)\s+(TD|TB|LR|BT|RL)/i.exec(firstLine);
  if (headerMatch) {
    direction = headerMatch[1].toUpperCase();
    if (direction === "TB") direction = "TD";
    lines.shift(); // remove header line
  } else if (/^(?:graph|flowchart)/i.test(firstLine)) {
    lines.shift();
  }

  // Helper to extract or register node
  function registerNode(rawToken) {
    if (!rawToken) return null;
    const token = rawToken.trim();
    if (!token) return null;

    // Matches: ID[Label], ID(Label), ID{Label}, ID([Label]), or plain ID
    const shapeMatch = /^([a-zA-Z0-9_\u00C0-\u00FF-]+)(?:(\[\(|\[|\(|\{)(.*?)(?:\)\]|\]|\)|\}))?$/.exec(
      token
    );

    if (shapeMatch) {
      const id = shapeMatch[1];
      let label = shapeMatch[3] !== undefined ? shapeMatch[3].trim() : id;
      // Strip surrounding quotes if present
      if (
        (label.startsWith('"') && label.endsWith('"')) ||
        (label.startsWith("'") && label.endsWith("'"))
      ) {
        label = label.slice(1, -1);
      }

      const shapeType = shapeMatch[2] || "rect";
      if (!nodes.has(id)) {
        nodes.set(id, { id, label: label || id, shape: shapeType });
      } else if (shapeMatch[3] !== undefined) {
        // Update label if previously only registered as bare id
        const existing = nodes.get(id);
        existing.label = label || id;
        existing.shape = shapeType;
      }
      return id;
    }

    const cleanId = token.replace(/[^a-zA-Z0-9_-]/g, "");
    if (cleanId) {
      if (!nodes.has(cleanId)) {
        nodes.set(cleanId, { id: cleanId, label: cleanId, shape: "rect" });
      }
      return cleanId;
    }
    return null;
  }

  // Regex to split connections
  // Supported: -->|label|, -.->|label|, ==>|label|, ---|label|, -- label -->, -->, -.->, ==>, ---
  const edgeRegex =
    /\s*(-->\|[^|]+\||-\.->\|[^|]+\||==>\|[^|]+\||---\|[^|]+\||--\s+[^->]+?\s+-->|-->|-\.->|==>|---)\s*/g;

  for (const line of lines) {
    if (/^(subgraph|end|classDef|class|style|click)\b/i.test(line)) {
      continue; // Skip styling / subgraph directives for simplicity
    }

    const segments = [];
    const connectors = [];
    let lastIndex = 0;
    let match;

    while ((match = edgeRegex.exec(line)) !== null) {
      segments.push(line.slice(lastIndex, match.index).trim());
      connectors.push(match[1]);
      lastIndex = edgeRegex.lastIndex;
    }
    segments.push(line.slice(lastIndex).trim());

    if (connectors.length > 0 && segments.length >= 2) {
      for (let i = 0; i < connectors.length; i++) {
        const fromToken = segments[i];
        const toToken = segments[i + 1];
        const conn = connectors[i];

        const fromId = registerNode(fromToken);
        const toId = registerNode(toToken);

        if (fromId && toId) {
          let style = "solid";
          let label = "";

          if (conn.includes("-.-")) style = "dashed";
          else if (conn.includes("==")) style = "thick";

          // Extract label from |label| or -- label -->
          const pipeLabel = /\|([^|]+)\|/.exec(conn);
          const arrowLabel = /--\s+([^->]+?)\s+-->/.exec(conn);
          if (pipeLabel) {
            label = pipeLabel[1].trim();
          } else if (arrowLabel) {
            label = arrowLabel[1].trim();
          }

          edges.push({ from: fromId, to: toId, label, style });
        }
      }
    } else {
      // Standalone node declaration (e.g. A[Label])
      registerNode(line);
    }
  }

  return { direction, nodes, edges };
}

/**
 * Computes simple rank-based layout positions for nodes.
 */
function layoutGraph(direction, nodesMap, edges) {
  const nodeIds = Array.from(nodesMap.keys());
  if (nodeIds.length === 0) {
    return { positions: new Map(), width: 400, height: 200 };
  }

  const inDegree = new Map(nodeIds.map((id) => [id, 0]));
  const adj = new Map(nodeIds.map((id) => [id, []]));

  for (const edge of edges) {
    if (adj.has(edge.from) && inDegree.has(edge.to)) {
      adj.get(edge.from).push(edge.to);
      inDegree.set(edge.to, (inDegree.get(edge.to) || 0) + 1);
    }
  }

  // BFS / topological levels
  const levels = new Map();
  const queue = [];

  for (const [id, deg] of inDegree.entries()) {
    if (deg === 0) {
      queue.push({ id, level: 0 });
      levels.set(id, 0);
    }
  }

  // If cyclic or no roots, seed all unvisited nodes
  if (queue.length === 0) {
    for (const id of nodeIds) {
      queue.push({ id, level: 0 });
      levels.set(id, 0);
      break;
    }
  }

  while (queue.length > 0) {
    const { id, level } = queue.shift();
    const neighbors = adj.get(id) || [];
    for (const n of neighbors) {
      const curLvl = levels.get(n);
      if (curLvl === undefined || level + 1 > curLvl) {
        levels.set(n, level + 1);
        queue.push({ id: n, level: level + 1 });
      }
    }
  }

  // Ensure all nodes have a level
  for (const id of nodeIds) {
    if (!levels.has(id)) levels.set(id, 0);
  }

  // Group nodes by level
  const byLevel = new Map();
  let maxLevel = 0;
  for (const [id, lvl] of levels.entries()) {
    if (!byLevel.has(lvl)) byLevel.set(lvl, []);
    byLevel.get(lvl).push(id);
    if (lvl > maxLevel) maxLevel = lvl;
  }

  const isTD = direction === "TD" || direction === "BT";
  const nodeW = 140;
  const nodeH = 46;
  const gapX = isTD ? 32 : 70;
  const gapY = isTD ? 64 : 28;
  const pad = 36;

  const positions = new Map();
  let maxCross = 0;

  for (let l = 0; l <= maxLevel; l++) {
    const row = byLevel.get(l) || [];
    if (row.length > maxCross) maxCross = row.length;
  }

  const totalPrimary = (maxLevel + 1) * (isTD ? nodeH : nodeW) + maxLevel * (isTD ? gapY : gapX);
  const totalCross = maxCross * (isTD ? nodeW : nodeH) + (maxCross - 1) * (isTD ? gapX : gapY);

  const totalWidth = (isTD ? totalCross : totalPrimary) + pad * 2;
  const totalHeight = (isTD ? totalPrimary : totalCross) + pad * 2;

  for (let l = 0; l <= maxLevel; l++) {
    const row = byLevel.get(l) || [];
    const count = row.length;
    const rowSpan = count * (isTD ? nodeW : nodeH) + (count - 1) * (isTD ? gapX : gapY);
    const startCross = (isTD ? totalWidth : totalHeight) / 2 - rowSpan / 2;

    for (let i = 0; i < count; i++) {
      const id = row[i];
      let x, y;
      const crossPos = startCross + i * ((isTD ? nodeW : nodeH) + (isTD ? gapX : gapY));
      const primaryPos = pad + l * ((isTD ? nodeH : nodeW) + (isTD ? gapY : gapX));

      if (isTD) {
        x = crossPos;
        y = primaryPos;
      } else {
        x = primaryPos;
        y = crossPos;
      }

      positions.set(id, {
        x,
        y,
        w: nodeW,
        h: nodeH,
        cx: x + nodeW / 2,
        cy: y + nodeH / 2,
      });
    }
  }

  return { positions, width: Math.max(totalWidth, 360), height: Math.max(totalHeight, 180) };
}

/**
 * Generates an SVG string representation of a parsed Mermaid diagram.
 *
 * @param {string} code - Raw Mermaid graph code
 * @returns {{ svg: string, nodeCount: number, edgeCount: number, success: boolean }}
 */
export function generateMermaidSvg(code) {
  const { direction, nodes, edges } = parseMermaidCode(code);

  if (nodes.size === 0) {
    return { svg: "", nodeCount: 0, edgeCount: 0, success: false };
  }

  const { positions, width, height } = layoutGraph(direction, nodes, edges);
  const isTD = direction === "TD" || direction === "BT";

  // Build SVG elements
  const edgeSvg = edges
    .map((e, idx) => {
      const p1 = positions.get(e.from);
      const p2 = positions.get(e.to);
      if (!p1 || !p2) return "";

      let startX, startY, endX, endY;
      if (isTD) {
        startX = p1.cx;
        startY = p1.y + p1.h;
        endX = p2.cx;
        endY = p2.y;
      } else {
        startX = p1.x + p1.w;
        startY = p1.cy;
        endX = p2.x;
        endY = p2.cy;
      }

      const dashAttr = e.style === "dashed" ? 'stroke-dasharray="4,4"' : "";
      const strokeW = e.style === "thick" ? "2.5" : "1.75";

      // Control points for smooth bezier curve
      let pathD;
      if (isTD) {
        const midY = (startY + endY) / 2;
        pathD = `M ${startX} ${startY} C ${startX} ${midY}, ${endX} ${midY}, ${endX} ${endY - 6}`;
      } else {
        const midX = (startX + endX) / 2;
        pathD = `M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${endX - 6} ${endY}`;
      }

      const labelSvg = e.label
        ? `<rect x="${(startX + endX) / 2 - 28}" y="${(startY + endY) / 2 - 9}" width="56" height="18" rx="4" fill="#0a0f1d" stroke="#38BDF8" stroke-width="0.75" />
           <text x="${(startX + endX) / 2}" y="${(startY + endY) / 2 + 3}" text-anchor="middle" font-size="10" fill="#38BDF8" font-family="system-ui, sans-serif">${escapeXml(e.label)}</text>`
        : "";

      return `
        <g class="vae-mermaid-edge">
          <path d="${pathD}" fill="none" stroke="#38BDF8" stroke-width="${strokeW}" ${dashAttr} marker-end="url(#vae-arrow)" opacity="0.85" />
          ${labelSvg}
        </g>
      `;
    })
    .join("\n");

  const nodeSvg = Array.from(nodes.values())
    .map((node) => {
      const pos = positions.get(node.id);
      if (!pos) return "";

      const rx = node.shape === "{" ? "0" : node.shape === "(" || node.shape === "([" ? "20" : "8";

      return `
        <g class="vae-mermaid-node" transform="translate(${pos.x}, ${pos.y})">
          <rect width="${pos.w}" height="${pos.h}" rx="${rx}" fill="#04060c" stroke="#38BDF8" stroke-width="1.5" filter="url(#vae-glow)" />
          <text x="${pos.w / 2}" y="${pos.h / 2 + 4}" text-anchor="middle" fill="#F8FAFC" font-size="12" font-weight="500" font-family="Inter, system-ui, sans-serif">
            ${escapeXml(node.label)}
          </text>
        </g>
      `;
    })
    .join("\n");

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="100%" height="auto" style="max-width: ${width}px; background-color: #000000; border-radius: 12px; display: block; margin: 0 auto;">
  <defs>
    <marker id="vae-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#38BDF8" />
    </marker>
    <filter id="vae-glow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#38BDF8" flood-opacity="0.25" />
    </filter>
  </defs>
  ${edgeSvg}
  ${nodeSvg}
</svg>`;

  return {
    svg,
    nodeCount: nodes.size,
    edgeCount: edges.length,
    success: true,
  };
}

function escapeXml(unsafe) {
  if (!unsafe) return "";
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
