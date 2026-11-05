// src/components/navConfig.js
// Struktur menu navigasi terpadu AIRA OS (dipakai Sidebar.jsx & MobileNav.jsx).

import {
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
    label: "Workspace",
    items: [
      { id: "workspace", label: "Workspace", icon: MessageSquare },
      { id: "infrastructure", label: "Infrastructure", icon: Network, requiredPermission: "inventory.read" },
      { id: "automations", label: "Automations", icon: Zap, requiredPermission: "playbooks.read" },
      { id: "files", label: "Files", icon: FolderOpen },
      { id: "models", label: "Models", icon: Cpu, requiredPermission: "settings.read" },
      { id: "logs", label: "Logs", icon: FileText, requiredPermission: "audit.read" },
    ],
  },
  {
    id: "admin",
    label: "Control Plane",
    items: [
      { id: "admin", label: "AIRA Control Plane", icon: ShieldCheck, adminOnly: true },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
