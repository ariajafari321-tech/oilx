import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained HTML file: JS, CSS and fonts inlined. No CDN, no server-side
// assets, so the same file works from `oilx serve`, from GitHub Pages, or offline.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  base: "./",
  build: { target: "es2020", assetsInlineLimit: 100000000, chunkSizeWarningLimit: 4000 },
});
