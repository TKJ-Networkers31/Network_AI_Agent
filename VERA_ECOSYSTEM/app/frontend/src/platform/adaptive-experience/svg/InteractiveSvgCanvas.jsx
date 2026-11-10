/**
 * src/platform/adaptive-experience/svg/InteractiveSvgCanvas.jsx
 *
 * Interactive SVG Engine with React-managed SVG DOM, Pan/Zoom controls,
 * animated traffic flows with user pause control, keyboard accessibility,
 * cluster visualization, and node detail drawer integration.
 */

import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Play,
  Pause,
  Maximize2,
  Minimize2,
  Router,
  Server,
  Shield,
  Layers,
  Activity,
  AlertTriangle,
  Info,
} from "lucide-react";

import { computeLayout, calculateEdgePath } from "./layoutEngine.js";
import { buildSceneGraph, NODE_KINDS } from "./sceneGraph.js";
import DeviceDetailDrawer from "./DeviceDetailDrawer.jsx";

export default function InteractiveSvgCanvas({ graph, onAction }) {
  const sceneGraph = useMemo(() => {
    return graph?.nodes ? buildSceneGraph(graph) : buildSceneGraph({ nodes: [], edges: [] });
  }, [graph]);

  const layout = useMemo(() => computeLayout(sceneGraph), [sceneGraph]);
  const { positioned, totalWidth, totalHeight, viewBox } = layout;

  // Viewport transform state
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const startPanRef = useRef({ x: 0, y: 0 });
  const containerRef = useRef(null);

  // Selected entities
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // Motion controls (Respects prefers-reduced-motion)
  const [isMotionPaused, setIsMotionPaused] = useState(false);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia) {
      const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
      if (mediaQuery.matches) {
        setIsMotionPaused(true);
      }
    }
  }, []);

  // Pan interaction handlers
  const handleMouseDown = (e) => {
    if (e.target.closest("button") || e.target.closest("[data-clickable]")) return;
    setIsPanning(true);
    startPanRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e) => {
    if (!isPanning) return;
    setPan({
      x: e.clientX - startPanRef.current.x,
      y: e.clientY - startPanRef.current.y,
    });
  };

  const handleMouseUp = () => setIsPanning(false);

  // Zoom handlers
  const zoomIn = () => setScale((s) => Math.min(s * 1.25, 3.0));
  const zoomOut = () => setScale((s) => Math.max(s / 1.25, 0.4));
  const resetView = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  const handleNodeClick = (node) => {
    setSelectedNodeId(node.id);
    setSelectedEdgeId(null);
    setIsDrawerOpen(true);
  };

  const handleNodeKeyDown = (e, node) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleNodeClick(node);
    }
  };

  const handleEdgeClick = (edge) => {
    setSelectedEdgeId(edge.id === selectedEdgeId ? null : edge.id);
  };

  const selectedNode = selectedNodeId ? positioned.get(selectedNodeId) : null;
  const nodesList = [...positioned.values()];

  return (
    <div
      ref={containerRef}
      className="relative my-3 rounded-2xl border border-white/10 bg-[#090D16] overflow-hidden select-none font-sans shadow-2xl transition-all"
      role="region"
      aria-label={sceneGraph.title || "Interactive Network Diagram"}
    >
      {/* Top Controls Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-[#0D1527]/90 border-b border-white/10 backdrop-blur-md z-10 relative">
        <div className="flex items-center gap-2">
          <span className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400">
            <Activity size={15} />
          </span>
          <span className="text-xs font-semibold text-white/90 tracking-wide">
            {sceneGraph.title}
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-white/50">
            {nodesList.length} Nodes • {sceneGraph.edges.length} Links
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1">
          {/* Pause / Resume Flow Motion */}
          <button
            type="button"
            onClick={() => setIsMotionPaused((p) => !p)}
            title={isMotionPaused ? "Putar Animasi Aliran" : "Jeda Animasi Aliran"}
            className="p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition"
            aria-label={isMotionPaused ? "Play Motion" : "Pause Motion"}
          >
            {isMotionPaused ? <Play size={14} className="text-amber-400" /> : <Pause size={14} />}
          </button>

          <div className="w-px h-3.5 bg-white/10 mx-1" />

          {/* Zoom In */}
          <button
            type="button"
            onClick={zoomIn}
            title="Perbesar"
            className="p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition"
            aria-label="Zoom in"
          >
            <ZoomIn size={14} />
          </button>

          {/* Zoom Out */}
          <button
            type="button"
            onClick={zoomOut}
            title="Perkecil"
            className="p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition"
            aria-label="Zoom out"
          >
            <ZoomOut size={14} />
          </button>

          {/* Reset Zoom & Pan */}
          <button
            type="button"
            onClick={resetView}
            title="Reset Tampilan"
            className="p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition"
            aria-label="Reset view"
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      {/* SVG Canvas Area */}
      <div
        className={`w-full h-[440px] cursor-grab ${isPanning ? "cursor-grabbing" : ""} overflow-hidden relative`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        <svg
          viewBox={viewBox}
          className="w-full h-full pointer-events-auto"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            transformOrigin: "center center",
            transition: isPanning ? "none" : "transform 0.15s ease-out",
          }}
          xmlns="http://www.w3.org/2000/svg"
        >
          <title>{sceneGraph.title}</title>
          <desc>Interactive network topology and state transition diagram.</desc>

          <defs>
            {/* Arrowhead Markers */}
            <marker id="arrow-cyan" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,1 L10,5 L0,9 z" fill="#00E5FF" />
            </marker>
            <marker id="arrow-emerald" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,1 L10,5 L0,9 z" fill="#10B981" />
            </marker>
            <marker id="arrow-rose" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,1 L10,5 L0,9 z" fill="#EF4444" />
            </marker>
            <marker id="arrow-indigo" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,1 L10,5 L0,9 z" fill="#6366F1" />
            </marker>
          </defs>

          {/* 1. EDGES & CONNECTORS */}
          <g className="edges-layer">
            {sceneGraph.edges.map((edge) => {
              const fromNode = positioned.get(edge.source);
              const toNode = positioned.get(edge.target);
              if (!fromNode || !toNode) return null;

              const isDown = edge.status === "down";
              const isSelected = edge.id === selectedEdgeId;
              const { path, labelPoint } = calculateEdgePath(fromNode, toNode, edge.kind);

              let strokeColor = "#6366F1";
              let markerId = "arrow-indigo";
              if (isDown) {
                strokeColor = "#EF4444";
                markerId = "arrow-rose";
              } else if (edge.kind === "vrrp_advertisement") {
                strokeColor = "#00E5FF";
                markerId = "arrow-cyan";
              } else if (edge.status === "up") {
                strokeColor = "#10B981";
                markerId = "arrow-emerald";
              }

              return (
                <g key={edge.id} data-clickable="true" onClick={() => handleEdgeClick(edge)} className="cursor-pointer group">
                  {/* Invisible broad hitbox for easy edge clicking */}
                  <path d={path} fill="none" stroke="transparent" strokeWidth="18" />

                  {/* Main Connector Line */}
                  <path
                    d={path}
                    fill="none"
                    stroke={strokeColor}
                    strokeWidth={isSelected ? 3.5 : 2}
                    strokeDasharray={isDown ? "6 4" : edge.trafficFlow ? "8 6" : "none"}
                    markerEnd={`url(#${markerId})`}
                    className={`transition-all duration-200 ${
                      edge.trafficFlow && !isMotionPaused && !isDown ? "animate-pulse" : ""
                    }`}
                  />

                  {/* Edge Label with Anti-Collision Pill Background */}
                  {edge.label && (
                    <g transform={`translate(${labelPoint.x}, ${labelPoint.y})`}>
                      <rect
                        x={-(edge.label.length * 3.3 + 12)}
                        y="-10"
                        width={edge.label.length * 6.6 + 24}
                        height="20"
                        rx="6"
                        fill="#0D1527"
                        stroke={isSelected ? "#00E5FF" : strokeColor}
                        strokeWidth="1"
                        className="shadow-md"
                      />
                      <text
                        x="0"
                        y="3.5"
                        textAnchor="middle"
                        fill={isDown ? "#FCA5A5" : "#E2E8F0"}
                        fontSize="9.5"
                        fontFamily="monospace"
                        fontWeight="600"
                      >
                        {edge.label}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>

          {/* 2. NODES & CLUSTERS */}
          <g className="nodes-layer">
            {nodesList.map((node) => {
              const isSelected = node.id === selectedNodeId;
              const isVrrp = node.kind === NODE_KINDS.VRRP_VIRTUAL;
              const isCluster = Boolean(node.isCluster);
              const isDown = node.status === "offline" || node.status === "down";

              let borderColor = isSelected ? "#00E5FF" : "rgba(255, 255, 255, 0.15)";
              let headerBg = "#111827";
              if (isVrrp) {
                borderColor = isSelected ? "#00E5FF" : "#0284C7";
                headerBg = "#082F49";
              } else if (isDown) {
                borderColor = "#EF4444";
                headerBg = "#450A0A";
              } else if (node.status === "master") {
                borderColor = "#10B981";
                headerBg = "#064E3B";
              } else if (node.status === "backup") {
                borderColor = "#6366F1";
                headerBg = "#1E1B4B";
              }

              return (
                <g
                  key={node.id}
                  data-clickable="true"
                  transform={`translate(${node.x}, ${node.y})`}
                  onClick={() => handleNodeClick(node)}
                  onKeyDown={(e) => handleNodeKeyDown(e, node)}
                  tabIndex={0}
                  role="button"
                  aria-label={`${node.title}, ${node.status}, ${node.kind}`}
                  className="cursor-pointer focus:outline-none transition-transform duration-150 group"
                >
                  {/* Cluster Stack Effect (Backdrop Cards) */}
                  {isCluster && (
                    <>
                      <rect x="6" y="-6" width={node.width} height={node.height} rx="14" fill="#1E1B4B" stroke="rgba(99, 102, 241, 0.4)" strokeWidth="1" />
                      <rect x="3" y="-3" width={node.width} height={node.height} rx="14" fill="#0F172A" stroke="rgba(255, 255, 255, 0.1)" strokeWidth="1" />
                    </>
                  )}

                  {/* Node Main Surface */}
                  <rect
                    x="0"
                    y="0"
                    width={node.width}
                    height={node.height}
                    rx="14"
                    fill="#0D1527"
                    stroke={borderColor}
                    strokeWidth={isSelected ? "2.5" : "1.5"}
                    className="shadow-xl"
                  />

                  {/* Header Bar Accent */}
                  <path
                    d={`M 1 14 A 13 13 0 0 1 14 1 L ${node.width - 14} 1 A 13 13 0 0 1 ${node.width - 1} 14 L ${node.width - 1} 24 L 1 24 Z`}
                    fill={headerBg}
                  />

                  {/* Status Indicator Dot */}
                  <circle
                    cx="16"
                    cy="12"
                    r="4"
                    fill={isDown ? "#EF4444" : node.status === "master" ? "#10B981" : "#6366F1"}
                    className={!isMotionPaused && !isDown ? "animate-pulse" : ""}
                  />

                  {/* Node Title */}
                  <text
                    x="28"
                    y="15.5"
                    fill="#FFFFFF"
                    fontSize="11.5"
                    fontWeight="700"
                    fontFamily="sans-serif"
                    letterSpacing="0.2"
                  >
                    {node.title}
                  </text>

                  {/* Node Subtitle / IP */}
                  <text
                    x="16"
                    y="42"
                    fill="rgba(255, 255, 255, 0.65)"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    {node.subtitle || node.ip || "Node"}
                  </text>

                  {/* Badges Pill Row */}
                  {node.badges && node.badges.length > 0 && (
                    <g transform="translate(16, 56)">
                      {node.badges.slice(0, 2).map((badge, bIdx) => {
                        const badgeWidth = badge.length * 5.8 + 12;
                        const offsetX = bIdx * 80;
                        return (
                          <g key={bIdx} transform={`translate(${offsetX}, 0)`}>
                            <rect
                              x="0"
                              y="0"
                              width={badgeWidth}
                              height="16"
                              rx="4"
                              fill="rgba(255, 255, 255, 0.08)"
                              stroke="rgba(255, 255, 255, 0.15)"
                              strokeWidth="0.8"
                            />
                            <text
                              x={badgeWidth / 2}
                              y="11.5"
                              textAnchor="middle"
                              fill="#00E5FF"
                              fontSize="8.5"
                              fontFamily="monospace"
                              fontWeight="600"
                            >
                              {badge}
                            </text>
                          </g>
                        );
                      })}
                    </g>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Edge Detail Popup (when edge is clicked) */}
        {selectedEdgeId && (
          <div className="absolute bottom-3 left-3 z-20 bg-slate-900/90 border border-cyan-500/30 rounded-xl p-3 shadow-xl backdrop-blur-md text-xs font-mono max-w-xs space-y-1">
            <div className="flex items-center justify-between font-bold text-cyan-300">
              <span>Rincian Link Koneksi</span>
              <button
                type="button"
                onClick={() => setSelectedEdgeId(null)}
                className="text-white/40 hover:text-white"
              >
                ✕
              </button>
            </div>
            {(() => {
              const edge = sceneGraph.edges.find((e) => e.id === selectedEdgeId);
              if (!edge) return null;
              return (
                <div className="space-y-0.5 text-white/80 text-[11px]">
                  <div>Tipe: <span className="text-cyan-400 capitalize">{edge.kind}</span></div>
                  <div>Status: <span className={edge.status === "down" ? "text-rose-400 font-bold" : "text-emerald-400 font-bold"}>{edge.status.toUpperCase()}</span></div>
                  <div>Jalur: {edge.source} ➔ {edge.target}</div>
                  {edge.label && <div className="text-white/60 mt-1 italic">{edge.label}</div>}
                </div>
              );
            })()}
          </div>
        )}
      </div>

      {/* Detail Drawer (when node is clicked) */}
      {isDrawerOpen && selectedNode && (
        <DeviceDetailDrawer
          node={selectedNode}
          onClose={() => setIsDrawerOpen(false)}
          onAction={onAction}
        />
      )}
    </div>
  );
}
