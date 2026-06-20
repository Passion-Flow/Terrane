/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const port = Number(env.VITE_DEV_PORT) || 43000;
  const apiTarget = env.VITE_DEV_API_TARGET || "http://localhost:43001";
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: { port, proxy: { "/api": { target: apiTarget, changeOrigin: true } } },
    build: { outDir: "dist" },
    test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], globals: true },
  };
});
