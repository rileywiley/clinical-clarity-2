/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Cookie-based auth — proxy keeps the frontend on the same origin in dev so
      // the session cookie is sent without CORS gymnastics. Override the target
      // via VITE_API_TARGET when the backend isn't on the default port (useful
      // for E2E smoke runs that pick a non-conflicting port).
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // Playwright owns the e2e dir; keep vitest out so they don't both pick up
    // the .spec files there (vitest defaults match **/*.spec.{ts,tsx}).
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
});
