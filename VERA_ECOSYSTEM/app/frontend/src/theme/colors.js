/**
 * theme/colors.js — VERA Design System Tokens
 *
 * Product: VERA (Enterprise Network Intelligence Platform)
 * Direction: Futuristic Minimalist Geometric Dark Interface
 * Primary Palette: Electric Blue (#176BFF) + Cyan (#54D6FF) + Deep Navy (#071426)
 */

export const colors = {
  // Base Canvas & Surfaces
  app: "#071426",          // Deep Navy (Base application background)
  surface: "#0D2340",      // Navy Surface (Elevated cards, panels, modals)
  surfaceHover: "#122C4F", // Navy Subtle (Hover state)
  border: "#1C3B66",       // Navy Border hairline divider

  // VERA Brand Accents
  electric: "#176BFF",     // Electric Blue (Primary CTA, intelligence core)
  cyan: "#54D6FF",         // Cyan Accent (Vector links, highlights, glows)
  ice: "#EAF2FF",          // Ice White (Primary high-contrast headings & data)
  steel: "#52657D",        // Steel Gray (Muted metadata & secondary labels)

  // Typography
  text: {
    primary: "#EAF2FF",    // Ice White
    secondary: "#8CA0B8",  // Steel Gray (Contrast ratio > 6.2:1 against #071426)
    muted: "#52657D",
  },

  // Semantic & Network Statuses (WCAG 2.2 Compliant)
  healthy: "#22C55E",      // Link UP, normal CPU/RAM, verified RIB
  warning: "#F59E0B",      // Flapping, latency threshold, high utilization
  critical: "#EF4444",     // Link DOWN, unreachable, BGP session dead
  info: "#176BFF",         // Scheduled discovery, sync ongoing
  unknown: "#64748B",      // Unmonitored, pending enrollment

  // Backward-compatibility aliases for legacy component classes
  primary: "#176BFF",
  sakura: "#54D6FF",       // Aliased to Cyan Accent
  purple: "#176BFF",       // Aliased to Electric Blue
  blue: "#176BFF",
  success: "#22C55E",
  danger: "#EF4444",
};

export default colors;
