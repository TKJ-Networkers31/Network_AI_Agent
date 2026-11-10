/**
 * src/platform/adaptive-experience/blocks/MetricGridBlock.jsx
 *
 * Multi-card responsive grid of hardware or operational metrics.
 */

import React from "react";
import MetricCard from "../../../components/MetricCard.jsx";

export default function MetricGridBlock({ block }) {
  const items = block?.data?.items || [];
  if (!items || items.length === 0) return null;

  return (
    <div className="my-2 grid grid-cols-2 md:grid-cols-4 gap-2.5">
      {items.map((item, idx) => (
        <MetricCard
          key={idx}
          title={item.title || "Metrik"}
          value={item.value ?? 0}
          unit={item.unit || ""}
          trend={item.trend}
          status={item.status || "healthy"}
          subtitle={item.subtitle}
        />
      ))}
    </div>
  );
}
