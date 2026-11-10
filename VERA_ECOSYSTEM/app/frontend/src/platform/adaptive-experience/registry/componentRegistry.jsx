/**
 * src/platform/adaptive-experience/registry/componentRegistry.jsx
 *
 * Centralized VAE Component Registry & Bindings.
 * Maps VAE block types to concrete React components.
 */

import React, { lazy } from "react";
import Markdown from "../../../components/Markdown.jsx";
import MetricCard from "../../../components/MetricCard.jsx";
import UnknownBlockFallback from "../renderer/UnknownBlockFallback.jsx";
import Renderer from "../../../components/dio/Renderer.jsx";
import {
  registerVaeComponent,
  getVaeComponent as coreGetVaeComponent,
  hasVaeComponent,
  listRegisteredVaeComponents,
} from "./registryCore.js";

// VAE Generative UI Component Imports
import ResourceGaugeBlock from "../blocks/ResourceGaugeBlock.jsx";
import MetricGridBlock from "../blocks/MetricGridBlock.jsx";
import InterfaceStatusBlock from "../blocks/InterfaceStatusBlock.jsx";
import TraceroutePathBlock from "../blocks/TraceroutePathBlock.jsx";
import RouteTableViewBlock from "../blocks/RouteTableViewBlock.jsx";
import IncidentSummaryBlock from "../blocks/IncidentSummaryBlock.jsx";
import ConfigDiffBlock from "../blocks/ConfigDiffBlock.jsx";
import WorkflowRecoveryBlock from "../blocks/WorkflowRecoveryBlock.jsx";
import InvestigationTimelineBlock from "../blocks/InvestigationTimelineBlock.jsx";
import HealthSummaryBlock from "../blocks/HealthSummaryBlock.jsx";
import TopologyDetailBlock from "../blocks/TopologyDetailBlock.jsx";
import VaeInteractiveSvgBlock from "../blocks/VaeInteractiveSvgBlock.jsx";

// Lazy-load heavy visualization components
const GraphBlock = lazy(() => import("../../../components/GraphBlock.jsx"));
const MapBlock = lazy(() => import("../../../components/MapBlock.jsx"));
const MermaidBlock = lazy(() => import("../../../components/MermaidBlock.jsx"));
const UnifiedActionCard = lazy(() => import("../interactions/UnifiedActionCard.jsx"));

// Component Adapters
function MarkdownBlockAdapter({ block }) {
  const content = block?.data?.content || "";
  return <Markdown content={content} />;
}

function MetricCardAdapter({ block }) {
  const data = block?.data || {};
  return (
    <div className="my-2 max-w-sm">
      <MetricCard
        title={data.title || "Metrik"}
        value={data.value ?? 0}
        unit={data.unit || ""}
        trend={data.trend}
        status={data.status || "healthy"}
        subtitle={data.subtitle}
      />
    </div>
  );
}

function DioInteractionAdapter({ block, onInteractionSubmit }) {
  const schema = block?.data?.schema;
  if (!schema) return null;
  return <Renderer schema={schema} onSubmitAction={onInteractionSubmit} />;
}

function ActionCardAdapter({ block, onActionInvoke }) {
  return <UnifiedActionCard data={block?.data} onActionInvoke={onActionInvoke} />;
}

function GraphBlockAdapter({ block }) {
  const code =
    typeof block?.data?.graph === "string"
      ? block.data.graph
      : JSON.stringify(block?.data || {});
  return <GraphBlock code={code} />;
}

function MapBlockAdapter({ block }) {
  const code =
    typeof block?.data?.map === "string"
      ? block.data.map
      : JSON.stringify(block?.data || {});
  return <MapBlock code={code} />;
}

function MermaidBlockAdapter({ block }) {
  const code = block?.data?.code || block?.data?.syntax || "";
  return <MermaidBlock code={code} />;
}

// Register standard VAE component bindings
registerVaeComponent("markdown", MarkdownBlockAdapter, { isLazy: false });
registerVaeComponent("text", MarkdownBlockAdapter, { isLazy: false });
registerVaeComponent("metric-card", MetricCardAdapter, { isLazy: false });
registerVaeComponent("metric-grid", MetricGridBlock, { isLazy: false });
registerVaeComponent("resource-gauge", ResourceGaugeBlock, { isLazy: false });
registerVaeComponent("interface-status", InterfaceStatusBlock, { isLazy: false });
registerVaeComponent("hop-by-hop-traceroute", TraceroutePathBlock, { isLazy: false });
registerVaeComponent("traceroute-path", TraceroutePathBlock, { isLazy: false });
registerVaeComponent("route-table-view", RouteTableViewBlock, { isLazy: false });
registerVaeComponent("route-table", RouteTableViewBlock, { isLazy: false });
registerVaeComponent("incident-summary", IncidentSummaryBlock, { isLazy: false });
registerVaeComponent("root-cause-panel", IncidentSummaryBlock, { isLazy: false });
registerVaeComponent("config-diff", ConfigDiffBlock, { isLazy: false });
registerVaeComponent("workflow-recovery", WorkflowRecoveryBlock, { isLazy: false });
registerVaeComponent("investigation-timeline", InvestigationTimelineBlock, { isLazy: false });
registerVaeComponent("timeline", InvestigationTimelineBlock, { isLazy: false });
registerVaeComponent("health-summary", HealthSummaryBlock, { isLazy: false });
registerVaeComponent("topology-detail", TopologyDetailBlock, { isLazy: false });
registerVaeComponent("node-detail", TopologyDetailBlock, { isLazy: false });
registerVaeComponent("edge-detail", TopologyDetailBlock, { isLazy: false });
registerVaeComponent("dio-interaction", DioInteractionAdapter, { isLazy: false });
registerVaeComponent("action-card", ActionCardAdapter, { isLazy: true });
registerVaeComponent("unified-action-card", ActionCardAdapter, { isLazy: true });
registerVaeComponent("action", ActionCardAdapter, { isLazy: true });
registerVaeComponent("svg", VaeInteractiveSvgBlock, { isLazy: false });
registerVaeComponent("interactive-svg", VaeInteractiveSvgBlock, { isLazy: false });
registerVaeComponent("vrrp", VaeInteractiveSvgBlock, { isLazy: false });
registerVaeComponent("topology-graph", VaeInteractiveSvgBlock, { isLazy: false });
registerVaeComponent("graph", VaeInteractiveSvgBlock, { isLazy: false });
registerVaeComponent("map", MapBlockAdapter, { isLazy: true });
registerVaeComponent("mermaid", MermaidBlockAdapter, { isLazy: true });

export function getVaeComponent(type) {
  return coreGetVaeComponent(type, UnknownBlockFallback);
}

export { hasVaeComponent, listRegisteredVaeComponents, registerVaeComponent };
