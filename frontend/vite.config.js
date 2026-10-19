import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../sbc/static/dashboard",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
  },
  server: { proxy: { "/api": "http://127.0.0.1:8080" } },
});
