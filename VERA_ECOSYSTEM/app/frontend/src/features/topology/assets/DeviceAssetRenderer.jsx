import React from "react";
import { resolveDeviceAsset, getDeviceAsset } from "./deviceAssetRegistry.js";
import { getDeviceStatusStyle } from "./DeviceStatusIndicator.jsx";

/**
 * Reusable Device Asset Renderer
 * Renders consistent vector device illustrations from the centralized registry.
 */
export default function DeviceAssetRenderer({
  assetKey,
  device,
  size = 40,
  status = null,
  showGlow = false,
  className = "",
  ...props
}) {
  // Resolve asset either by explicit key or device metadata
  const asset = device ? resolveDeviceAsset(device) : getDeviceAsset(assetKey);
  const SvgComponent = asset.component;

  // Optional status glow styling
  const statusStyle = status ? getDeviceStatusStyle(status) : null;

  return (
    <div
      className={`relative inline-flex items-center justify-center shrink-0 ${className}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={asset.label}
      {...props}
    >
      {/* Optional ambient status halo */}
      {showGlow && statusStyle && statusStyle.haloShadow !== "shadow-none" && (
        <div
          className={`absolute inset-0 rounded-full blur-md opacity-40 transition-all ${statusStyle.haloShadow}`}
          style={{ backgroundColor: statusStyle.hexColor }}
        />
      )}

      {/* Primary Vector Device Illustration */}
      <SvgComponent
        className="relative z-10 w-full h-full object-contain transition-transform"
      />
    </div>
  );
}
