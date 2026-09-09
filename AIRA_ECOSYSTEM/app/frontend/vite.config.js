import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Selama dev, request ke /api diteruskan ke FastAPI (port 8000)
      // supaya tidak perlu urus CORS manual dari sisi kode React.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
