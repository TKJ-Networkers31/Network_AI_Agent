/**
 * shared/iconRegistry.js — registry ikon bersama (nama string -> komponen lucide).
 *
 * Sengaja di luar components/cockpit supaya bisa dipakai Cockpit, Settings,
 * Tool Manager, dan Marketplace tanpa saling bergantung.
 *
 * - resolveIcon(name, extra?)  : `extra` = registry lokal milik pemanggil (menimpa bawaan)
 * - registerIcons({ nama: Komponen }) : perluas registry global (mis. dari plugin/marketplace)
 * - Nama tak dikenal jatuh ke ikon "wrench".
 */

import {
  Terminal,
  Globe,
  Folder,
  History,
  Eye,
  Wrench,
  Cpu,
  Plug,
  Brain,
  Mic,
  Network,
  Container,
  Cable,
} from "lucide-react";

const registry = {
  terminal: Terminal,
  globe: Globe,
  folder: Folder,
  history: History,
  eye: Eye,
  wrench: Wrench,
  cpu: Cpu,
  plug: Plug,
  brain: Brain,
  mic: Mic,
  network: Network,
  container: Container,
  cable: Cable,
};

export function registerIcons(map) {
  if (!map || typeof map !== "object") return;
  for (const [name, component] of Object.entries(map)) {
    if (component) registry[String(name).toLowerCase()] = component;
  }
}

export function hasIcon(name) {
  return String(name || "").toLowerCase() in registry;
}

export function resolveIcon(name, extra) {
  const key = String(name || "").toLowerCase();
  return (extra && extra[key]) || registry[key] || registry.wrench;
}

export default registry;
