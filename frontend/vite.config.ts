import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Em dev, a API (uvicorn :8000) atende só as chamadas JSON; navegação de página
// em /laudos cai no index.html do Vite — mesma negociação por Accept do backend.
const API = process.env.API_URL || "http://127.0.0.1:8000";
const soJson = (req: { headers: Record<string, string | string[] | undefined> }) =>
  String(req.headers.accept || "").includes("text/html") ? "/index.html" : undefined;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/laudos": { target: API, bypass: soJson },
      "/health": { target: API },
    },
  },
});
