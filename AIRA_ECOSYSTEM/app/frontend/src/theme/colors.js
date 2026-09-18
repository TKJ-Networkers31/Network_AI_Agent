/**
 * theme/colors.js — AIRA OS design tokens: color.
 *
 * Single source of truth for the palette (UI Redesign Sprint, Worker C).
 * tailwind.config.js reads this file directly — never hardcode a hex
 * value in a component; reference the Tailwind class it produces
 * (bg-app, text-secondary, border-hairline, text-sakura, etc.).
 */

export const colors = {
  app: "#070714",        // background
  surface: "#111122",     // panel / card surface
  surfaceHover: "#1B1B30",

  primary: "#9F7AEA",     // violet
  sakura: "#F472B6",      // primary accent
  cyan: "#60A5FA",        // support accent

  border: "rgba(255,255,255,0.08)",

  text: {
    primary: "#F8FAFC",
    secondary: "#A1A1B5",
  },

  success: "#10B981",
  danger: "#EF4444",
  warning: "#F59E0B",
};

export default colors;
