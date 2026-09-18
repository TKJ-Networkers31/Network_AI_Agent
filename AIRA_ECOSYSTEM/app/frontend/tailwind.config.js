/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        app: "#070714",
        panel: "#111122",
        card: "#151528",
        border: "rgba(255,255,255,0.08)",
        accent: {
          DEFAULT: "#9F7AEA",
          light: "#F472B6",
          soft: "#5B3B78",
        },
        sakura: "#F472B6",
        cyan: "#60A5FA",
      },
      borderRadius: {
        xl2: "1rem",
        panel: "1.25rem",
      },
      backgroundImage: {
        "accent-gradient": "linear-gradient(135deg, #9F7AEA 0%, #F472B6 100%)",
        "hero-gradient": "radial-gradient(circle at 50% 0%, rgba(159,122,234,0.18), transparent 48%), linear-gradient(135deg, #111122 0%, #070714 62%, #180F24 100%)",
      },
      boxShadow: {
        panel: "0 18px 60px rgba(0,0,0,0.28)",
        sakura: "0 0 28px rgba(244,114,182,0.16)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
