import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the page runs on :5173 and its /api calls go to the driver on :8010 (docker-compose maps it).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8010" } },
  build: { outDir: "dist", emptyOutDir: true },
});
