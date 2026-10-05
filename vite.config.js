import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: "frontend",
  plugins: [react()],
  build: { outDir: "../app/static", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      "/evaluate": "http://127.0.0.1:8000",
      "/guard": "http://127.0.0.1:8000",
      "/run": "http://127.0.0.1:8000",
      "/custom-run": "http://127.0.0.1:8000",
      "/simulate": "http://127.0.0.1:8000",
      "/adaptive-run": "http://127.0.0.1:8000",
      "/multi-agent-run": "http://127.0.0.1:8000",
      "/ai": "http://127.0.0.1:8000",
      "/pass": "http://127.0.0.1:8000",
      "/patch": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
