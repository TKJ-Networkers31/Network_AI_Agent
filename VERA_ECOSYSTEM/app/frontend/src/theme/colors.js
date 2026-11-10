/**
 * theme/colors.js — VERA Design System Tokens
 *
 * Restored Authoritative Palette: Jet Black Cyber Glass
 * Canvas: True OLED Black (#000000)
 * Surface: Ultra-dark subtle glass (#04060c) / Hover (#0a0f1d)
 * Primary Accent: Electric Cyan (#38BDF8)
 * Secondary Accent: Cyber Purple / Neon Violet (#8B5CF6 / #A855F7)
 * Deep Tech Blue: #2563EB
 * High-Contrast Text: Primary (#F8FAFC), Secondary (#94A3B8)
 * Semantic Status: Healthy (#10B981), Warning (#F59E0B), Danger (#EF4444)
 */

export const colors = {
  // Base Canvas & Glass Surfaces
  app: "#000000",          // True Pitch Black / OLED Black
  surface: "#04060c",      // Ultra-dark subtle glass
  surfaceHover: "#0a0f1d", // Hover glass surface
  border: "rgba(255, 255, 255, 0.08)",
  borderGlow: "rgba(56, 189, 248, 0.5)",
  borderPurple: "rgba(168, 85, 247, 0.5)",

  // VERA Brand & Cyber Glass Accents
  primary: "#8B5CF6",       // Cyber Purple / Violet
  sakura: "#38BDF8",        // Tech Electric Cyan / Blue (Primary Brand Accent)
  cyan: "#38BDF8",          // Electric Cyan
  purple: "#A855F7",        // Neon Purple
  blue: "#2563EB",          // Deep Tech Blue
  electric: "#38BDF8",      // Alias for primary electric accent
  ice: "#F8FAFC",           // High-contrast clean text
  steel: "#94A3B8",         // Muted metadata

  // Typography
  text: {
    primary: "#F8FAFC",     // Clean White (Contrast ratio > 15:1 against #000000)
    secondary: "#94A3B8",   // Tech Gray (Contrast ratio > 7:1 against #000000)
    muted: "#64748B",
  },

  // Semantic & Observability Statuses
  success: "#10B981",       // Healthy / UP (Normal operation)
  healthy: "#10B981",       // Healthy alias
  warning: "#F59E0B",       // Warning / Degraded / Latency threshold
  danger: "#EF4444",        // Critical / DOWN / Link severed
  critical: "#EF4444",      // Critical alias
  info: "#38BDF8",          // Info / In-progress
  unknown: "#64748B",       // Unmonitored / Pending
};

export default colors;
