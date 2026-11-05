// AIRA_ECOSYSTEM/app/frontend/src/benchmark_svg_performance.js
// Phase 4.5 SVG Multi-Layer Performance & Rendering Benchmark Suite

import { performance } from "perf_hooks";
import {
  RELATIONSHIP_CLASSES,
  normalizeEdge,
  computeCurvedEdgePath,
} from "./components/topology/topologyConstants.js";

// Synthetic Graph Generator
function generateSyntheticGraph(nodeCount, edgeCount) {
  const nodes = [];
  for (let i = 0; i < nodeCount; i++) {
    nodes.push({
      id: `node_${i}`,
      name: `Device-${i}`,
      ip: `10.10.${Math.floor(i / 254)}.${(i % 254) + 1}`,
      device_type: i === 0 ? "router" : i < nodeCount * 0.3 ? "switch" : "server",
      pos_x: Math.round(100 + (i % 20) * 120 + Math.random() * 40),
      pos_y: Math.round(100 + Math.floor(i / 20) * 100 + Math.random() * 30),
      oper_status: "up",
    });
  }

  const relationshipClasses = [
    RELATIONSHIP_CLASSES.PHYSICAL,
    RELATIONSHIP_CLASSES.LAYER2,
    RELATIONSHIP_CLASSES.LAYER3,
    RELATIONSHIP_CLASSES.LOGICAL,
  ];

  const edges = [];
  for (let i = 0; i < edgeCount; i++) {
    const srcIdx = Math.floor(Math.random() * nodeCount);
    let dstIdx = Math.floor(Math.random() * nodeCount);
    if (dstIdx === srcIdx) {
      dstIdx = (srcIdx + 1) % nodeCount;
    }
    const relClass = relationshipClasses[i % relationshipClasses.length];
    edges.push({
      id: `edge_${i}`,
      source: `node_${srcIdx}`,
      target: `node_${dstIdx}`,
      source_node_id: `node_${srcIdx}`,
      target_node_id: `node_${dstIdx}`,
      source_port: `ether${(i % 8) + 1}`,
      target_port: `ether${((i + 1) % 8) + 1}`,
      relationship_class: relClass,
      oper_status: i % 25 === 0 ? "down" : "up",
      verification_status: i % 3 === 0 ? "confirmed" : "observed",
      confidence_tier: i % 4 === 0 ? "CONFIRMED" : "HIGH",
      confidence_score: 0.85 + (i % 15) * 0.01,
      confidence_rationale: "Automated synthetic performance benchmark edge",
    });
  }

  return { nodes, edges };
}

