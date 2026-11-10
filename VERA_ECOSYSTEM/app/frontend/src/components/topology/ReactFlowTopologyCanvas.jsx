import React, { useCallback, useMemo, useState, useEffect } from "react";
import DeviceNode from "../../features/topology/assets/DeviceNode.jsx";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Handle,
  Position,
  getBezierPath,
  BaseEdge,
  EdgeLabelRenderer,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Router,
  Server,
  Monitor,
  Wifi,
  Globe,
  Radio,
  Layers,
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Terminal,
  Shield,
  Eye,
  RefreshCw,
  ExternalLink,
  ChevronRight,
} from "lucide-react";

// ============================================================================
// DEVICE ICONS & COLOR MAPS
// ============================================================================
const NODE_ICONS = {
  mikrotik_router: Router,
  generic_router: Router,
  router: Router,
  switch: Layers,
  access_point: Wifi,
  ap: Wifi,
  server: Server,
  client: Monitor,
  workstation: Monitor,
  wireless_client: Radio,
  internet_gateway: Globe,
  gateway: Globe,
  internet: Globe,
  unknown: Radio,
};

const STATUS_GLOWS = {
  up: "ring-1 ring-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.25)] border-emerald-500/30",
  online: "ring-1 ring-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.25)] border-emerald-500/30",
  down: "ring-1 ring-rose-500/40 shadow-[0_0_15px_rgba(244,63,94,0.25)] border-rose-500/30",
  offline: "ring-1 ring-rose-500/40 shadow-[0_0_15px_rgba(244,63,94,0.25)] border-rose-500/30",
  degraded: "ring-1 ring-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.25)] border-amber-500/30",
  unknown: "ring-1 ring-white/10 border-white/10",
};

