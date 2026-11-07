import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "");
  const api = env.DEV_PROXY_API || "http://localhost:8000";
  const voice = env.DEV_PROXY_VOICE || "http://localhost:8002";
  return {
    plugins: [react()],
    server: {
      port: 5174,
      proxy: {
        "/api/v1/voice": { target: voice, changeOrigin: true, rewrite: (p: string) => p.replace(/^\/api\/v1\/voice/, "/voice") },
        "/api": { target: api, changeOrigin: true },
        "/ws": { target: api.replace(/^http/, "ws"), ws: true }
      }
    }
  };
});
