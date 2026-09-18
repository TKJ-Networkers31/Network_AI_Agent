/**
 * theme/typography.js — type scale (Inter, weights 300–700).
 * Line-height stays loose/premium per spec — never tighten below these.
 */

export const typography = {
  fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
  scale: {
    hero: { size: "2.25rem", lineHeight: "1.25", weight: 600 },   // 36px
    h1: { size: "1.75rem", lineHeight: "1.3", weight: 600 },      // 28px
    h2: { size: "1.375rem", lineHeight: "1.35", weight: 600 },    // 22px
    body: { size: "0.9375rem", lineHeight: "1.65", weight: 400 }, // 15px
    caption: { size: "0.8125rem", lineHeight: "1.5", weight: 500 }, // 13px
  },
};

export default typography;
