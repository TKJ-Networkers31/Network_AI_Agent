/**
 * cockpit/tokens.js — token visual "Arctic Tech Blue" untuk cockpit.
 * SCOPED: dipasang sebagai CSS variable di root <WorkspaceCockpit>, bukan di
 * tailwind.config.js / theme/*, jadi palet halaman lain tidak tersentuh.
 * Pemakaian: bg-[color:var(--ck-surface)], text-[color:var(--ck-muted)], dst.
 */

export const COCKPIT_VARS = Object.freeze({
  "--ck-bg": "#0A1220",
  "--ck-surface": "#0F1A2E",
  "--ck-surface-2": "#15243B",
  "--ck-border": "rgba(125, 170, 220, 0.16)",
  "--ck-border-strong": "rgba(125, 170, 220, 0.32)",
  "--ck-accent": "#38BDF8",
  "--ck-accent-soft": "rgba(56, 189, 248, 0.12)",
  "--ck-text": "#E6EEF8",
  "--ck-muted": "#8FA3BD",
  "--ck-ok": "#34D399",
  "--ck-warn": "#FBBF24",
  "--ck-err": "#F87171",
});

export default COCKPIT_VARS;
