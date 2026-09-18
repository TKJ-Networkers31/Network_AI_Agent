/** @type {import('tailwindcss').Config} */
import { colors } from "./src/theme/colors.js";
import { radius } from "./src/theme/radius.js";
import { typography } from "./src/theme/typography.js";

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        app: colors.app,
        surface: colors.surface,
        "surface-hover": colors.surfaceHover,
        // kept for any file not yet migrated off the old token names
        panel: colors.surface,
        card: colors.surface,
        border: colors.border,
        accent: {
          DEFAULT: colors.primary, // violet
          light: colors.cyan,
          soft: colors.primary,
        },
        sakura: {
          DEFAULT: colors.sakura,
          soft: "rgba(244,114,182,0.12)",
        },
        cyan: {
          DEFAULT: colors.cyan,
        },
        success: colors.success,
        danger: colors.danger,
        warning: colors.warning,
        "text-primary": colors.text.primary,
        "text-secondary": colors.text.secondary,
      },
      fontFamily: {
        sans: [typography.fontFamily],
      },
      fontSize: {
        hero: [typography.scale.hero.size, { lineHeight: typography.scale.hero.lineHeight }],
        h1: [typography.scale.h1.size, { lineHeight: typography.scale.h1.lineHeight }],
        h2: [typography.scale.h2.size, { lineHeight: typography.scale.h2.lineHeight }],
        body: [typography.scale.body.size, { lineHeight: typography.scale.body.lineHeight }],
        caption: [typography.scale.caption.size, { lineHeight: typography.scale.caption.lineHeight }],
      },
      borderRadius: {
        control: radius.control,
        card: radius.card,
        xl2: radius.card, // legacy alias used across existing components
        pill: radius.pill,
      },
      boxShadow: {
        card: "0 8px 30px -12px rgba(0,0,0,0.45)",
        floating: "0 20px 60px -20px rgba(0,0,0,0.6)",
        "sakura-glow": "0 0 40px -8px rgba(244,114,182,0.35)",
        "violet-glow": "0 0 40px -8px rgba(159,122,234,0.35)",
      },
      backgroundImage: {
        "sakura-gradient": "linear-gradient(135deg, #F472B6 0%, #9F7AEA 100%)",
        "accent-gradient": "linear-gradient(90deg, #9F7AEA 0%, #60A5FA 100%)",
        "hero-gradient":
          "radial-gradient(60% 60% at 50% 40%, rgba(159,122,234,0.25) 0%, rgba(7,7,20,0) 70%)",
        "core-glow":
          "radial-gradient(circle at 50% 50%, #F472B6 0%, #9F7AEA 55%, rgba(159,122,234,0) 75%)",
      },
      maxWidth: {
        shell: "1600px",
        content: "1100px",
      },
      transitionDuration: {
        DEFAULT: "200ms",
      },
    },
  },
  plugins: [],
};