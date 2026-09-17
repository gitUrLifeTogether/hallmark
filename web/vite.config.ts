import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    server: {
      // Bind both stacks: on Windows, Vite otherwise listens on [::1] only and
      // http://localhost:5173 fails wherever it resolves to IPv4 first.
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy: {
        // The console calls a relative /api path and the dev server forwards it. This
        // keeps the deployment's address out of the bundle, and means no cross-origin
        // preflight, which the emulated API gateway would otherwise have to answer.
        // The target changes whenever the stack is recreated, so it is read from the
        // environment that the deploy writes rather than hardcoded.
        "/api": {
          target: env.VITE_API_TARGET || "http://localhost:4566",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
