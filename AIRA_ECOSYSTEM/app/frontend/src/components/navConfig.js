// src/components/navConfig.js
// Sumber tunggal struktur menu (dipakai Sidebar.jsx & MobileNav.jsx).
// Tambah halaman baru: tambahkan item di grup yang sesuai + daftarkan
// di PAGES pada App.jsx.

import {
  Activity,
  MessageSquare,
  FolderOpen,
  Server,
  Cable,
  Network,
  Cpu,
  Sparkles,
  Brain,
  ScrollText,
  Settings,
  ShieldCheck,
} from "lucide-react";

export const NAV_GROUPS = [
  {
    id: "main",
    label: "Utama",
    items: [
      { id: "chat", label: "Chat", icon: MessageSquare },
      { id: "workspace", label: "Workspace", icon: FolderOpen },
    ],
  },
  {
    id: "network",
    label: "Jaringan",
    items: [
      { id: "topology", label: "Topology", icon: Network },
      { id: "nms", label: "Monitoring NMS", icon: Activity },
      { id: "devices", label: "Devices", icon: Server },
      { id: "intelligence", label: "Investigasi & Planning", icon: ShieldCheck },
      { id: "akane", label: "AKANE", icon: Cable },
    ],
  },
  {
    id: "ai",
    label: "AI",
    items: [
      { id: "models", label: "Models", icon: Cpu },
      { id: "persona", label: "Persona", icon: Sparkles },
      { id: "memory", label: "Memory", icon: Brain },
    ],
  },
  {
    id: "system",
    label: "Sistem",
    items: [
      { id: "logs", label: "Logs", icon: ScrollText },
      { id: "settings", label: "Settings", icon: Settings },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
