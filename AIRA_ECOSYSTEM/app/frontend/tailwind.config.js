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
        panel: colors.surface,
        card: colors.surface,
        border: colors.border,
        accent: {
          DEFAULT: colors.sakura,
          light: colors.cyan,
          soft: "rgba(56, 189, 248, 0.15)",
        },
        sakura: {
          DEFAULT: colors.sakura, // Tech Cyan / Electric Blue
          soft: "rgba(56, 189, 248, 0.12)",
        },
        cyan: {
          DEFAULT: colors.cyan,
        },
        purple: {
          DEFAULT: colors.purple,
          soft: "rgba(168, 85, 247, 0.15)",
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
        xl2: radius.card,
        pill: radius.pill,
      },
      boxShadow: {
        card: "0 8px 32px -8px rgba(0,0,0,0.6)",
        floating: "0 20px 60px -15px rgba(0,0,0,0.8)",
        "sakura-glow": "0 0 25px -4px rgba(56, 189, 248, 0.4)",
        "cyan-glow": "0 0 25px -4px rgba(56, 189, 248, 0.45)",
        "violet-glow": "0 0 25px -4px rgba(139, 92, 246, 0.45)",
        "purple-glow": "0 0 25px -4px rgba(168, 85, 247, 0.45)",
      },
      backgroundImage: {
        "sakura-gradient": "linear-gradient(135deg, #38BDF8 0%, #8B5CF6 100%)",
        "accent-gradient": "linear-gradient(90deg, #38BDF8 0%, #8B5CF6 100%)",
        "tech-gradient": "linear-gradient(135deg, #0284C7 0%, #38BDF8 50%, #8B5CF6 100%)",
        "hero-gradient":
          "radial-gradient(60% 60% at 50% 40%, rgba(56, 189, 248, 0.15) 0%, rgba(139, 92, 246, 0.08) 45%, rgba(3, 7, 18, 0) 75%)",
        "core-glow":
          "radial-gradient(circle at 50% 50%, #38BDF8 0%, #8B5CF6 55%, rgba(139, 92, 246, 0) 75%)",
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
