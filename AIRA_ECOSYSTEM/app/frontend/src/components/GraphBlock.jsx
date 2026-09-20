import { useMemo, useState } from "react";
import CopyButton from "./CopyButton.jsx";

const NODE_HEIGHT = 44;
const NODE_MIN_WIDTH = 90;
const NODE_MAX_WIDTH = 220;
const CHAR_WIDTH = 7.2;
const NODE_PAD_X = 16;
const LAYER_GAP_X = 90;
const ROW_GAP_Y = 24;
const MARGIN = 24;

function estimateNodeWidth(label) {
  const raw = Math.ceil((label || "").length * CHAR_WIDTH) + NODE_PAD_X * 2;
  return Math.min(Math.max(raw, NODE_MIN_WIDTH), NODE_MAX_WIDTH);
}

function wrapLabel(label, width) {
  const maxChars = Math.max(4, Math.floor((width - NODE_PAD_X * 2) / CHAR_WIDTH));
  const text = String(label || "");
  if (text.length <= maxChars) return [text];

  const words = text.split(" ");
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
    if (lines.length === 1) break;
  }
  if (current) lines.push(current);

  if (lines.length > 2) {
    lines.length = 2;
    lines[1] = lines[1].slice(0, maxChars - 1) + "…";
  } else if (lines.length === 2 && lines[1].length > maxChars) {
    lines[1] = lines[1].slice(0, maxChars - 1) + "…";
  }
  return lines;
}

/** Longest-path layering dari root. Node yang terlibat siklus dipin ke layer 0
 *  (fallback aman) alih-alih membuat algoritma hang. */
function assignLayers(nodes, edges) {
  const ids = nodes.map((n) => n.id);
  const incoming = new Map(ids.map((id) => [id, []]));
  for (const e of edges) {
    if (incoming.has(e.to)) incoming.get(e.to).push(e.from);
  }

  const layer = new Map();
  const visiting = new Set();

  function resolve(id, depth) {
    if (depth > ids.length + 1) return 0;
    if (layer.has(id)) return layer.get(id);
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const preds = incoming.get(id) || [];
    const l = preds.length === 0 ? 0 : Math.max(...preds.map((p) => resolve(p, depth + 1))) + 1;
    visiting.delete(id);
    layer.set(id, l);
    return l;
  }

  for (const id of ids) resolve(id, 0);
  return layer;
}

function layoutGraph(nodes, edges) {
  const layerOf = assignLayers(nodes, edges);
  const byLayer = new Map();
  for (const node of nodes) {
    const l = layerOf.get(node.id) ?? 0;
    if (!byLayer.has(l)) byLayer.set(l, []);
    byLayer.get(l).push(node);
  }

  const layers = [...byLayer.keys()].sort((a, b) => a - b);
  const positioned = new Map();
  let cursorX = MARGIN;
  let maxHeight = 0;

  for (const l of layers) {
    const layerNodes = byLayer.get(l);
    const widths = layerNodes.map((n) => estimateNodeWidth(n.label));
    const colWidth = Math.max(...widths);
    let cursorY = MARGIN;

    layerNodes.forEach((n, i) => {
      const w = widths[i];
      positioned.set(n.id, { ...n, x: cursorX + (colWidth - w) / 2, y: cursorY, width: w, height: NODE_HEIGHT });
      cursorY += NODE_HEIGHT + ROW_GAP_Y;
    });

    maxHeight = Math.max(maxHeight, cursorY - ROW_GAP_Y);
    cursorX += colWidth + LAYER_GAP_X;
  }

  return { positioned, totalWidth: cursorX - LAYER_GAP_X + MARGIN, totalHeight: maxHeight + MARGIN };
}

function edgePath(from, to) {
  const x1 = from.x + from.width, y1 = from.y + from.height / 2;
  const x2 = to.x, y2 = to.y + to.height / 2;
  if (Math.abs(y1 - y2) < 1) return `M ${x1} ${y1} L ${x2} ${y2}`;
  const midX = x1 + (x2 - x1) / 2;
  return `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`;
}

function hashString(str) {
  let h = 0;
  for (let i = 0; i < str.length; i += 1) h = (h * 31 + str.charCodeAt(i)) | 0;
  return h;
}
const GROUP_COLORS = [
  { fill: "#EEF2FF", stroke: "#6366F1" }, { fill: "#ECFDF5", stroke: "#10B981" },
  { fill: "#FFF7ED", stroke: "#F59E0B" }, { fill: "#FDF2F8", stroke: "#EC4899" },
  { fill: "#F0F9FF", stroke: "#0EA5E9" },
];
function colorForGroup(group, index) {
  if (group == null) return GROUP_COLORS[0];
  const key = typeof group === "number" ? group : Math.abs(hashString(String(group)));
  return GROUP_COLORS[key % GROUP_COLORS.length];
}

