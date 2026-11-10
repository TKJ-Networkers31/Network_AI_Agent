/**
 * src/platform/adaptive-experience/renderer/ExperienceRenderer.jsx
 *
 * Top-Level Experience Renderer for VERA Adaptive Experience (VAE).
 * Coordinates response normalization, component resolution, error boundary
 * wrapping, and mixed text + structured output rendering.
 */

import React, { Suspense, useEffect } from "react";
import { normalizeToVaeBlocks } from "../protocol/vaeProtocol.js";
import { getVaeComponent } from "../registry/componentRegistry.jsx";
import { ComponentErrorBoundary } from "./ComponentErrorBoundary.jsx";
import { trackBlockRendered } from "../telemetry/experienceTelemetry.js";
import StreamingMarkdown from "../../../components/StreamingMarkdown.jsx";

export default function ExperienceRenderer({
  content,
  interactionSchema,
  interactionResolved,
  interactionStatus,
  blocks,
  streaming = false,
  streamed = false,
  onInteractionSubmit,
  onActionInvoke,
}) {
  // Normalize incoming payload into formal VAE blocks
  const normalizedBlocks = React.useMemo(() => {
    return normalizeToVaeBlocks({ content, interactionSchema, blocks });
  }, [content, interactionSchema, blocks]);

  useEffect(() => {
    if (normalizedBlocks && normalizedBlocks.length > 0) {
      for (const block of normalizedBlocks) {
        trackBlockRendered({
          blockType: block.type,
          blockId: block.id,
          success: true,
        });
      }
    }
  }, [normalizedBlocks]);

  const hasWorkflowRecovery = React.useMemo(() => {
    return normalizedBlocks?.some((b) => b.type === "workflow-recovery") || false;
  }, [normalizedBlocks]);

  if (!normalizedBlocks || normalizedBlocks.length === 0) {
    return null;
  }

  return (
    <div className="vae-experience-container space-y-3">
      {normalizedBlocks.map((block) => {
        // Handle DIO interaction block with resolution state check
        if (block.type === "dio-interaction") {
          if (interactionResolved) {
            const isCancelled = interactionStatus === "CANCELLED" || block.status === "CANCELLED";
            const isExpired = interactionStatus === "EXPIRED" || block.status === "EXPIRED";

            return (
              <div
                key={block.id}
                className={`flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg border font-medium ${
                  isCancelled || isExpired
                    ? "text-white/40 bg-white/5 border-white/10"
                    : hasWorkflowRecovery
                    ? "text-amber-400/90 bg-amber-500/10 border-amber-500/20"
                    : "text-emerald-400/90 bg-emerald-500/10 border-emerald-500/20"
                }`}
              >
                <span>
                  {isCancelled ? "✕" : isExpired ? "⏱" : hasWorkflowRecovery ? "⚠" : "✓"}
                </span>
                <span>
                  {isCancelled
                    ? "Formulir dibatalkan."
                    : isExpired
                    ? "Formulir telah kedaluwarsa."
                    : hasWorkflowRecovery
                    ? "Permintaan terkirim, namun memerlukan tindakan pemulihan di bawah ini."
                    : "Formulir telah dikirim."}
                </span>
              </div>
            );
          }
        }

        // Handle streaming markdown block
        if (block.type === "markdown" && (streaming || streamed)) {
          return (
            <ComponentErrorBoundary key={block.id}>
              <StreamingMarkdown
                content={block.data?.content || ""}
                streaming={Boolean(streaming)}
              />
            </ComponentErrorBoundary>
          );
        }

        const Component = getVaeComponent(block.type);

        return (
          <ComponentErrorBoundary key={block.id}>
            <Suspense
              fallback={
                <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 text-xs text-text-secondary animate-pulse">
                  Memuat komponen VAE ({block.type})...
                </div>
              }
            >
              <Component
                block={block}
                onInteractionSubmit={onInteractionSubmit}
                onActionInvoke={onActionInvoke}
              />
            </Suspense>
          </ComponentErrorBoundary>
        );
      })}
    </div>
  );
}
