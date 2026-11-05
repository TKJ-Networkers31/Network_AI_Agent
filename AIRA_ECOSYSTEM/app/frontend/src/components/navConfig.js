// src/components/navConfig.js
// Struktur menu navigasi terpadu AIRA OS (dipakai Sidebar.jsx & MobileNav.jsx).
// Minimalist AI Workspace: 5 tujuan utama pelanggan + 1 area administrasi platform terpisah.

import {
  Activity,
  FolderOpen,
  MessageSquare,
  Network,
  Settings,
  ShieldCheck,
  Zap,
} from "lucide-react";

export const NAV_GROUPS = [
  {
    id: "main",
    label: "Workspace",
    items: [
      { id: "workspace", label: "Workspace", icon: MessageSquare },
      { id: "infrastructure", label: "Infrastructure", icon: Network },
      { id: "automations", label: "Automations", icon: Zap },
      { id: "files", label: "Files", icon: FolderOpen },
      { id: "settings", label: "Settings", icon: Settings },
    ],
  },
  {
    id: "admin",
    label: "Platform Admin",
    items: [
      { id: "admin", label: "Admin Platform", icon: ShieldCheck },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
