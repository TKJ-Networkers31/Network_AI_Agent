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

        // VERA Canonical Brand Tokens
        vera: {
          navy: colors.app,
          surface: colors.surface,
          subtle: colors.surfaceHover,
          border: colors.border,
          blue: colors.electric,
          cyan: colors.cyan,
          ice: colors.ice,
          steel: colors.steel,
        },

        // Status Semantics
        healthy: colors.healthy,
        warning: colors.warning,
        critical: colors.critical,
        info: colors.info,
        unknown: colors.unknown,

        // Backward-compatibility aliases
        accent: {
          DEFAULT: colors.electric,
          light: colors.cyan,
          soft: "rgba(84, 214, 255, 0.15)",
        },
        sakura: {
          DEFAULT: colors.cyan,
          soft: "rgba(84, 214, 255, 0.12)",
        },
        cyan: {
          DEFAULT: colors.cyan,
        },
        purple: {
          DEFAULT: colors.electric,
          soft: "rgba(23, 107, 255, 0.15)",
        },
        success: colors.healthy,
        danger: colors.critical,
        "text-primary": colors.text.primary,
        "text-secondary": colors.text.secondary,
      },
      fontFamily: {
        sans: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "'Fira Code'", "ui-monospace", "monospace"],
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
        card: "0 4px 20px -2px rgba(0, 0, 0, 0.5), 0 0 0 1px #1C3B66",
        floating: "0 16px 48px -8px rgba(0, 0, 0, 0.7), 0 0 0 1px #1C3B66",
        "vera-glow": "0 0 24px -2px rgba(23, 107, 255, 0.4)",
        "cyan-glow": "0 0 20px -2px rgba(84, 214, 255, 0.4)",
      },
      backgroundImage: {
        "vera-gradient": "linear-gradient(135deg, #54D6FF 0%, #176BFF 100%)",
        "accent-gradient": "linear-gradient(90deg, #54D6FF 0%, #176BFF 100%)",
        "tech-gradient": "linear-gradient(135deg, #071426 0%, #0D2340 50%, #122C4F 100%)",
        "hero-gradient":
          "radial-gradient(60% 60% at 50% 40%, rgba(23, 107, 255, 0.15) 0%, rgba(84, 214, 255, 0.05) 50%, rgba(7, 20, 38, 0) 80%)",
        "core-glow":
          "radial-gradient(circle at 50% 50%, #54D6FF 0%, #176BFF 55%, rgba(23, 107, 255, 0) 75%)",
        // Legacy gradient aliases
        "sakura-gradient": "linear-gradient(135deg, #54D6FF 0%, #176BFF 100%)",
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
