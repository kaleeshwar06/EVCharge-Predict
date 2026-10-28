import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        configure: (proxy, _options) => {
          proxy.on("proxyReq", (proxyReq) => {
            const token = process.env.API_AUTH_TOKEN;
            if (token) {
              proxyReq.setHeader("Authorization", `Bearer ${token}`);
            }
          });
        },
      },
      "/healthz": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
      "/readyz": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
