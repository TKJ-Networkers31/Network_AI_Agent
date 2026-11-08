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
    id: "main",
    label: "Intelligence & Ops",
    items: [
      { id: "intelligence", label: "Network Intelligence", icon: Activity, requiredPermission: "nms.read" },
      { id: "infrastructure", label: "Infrastructure", icon: Network, requiredPermission: "inventory.view" },
      { id: "workspace", label: "AI Diagnostics", icon: MessageSquare, requiredPermission: "workspace.view" },
      { id: "automations", label: "Automations", icon: Zap, requiredPermission: "automations.view" },
      { id: "files", label: "Files", icon: FolderOpen, requiredPermission: "files.view" },
      { id: "models", label: "Models", icon: Cpu, superAdminOnly: true },
      { id: "logs", label: "Logs", icon: FileText, requiredPermission: "logs.view" },
    ],
  },
  {
    id: "admin",
    label: "Control Plane",
    items: [
      { id: "admin", label: "VERA Control Plane", icon: ShieldCheck, adminOnly: true, requiredPermission: "admin.view" },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