function parseGraph(raw) {
  let data;
  try { data = JSON.parse(raw); } catch { return null; }
  if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges) || data.nodes.length === 0) return null;

  const nodes = data.nodes
    .filter((n) => n && n.id != null)
    .map((n) => ({ id: String(n.id), label: String(n.label ?? n.id), group: n.group }));

  const validIds = new Set(nodes.map((n) => n.id));
  const edges = data.edges
    .filter((e) => e && validIds.has(String(e.from)) && validIds.has(String(e.to)))
    .map((e) => ({ from: String(e.from), to: String(e.to), label: e.label ? String(e.label) : "" }));

  return { nodes, edges };
}

export default function GraphBlock({ code }) {
  const [showCode, setShowCode] = useState(false);
  const parsed = useMemo(() => parseGraph(code), [code]);
  const layout = useMemo(() => (parsed ? layoutGraph(parsed.nodes, parsed.edges) : null), [parsed]);

  if (!parsed || !layout) {
    return (
      <div className="my-3 rounded-xl2 border border-border overflow-hidden">
        <div className="flex items-center justify-between pl-3 pr-1.5 py-1 bg-white/5 border-b border-border">
          <span className="text-[10px] uppercase tracking-wide text-amber-300/80">
            graph tidak valid - ditampilkan sebagai kode
          </span>
          <CopyButton text={code} label="Salin" title="Salin kode graph" />
        </div>
        <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed bg-black/30">
          <code className="font-mono text-white/85">{code}</code>
        </pre>
      </div>
    );
  }

  const { positioned, totalWidth, totalHeight } = layout;
  const nodesArr = [...positioned.values()];

  return (
    <div className="my-3 rounded-xl2 border border-border overflow-hidden">
      <div className="flex items-center justify-between pl-3 pr-1.5 py-1 bg-white/5 border-b border-border">
        <span className="text-[10px] uppercase tracking-wide text-white/40">diagram (auto-layout)</span>
        <div className="flex items-center gap-0.5">
          <button type="button" onClick={() => setShowCode((v) => !v)}
            className="inline-flex items-center rounded-pill px-2 py-1 text-[11px] text-white/40 hover:text-white hover:bg-white/10 transition">
            {showCode ? "Sembunyikan data" : "Data"}
          </button>
          <CopyButton text={code} label="Salin" title="Salin data graph" />
        </div>
      </div>

      <div className="bg-[#F8FAFC] p-3 overflow-x-auto">
        <svg viewBox={`0 0 ${totalWidth} ${totalHeight}`} width="100%"
          style={{ minWidth: Math.min(totalWidth, 320), maxWidth: "100%", height: "auto" }}
          xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#64748B" />
            </marker>
          </defs>

          {parsed.edges.map((e, i) => {
            const from = positioned.get(e.from), to = positioned.get(e.to);
            if (!from || !to) return null;
            const midX = (from.x + from.width + to.x) / 2;
            const midY = (from.y + from.height / 2 + to.y + to.height / 2) / 2;
            return (
              <g key={`edge-${i}`}>
                <path d={edgePath(from, to)} fill="none" stroke="#64748B" strokeWidth="1.6" markerEnd="url(#arrow)" />
                {e.label && (
                  <text x={midX} y={midY - 6} textAnchor="middle" fontSize="11" fill="#475569" fontFamily="sans-serif">
                    {e.label}
                  </text>
                )}
              </g>
            );
          })}

          {nodesArr.map((n, i) => {
            const color = colorForGroup(n.group, i);
            const lines = wrapLabel(n.label, n.width);
            const lineHeight = 14;
            const startY = n.y + n.height / 2 - ((lines.length - 1) * lineHeight) / 2 + 4;
            return (
              <g key={n.id}>
                <rect x={n.x} y={n.y} width={n.width} height={n.height} rx="10"
                  fill={color.fill} stroke={color.stroke} strokeWidth="1.4" />
                {lines.map((line, li) => (
                  <text key={li} x={n.x + n.width / 2} y={startY + li * lineHeight}
                    textAnchor="middle" fontSize="12.5" fontFamily="sans-serif" fill="#1E293B">
                    {line}
                  </text>
                ))}
              </g>
            );
          })}
        </svg>
      </div>

      {showCode && (
        <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed bg-black/30 border-t border-border">
          <code className="font-mono text-white/85">{code}</code>
        </pre>
      )}
    </div>
  );
}