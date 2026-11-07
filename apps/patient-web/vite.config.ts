import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { loadEnv, type Plugin } from "vite";
import fs from "node:fs";
import path from "node:path";

// Serves/copies packages/content/assets at /assets/* (games resolve relative asset paths against "/").
function contentAssets(): Plugin {
  const dir = path.resolve(__dirname, "../../packages/content/assets");
  return {
    name: "smaran-content-assets",
    configureServer(server) {
      server.middlewares.use("/assets", (req, res, next) => {
        const f = path.join(dir, decodeURIComponent((req.url ?? "/").split("?")[0]));
        if (f.startsWith(dir) && fs.existsSync(f) && fs.statSync(f).isFile()) {
          res.setHeader("Content-Type", f.endsWith(".svg") ? "image/svg+xml" : "application/octet-stream");
          fs.createReadStream(f).pipe(res);
        } else next();
      });
    },
    // Runs before vite-plugin-pwa's (post) closeBundle, so assets land in the Workbox precache manifest.
    closeBundle() {
      const dist = path.resolve(__dirname, "dist");
      if (fs.existsSync(dist)) fs.cpSync(dir, path.join(dist, "assets"), { recursive: true });
    }
  };
}

// apps/patient-web — offline-first elder PWA (Claude 3 of 6). Port 5173 per
// the shared briefing's monorepo layout.
export default defineConfig(({ mode }) => {
const env = loadEnv(mode, __dirname, "");
const api = env.DEV_PROXY_API || "http://localhost:8000";
const voice = env.DEV_PROXY_VOICE || "http://localhost:8002";
return {
  server: {
    port: 5173,
    // D4/D6: relative API base. /api/v1/voice/* -> services/voice /voice/* (must precede /api).
    proxy: {
      "/api/v1/voice": { target: voice, changeOrigin: true, rewrite: (p: string) => p.replace(/^\/api\/v1\/voice/, "/voice") },
      "/api": { target: api, changeOrigin: true },
      "/ws": { target: api.replace(/^http/, "ws"), ws: true }
    }
  },
  plugins: [
    react(),
    contentAssets(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/*.png"],
      manifest: {
        id: "/",
        name: "SMARAN",
        short_name: "SMARAN",
        description: "Understanding Memory Through Emotion",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: "#F8FAFC",
        theme_color: "#0F766E",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icons/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" }
        ]
      },
      workbox: {
        // App shell + static assets precached so the elder UI launches and a
        // game session can be played with the network fully off. API calls
        // are handled by the sync queue (IndexedDB), not the service worker
        // cache, since GameEvent/EmotionSample writes must queue, not cache.
        globPatterns: ["**/*.{js,css,html,woff2,png,svg}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api/, /^\/ws/]
      },
      devOptions: { enabled: true }
    })
  ],
  resolve: {
    alias: {
      "@": "/src"
    }
  }
};
});
