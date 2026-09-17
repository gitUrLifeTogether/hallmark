import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Bind both stacks: on Windows, Vite otherwise listens on [::1] only and
  // http://localhost:5173 fails wherever it resolves to IPv4 first.
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
});
