/**
 * theme/shadow.js — elevation scale.
 * Soft shadows only — no glow-heavy card treatments (spec: "Tidak
 * menggunakan glow berlebihan"). The sakura/violet glow is reserved for
 * the hero core asset, the active workspace item, and loading states.
 */

export const shadow = {
  card: "0 8px 30px -12px rgba(0,0,0,0.45)",
  floating: "0 20px 60px -20px rgba(0,0,0,0.6)",
  sakuraGlow: "0 0 40px -8px rgba(244,114,182,0.35)",
  violetGlow: "0 0 40px -8px rgba(159,122,234,0.35)",
};

export default shadow;
