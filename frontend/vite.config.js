import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built SPA is served by Django: `frontend/dist` is in STATICFILES_DIRS,
// so assets land under /static/. In dev we keep the default base and proxy
// API/media requests to Django so the browser only ever talks same-origin
// (no CORS setup needed).
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/static/" : "/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
    },
  },
}));