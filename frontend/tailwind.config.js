/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        app: "#070b14",
        panel: "#0c1220",
        card: "#101a2c",
        border: "rgba(148,197,255,0.10)",
        accent: {
          DEFAULT: "#2563eb", // blue-600
          light: "#38bdf8",   // sky-400
          soft: "#1e3a8a",    // blue-900
        },
      },
      borderRadius: {
        xl2: "1rem",
      },
      backgroundImage: {
        "accent-gradient": "linear-gradient(90deg, #2563eb 0%, #06b6d4 100%)",
        "hero-gradient":
          "linear-gradient(135deg, #102341 0%, #0a1220 55%, #062033 100%)",
      },
    },
  },
  plugins: [],
};
