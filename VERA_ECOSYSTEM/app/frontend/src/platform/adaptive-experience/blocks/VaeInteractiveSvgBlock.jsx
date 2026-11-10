/**
 * src/platform/adaptive-experience/blocks/VaeInteractiveSvgBlock.jsx
 *
 * Registered VAE Block for Interactive SVG, Topology Graphs, and Protocol State Machines.
 * Seamlessly arbitrates between interactive scene graphs and static SVG illustrations.
 */

import React, { useMemo } from "react";
import InteractiveSvgCanvas from "../svg/InteractiveSvgCanvas.jsx";
import { buildVrrpFailoverSceneGraph } from "../svg/sceneGraph.js";
import { buildSafeSvg } from "../assets/svgBuilder.js";
import InteractiveSvgPreview from "../../../components/InteractiveSvgPreview.jsx";

export default function VaeInteractiveSvgBlock({ block, onActionInvoke }) {
  const data = block?.data || {};

  const graph = useMemo(() => {
    // Case 1: Structured nodes and edges provided
    if (Array.isArray(data.nodes)) {
      return data;
    }

    // Case 2: VRRP specific payload
    if (data.type === "vrrp" || data.vrrp || block?.type === "vrrp") {
      return buildVrrpFailoverSceneGraph(data.vrrp || data);
    }

    // Case 3: Embedded graph payload
    if (data.graph && typeof data.graph === "object") {
      return data.graph;
    }

    // Case 4: Raw JSON string graph
    if (typeof data.code === "string") {
      try {
        const parsed = JSON.parse(data.code);
        if (Array.isArray(parsed.nodes)) return parsed;
      } catch {}
    }

    return null;
  }, [data, block?.type]);

  // If structured graph data is present, render with full React-managed SVG interactivity
  if (graph) {
    return <InteractiveSvgCanvas graph={graph} onAction={onActionInvoke} />;
  }

  // Safe interactive SVG rendering if raw XML code was provided
  const rawCode = data.code || data.xml || (typeof data === "string" ? data : "");
  if (rawCode && rawCode.trim()) {
    return <InteractiveSvgPreview code={rawCode} title={block?.title || "Diagram Interaktif"} />;
  }

  return (
    <div className="p-3 my-2 rounded-xl border border-white/10 bg-black/40 text-xs font-mono text-white/50">
      Diagram SVG tidak memuat data yang valid.
    </div>
  );
}