// ============================================================================
// CUSTOM NETWORK NODE COMPONENT
// ============================================================================
export function NetworkDeviceNode({ data, selected }) {
  const nodeType = data.device_type || data.type || "unknown";
  const Icon = NODE_ICONS[nodeType] || NODE_ICONS.unknown;
  const status = (data.status || "unknown").toLowerCase();
  const isUp = status === "up" || status === "online";
  const isDown = status === "down" || status === "offline";
  const isDegraded = status === "degraded" || status === "warning";

  const glowClass = isUp
    ? STATUS_GLOWS.up
    : isDown
    ? STATUS_GLOWS.down
    : isDegraded
    ? STATUS_GLOWS.degraded
    : STATUS_GLOWS.unknown;

  const isMikrotik = nodeType === "mikrotik_router" || (data.vendor || "").toLowerCase().includes("mikrotik");

  return (
    <div
      className={`group relative rounded-xl bg-zinc-950/95 border backdrop-blur-md px-3.5 py-3 min-w-[190px] max-w-[240px] text-left transition-all duration-200 select-none ${glowClass} ${
        selected ? "ring-2 ring-cyan-400 border-cyan-400 shadow-[0_0_25px_rgba(34,211,238,0.4)]" : "hover:border-white/20"
      }`}
    >
      {/* Visual Connection Handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-zinc-950 transition-transform group-hover:scale-125"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-zinc-950 transition-transform group-hover:scale-125"
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-zinc-950 transition-transform group-hover:scale-125"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-zinc-950 transition-transform group-hover:scale-125"
      />

      {/* Header with Type Emblem & Live Status Pill */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          <div
            className={`p-1.5 rounded-lg border ${
              isUp
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                : isDown
                ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                : "bg-white/5 text-white/60 border-white/10"
            }`}
          >
            <Icon size={14} className={isUp ? "animate-pulse" : ""} />
          </div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/50">
            {isMikrotik ? "RouterOS" : nodeType.replace(/_/g, " ")}
          </span>
        </div>

        {/* UP/DOWN Live Pill */}
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border ${
            isUp
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : isDown
              ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
              : "bg-white/5 text-white/40 border-white/10"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isUp ? "bg-emerald-400 animate-ping" : isDown ? "bg-rose-400" : "bg-white/40"
            }`}
          />
          {status}
        </span>
      </div>

      {/* Device Name / Label */}
      <div className="font-semibold text-xs text-white truncate tracking-wide" title={data.label || data.name}>
        {data.label || data.name || data.id}
      </div>

      {/* IP & Metadata Row */}
      <div className="mt-1 flex items-center justify-between text-[11px] font-mono text-white/60">
        <span className="truncate">{data.ip || data.management_ip || data.host || "-"}</span>
        {data.role && (
          <span className="text-[9px] px-1.5 py-0.2 rounded bg-white/5 text-white/40 uppercase">
            {data.role}
          </span>
        )}
      </div>

      {/* Sub-Metrics Pill (Ports / CPU / Latency) */}
      {(data.ports_count != null || data.cpu_load != null || data.latency_ms != null) && (
        <div className="mt-2 pt-2 border-t border-white/5 flex items-center justify-between text-[10px] font-mono text-white/40">
          {data.ports_count != null && <span>Ports: {data.ports_count}</span>}
          {data.cpu_load != null && <span>CPU: {data.cpu_load}%</span>}
          {data.latency_ms != null && <span>{Math.round(data.latency_ms)}ms</span>}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// CUSTOM MULTI-LAYER EVIDENCE EDGE COMPONENT
// ============================================================================
export function MultiLayerEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data = {},
  selected,
}) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetPosition,
    targetX,
    targetY,
  });

  const layer = data.layer || data.relationship_class || "physical";
  const operStatus = (data.oper_status || "up").toLowerCase();
  const isUp = operStatus === "up" || operStatus === "active";
  const confidence = data.confidence_score ?? data.confidence ?? 1.0;

  // Evidence-based styling
  let strokeColor = "#10b981"; // Physical: solid emerald
  let strokeDasharray = undefined;
  let strokeWidth = selected ? 3 : 2;

  if (layer === "layer2" || data.evidence_type === "mndp" || data.evidence_type === "lldp") {
    strokeColor = "#06b6d4"; // Layer 2 / MNDP: cyan
  } else if (layer === "layer3" || data.evidence_type === "arp") {
    strokeColor = "#f59e0b"; // Layer 3 / ARP: amber dashed
    strokeDasharray = "6 4";
  } else if (layer === "routing" || data.evidence_type === "routing_table") {
    strokeColor = "#a855f7"; // Routing: purple dotted
    strokeDasharray = "3 3";
  } else if (layer === "logical" || data.inferred) {
    strokeColor = "#3b82f6"; // Inferred: blue dashed
    strokeDasharray = "4 4";
    strokeWidth = 1.5;
  }

  if (!isUp) {
    strokeColor = "#f43f5e"; // Down: rose
    strokeDasharray = "4 4";
  }

  const labelText = data.label || (data.src_if && data.dst_if ? `${data.src_if} ↔ ${data.dst_if}` : null);

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray,
          filter: selected ? `drop-shadow(0 0 6px ${strokeColor})` : undefined,
          transition: "all 0.2s ease",
        }}
      />
      {labelText && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className="nodrag nopan px-2 py-0.5 rounded-full bg-zinc-950/90 border border-white/10 text-[9px] font-mono text-white/70 shadow-md backdrop-blur-sm cursor-pointer hover:border-cyan-400 hover:text-white transition-colors"
          >
            {labelText}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

// Node types registry using Centralized Device Node & Asset Library
const nodeTypes = {
  networkDevice: DeviceNode,
  mikrotik_router: DeviceNode,
  generic_router: DeviceNode,
  router: DeviceNode,
  switch: DeviceNode,
  switch_l2: DeviceNode,
  switch_l3: DeviceNode,
  firewall: DeviceNode,
  access_point: DeviceNode,
  ap: DeviceNode,
  server: DeviceNode,
  client: DeviceNode,
  workstation: DeviceNode,
  wireless_client: DeviceNode,
  internet_gateway: DeviceNode,
  gateway: DeviceNode,
  internet: DeviceNode,
  unknown: DeviceNode,
};

// Edge types registry
const edgeTypes = {
  multiLayer: MultiLayerEdge,
};

// ============================================================================
// MAIN REACT FLOW TOPOLOGY CANVAS
// ============================================================================
export default function ReactFlowTopologyCanvas({
  nodes: rawNodes = [],
  links: rawLinks = [],
  selectedNode = null,
  selectedEdge = null,
  onNodeClick = () => {},
  onNodeDoubleClick = () => {},
  onEdgeClick = () => {},
  onNodeContextMenu = () => {},
  onNodePositionChange = () => {},
  searchQuery = "",
  layerFilters = { physical: true, layer2: true, layer3: true, logical: true },
}) {
  // Convert API nodes to React Flow nodes
  const rfNodes = useMemo(() => {
    return rawNodes.map((n, idx) => {
      const isMatch =
        !searchQuery ||
        (n.label || n.name || n.id || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
        (n.ip || "").includes(searchQuery);

      const posX = n.pos_x != null ? n.pos_x : 100 + (idx % 4) * 260;
      const posY = n.pos_y != null ? n.pos_y : 80 + Math.floor(idx / 4) * 180;

      return {
        id: n.id,
        type: "networkDevice",
        position: { x: posX, y: posY },
        data: {
          ...n,
          label: n.label || n.name || n.id,
          ip: n.ip || n.management_ip || n.host,
          status: n.status || n.oper_status || "unknown",
          device_type: n.device_type || n.type || "unknown",
        },
        selected: selectedNode?.id === n.id,
        style: {
          opacity: isMatch ? 1 : 0.25,
          transition: "opacity 0.2s ease",
        },
      };
    });
  }, [rawNodes, selectedNode, searchQuery]);

  // Convert API links to React Flow edges
  const rfEdges = useMemo(() => {
    return rawLinks
      .filter((link) => {
        const layer = link.layer || link.relationship_class || "physical";
        if (layer === "physical" && !layerFilters.physical) return false;
        if (layer === "layer2" && !layerFilters.layer2) return false;
        if (layer === "layer3" && !layerFilters.layer3) return false;
        if (layer === "logical" && !layerFilters.logical) return false;
        return true;
      })
      .map((link) => {
        const edgeId = link.id || `${link.source_node_id || link.source}-${link.target_node_id || link.target}`;
        return {
          id: edgeId,
          source: link.source_node_id || link.source,
          target: link.target_node_id || link.target,
          type: "multiLayer",
          data: link,
          selected: selectedEdge?.id === edgeId,
          animated: link.oper_status === "up" || link.lifecycle_state === "ACTIVE",
        };
      });
  }, [rawLinks, selectedEdge, layerFilters]);

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  // Sync state when props update
  useEffect(() => {
    setNodes(rfNodes);
  }, [rfNodes, setNodes]);

  useEffect(() => {
    setEdges(rfEdges);
  }, [rfEdges, setEdges]);

  // Handle drag stop -> persist node coordinates to backend
  const handleNodeDragStop = useCallback(
    (event, node) => {
      onNodePositionChange(node.id, Math.round(node.position.x), Math.round(node.position.y));
    },
    [onNodePositionChange]
  );

  return (
    <div className="w-full h-full relative bg-[#030712] select-none">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(_, node) => onNodeClick(node.data)}
        onNodeDoubleClick={(_, node) => onNodeDoubleClick(node.data)}
        onEdgeClick={(_, edge) => onEdgeClick(edge.data)}
        onNodeContextMenu={(event, node) => {
          event.preventDefault();
          onNodeContextMenu(event, node.data);
        }}
        onNodeDragStop={handleNodeDragStop}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2.5}
        className="react-flow-dark"
      >
        <Background color="#1e293b" gap={24} size={1} />
        <Controls
          className="!bg-zinc-900/90 !border-white/10 !fill-white !text-white !rounded-xl !shadow-xl [&>button]:!border-white/10 [&>button:hover]:!bg-white/10"
        />
        <MiniMap
          nodeColor={(n) => {
            const status = (n.data?.status || "").toLowerCase();
            if (status === "up" || status === "online") return "#10b981";
            if (status === "down" || status === "offline") return "#f43f5e";
            if (status === "degraded") return "#f59e0b";
            return "#475569";
          }}
          maskColor="rgba(3, 7, 18, 0.75)"
          className="!bg-zinc-950/90 !border !border-white/10 !rounded-xl !overflow-hidden"
        />
      </ReactFlow>
    </div>
  );
}
