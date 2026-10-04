import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: "frontend",
  plugins: [react()],
  build: { outDir: "../app/static", emptyOutDir: true },
  server: { port: 5173, proxy: { "/run": "http://127.0.0.1:8000", "/patch": "http://127.0.0.1:8000", "/health": "http://127.0.0.1:8000" } },
});