// Pipeline execution: Normalization -> Filtering -> Bundling -> Bezier Calculation
function runBenchmarkTier(name, nodeCount, edgeCount) {
  const graph = generateSyntheticGraph(nodeCount, edgeCount);
  const nodesMap = new Map(graph.nodes.map((n) => [n.id, n]));

  const t0 = performance.now();

  // 1. Edge normalization
  const normalizedEdges = graph.edges.map((e) => normalizeEdge(e));
  const tNorm = performance.now();

  // 2. Multi-layer filtering (simulate all layers active)
  const activeLayers = {
    [RELATIONSHIP_CLASSES.PHYSICAL]: true,
    [RELATIONSHIP_CLASSES.LAYER2]: true,
    [RELATIONSHIP_CLASSES.LAYER3]: true,
    [RELATIONSHIP_CLASSES.LOGICAL]: true,
  };
  const visibleEdges = normalizedEdges.filter((e) => {
    if (!activeLayers[e.relationship_class]) return false;
    return nodesMap.has(e.source) && nodesMap.has(e.target);
  });
  const tFilter = performance.now();

  // 3. Parallel Edge Bundling
  const groups = new Map();
  for (const edge of visibleEdges) {
    const srcId = edge.source_node_id || edge.source;
    const dstId = edge.target_node_id || edge.target;
    const pairKey = [srcId, dstId].sort().join("---");
    if (!groups.has(pairKey)) {
      groups.set(pairKey, []);
    }
    groups.get(pairKey).push(edge);
  }

  const bundled = [];
  for (const [, edges] of groups.entries()) {
    const bundleSize = edges.length;
    edges.forEach((edge, bundleIndex) => {
      bundled.push({ edge, bundleIndex, bundleSize });
    });
  }
  const tBundle = performance.now();

  // 4. Bezier SVG Path & Label Coordinate Computation
  let pathCount = 0;
  for (const item of bundled) {
    const src = nodesMap.get(item.edge.source);
    const dst = nodesMap.get(item.edge.target);
    const curved = computeCurvedEdgePath(
      src.pos_x,
      src.pos_y,
      dst.pos_x,
      dst.pos_y,
      item.bundleIndex,
      item.bundleSize
    );
    if (curved.pathD) pathCount++;
  }
  const tBezier = performance.now();

  // 5. Layer Toggle Simulation (toggle off Layer 3)
  const toggle0 = performance.now();
  const toggledVisible = normalizedEdges.filter((e) => {
    if (e.relationship_class === RELATIONSHIP_CLASSES.LAYER3) return false;
    return nodesMap.has(e.source) && nodesMap.has(e.target);
  });
  const toggleGroups = new Map();
  for (const edge of toggledVisible) {
    const pairKey = [edge.source, edge.target].sort().join("---");
    if (!toggleGroups.has(pairKey)) toggleGroups.set(pairKey, []);
    toggleGroups.get(pairKey).push(edge);
  }
  const toggleBundled = [];
  for (const [, edges] of toggleGroups.entries()) {
    edges.forEach((edge, bundleIndex) => {
      toggleBundled.push({ edge, bundleIndex, bundleSize: edges.length });
    });
  }
  for (const item of toggleBundled) {
    const src = nodesMap.get(item.edge.source);
    const dst = nodesMap.get(item.edge.target);
    computeCurvedEdgePath(src.pos_x, src.pos_y, dst.pos_x, dst.pos_y, item.bundleIndex, item.bundleSize);
  }
  const toggleTimeMs = performance.now() - toggle0;

  // 6. Selection Simulation (lookup edge & related nodes)
  const select0 = performance.now();
  const selectedEdge = normalizedEdges[Math.floor(normalizedEdges.length / 2)];
  const relatedSource = nodesMap.get(selectedEdge.source);
  const relatedTarget = nodesMap.get(selectedEdge.target);
  const selectionTimeMs = performance.now() - select0;

  const totalFullPipelineMs = tBezier - t0;
  const throughputEdgesPerSec = Math.round((edgeCount / (totalFullPipelineMs / 1000)));

  return {
    tier: name,
    nodes: nodeCount,
    edges: edgeCount,
    normalizationMs: +(tNorm - t0).toFixed(3),
    filteringMs: +(tFilter - tNorm).toFixed(3),
    bundlingMs: +(tBundle - tFilter).toFixed(3),
    bezierMs: +(tBezier - tBundle).toFixed(3),
    totalPipelineMs: +totalFullPipelineMs.toFixed(3),
    layerToggleTimeMs: +toggleTimeMs.toFixed(3),
    edgeSelectionTimeMs: +selectionTimeMs.toFixed(3),
    throughputEdgesPerSec,
  };
}

console.log("================================================================================");
console.log("AIRA OS Phase 4.5 — Multi-Layer SVG Topology Canvas Performance Benchmark");
console.log("================================================================================\n");

const tiers = [
  { name: "Tier A (Typical Branch)", nodes: 50, edges: 100 },
  { name: "Tier B (Campus / Mid-Core)", nodes: 100, edges: 300 },
  { name: "Tier C (Large Enterprise)", nodes: 250, edges: 750 },
  { name: "Tier D (Data Center Fabric)", nodes: 500, edges: 1500 },
];

const results = [];
for (const t of tiers) {
  // Warm-up run
  runBenchmarkTier("Warm-up", 20, 40);

  // 5 benchmark iterations for statistical stability
  let totalPipe = 0;
  let totalToggle = 0;
  let totalSelect = 0;
  let rLast = null;

  for (let iter = 0; iter < 5; iter++) {
    const r = runBenchmarkTier(t.name, t.nodes, t.edges);
    totalPipe += r.totalPipelineMs;
    totalToggle += r.layerToggleTimeMs;
    totalSelect += r.edgeSelectionTimeMs;
    rLast = r;
  }

  rLast.totalPipelineMs = +(totalPipe / 5).toFixed(3);
  rLast.layerToggleTimeMs = +(totalToggle / 5).toFixed(3);
  rLast.edgeSelectionTimeMs = +(totalSelect / 5).toFixed(3);
  rLast.throughputEdgesPerSec = Math.round((t.edges / (rLast.totalPipelineMs / 1000)));
  results.push(rLast);
}

console.table(results);

console.log("\n--- BENCHMARK VERDICT & THRESHOLDS ---");
for (const res of results) {
  const acceptable = res.totalPipelineMs < 50 && res.layerToggleTimeMs < 50;
  console.log(
    `[${acceptable ? "PASS" : "WARN"}] ${res.tier}: Total Pipeline ${res.totalPipelineMs} ms | Layer Toggle ${res.layerToggleTimeMs} ms | Selection ${res.edgeSelectionTimeMs} ms`
  );
}
console.log("\nBenchmark complete.");
