// src/components/navConfig.js
// Struktur menu navigasi terpadu VERA (dipakai Sidebar.jsx & MobileNav.jsx).

import {
  Activity,
  Cpu,
  FileText,
  FolderOpen,
  MessageSquare,
  Network,
  ShieldCheck,
  Zap,
} from "lucide-react";

export const NAV_GROUPS = [
  {
    id: "observability",
    label: "Observability & Intelligence",
    items: [
      { id: "intelligence", label: "Network Intelligence", icon: Activity, requiredPermission: "nms.read" },
      { id: "infrastructure", label: "Infrastructure Fabric", icon: Network, requiredPermission: "inventory.view" },
      { id: "workspace", label: "AI Diagnostics", icon: MessageSquare, requiredPermission: "workspace.view" },
    ],
  },
  {
    id: "engineering",
    label: "Operations & Automation",
    items: [
      { id: "automations", label: "Automations", icon: Zap, requiredPermission: "automations.view" },
      { id: "files", label: "Files & Artifacts", icon: FolderOpen, requiredPermission: "files.view" },
      { id: "logs", label: "Logs & Telemetry", icon: FileText, requiredPermission: "logs.view" },
    ],
  },
  {
    id: "admin",
    label: "Control Plane",
    items: [
      { id: "models", label: "Models & Reasoning", icon: Cpu, superAdminOnly: true },
      { id: "admin", label: "VERA Control Plane", icon: ShieldCheck, adminOnly: true, requiredPermission: "admin.view" },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
