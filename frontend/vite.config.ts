import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // API_URL lets a second copy (e.g. a test instance) point at a different backend.
    proxy: { "/api": process.env.API_URL ?? "http://127.0.0.1:8000" },
  },
});
