import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds into the folder the Python server already serves (dashboard/static).
// emptyOutDir:false preserves the hand-maintained assets/ (Dice sprite etc.);
// assetsDir:"app" keeps built JS/CSS in app/, which the "prebuild" npm script
// clears so stale hashed bundles never accumulate.
export default defineConfig({
  base: "/",
  plugins: [react()],
  build: {
    outDir: "../static",
    emptyOutDir: false,
    assetsDir: "app",
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/applications": "http://127.0.0.1:8765",
    },
  },
});
