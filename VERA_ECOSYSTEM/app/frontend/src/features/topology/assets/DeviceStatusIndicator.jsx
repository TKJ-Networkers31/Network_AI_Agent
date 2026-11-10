import React from "react";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HelpCircle,
  Clock,
  Slash,
} from "lucide-react";
import {
  DEVICE_STATUSES,
  normalizeDeviceStatus,
  getDeviceStatusStyle,
} from "./deviceStatusCore.js";

export { DEVICE_STATUSES, normalizeDeviceStatus, getDeviceStatusStyle };

const STATUS_ICONS = {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HelpCircle,
  Clock,
  Slash,
};

/**
 * Reusable Status Indicator Badge / Pill Component
 */
export default function DeviceStatusIndicator({
  status: rawStatus,
  size = "sm",
  showLabel = true,
  className = "",
}) {
  const config = getDeviceStatusStyle(rawStatus);
  const { label, badgeBg, badgeText, badgeBorder, dotBg, dotPing, iconName } = config;
  const Icon = STATUS_ICONS[iconName] || HelpCircle;

  const isMini = size === "xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[9px] font-bold tracking-wider uppercase select-none transition-colors ${badgeBg} ${badgeText} ${badgeBorder} ${className}`}
      title={`Operational Status: ${label}`}
      role="status"
    >
      <span className="relative flex h-1.5 w-1.5">
        {dotPing && (
          <span
            className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${dotBg} ${dotPing}`}
          />
        )}
        <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${dotBg}`} />
      </span>
      {showLabel && <span>{label}</span>}
      {!showLabel && <Icon size={isMini ? 10 : 12} />}
    </span>
  );
}
