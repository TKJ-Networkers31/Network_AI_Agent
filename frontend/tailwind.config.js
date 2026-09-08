/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        app: "#0b0a14",
        panel: "#12111f",
        card: "#181628",
        border: "rgba(255,255,255,0.08)",
        accent: {
          DEFAULT: "#7c6bfb",
          light: "#9b6bff",
          soft: "#4c3fb0",
        },
      },
      borderRadius: {
        xl2: "1rem",
      },
      backgroundImage: {
        "accent-gradient": "linear-gradient(90deg, #6d5ef8 0%, #a78bfa 100%)",
        "hero-gradient": "linear-gradient(135deg, #241f45 0%, #120f24 60%, #0b1a12 100%)",
      },
    },
  },
  plugins: [],
};
