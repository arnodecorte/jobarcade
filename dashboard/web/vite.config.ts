import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds into the folder the Python server already serves (dashboard/static).
// emptyOutDir:false preserves draft.html, database.html, their JS, and the
// sprite asset; assetsDir:"app" keeps built JS/CSS out of the existing assets/.
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
