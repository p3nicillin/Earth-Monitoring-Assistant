import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { viteStaticCopy } from "vite-plugin-static-copy";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    viteStaticCopy({
      targets: [
        {
          src: "node_modules/cesium/Build/Cesium/{Workers,ThirdParty,Assets,Widgets}/**/*",
          dest: "cesium",
          rename: { stripBase: 4 },
        },
      ],
    }),
  ],
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesium/"),
  },
  // Cesium is already native ESM. Vite 8's dependency pre-bundler can emit an
  // invalid monolithic development chunk for it, while direct ESM serving and
  // the production build both work correctly.
  optimizeDeps: {
    exclude: ["cesium"],
    include: ["bitmap-sdf", "draco3d", "grapheme-splitter", "lerc", "mersenne-twister", "nosleep.js", "protobufjs", "urijs"],
  },
  server: {
    port: 5173,
  },
  preview: {
    port: 4173,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
