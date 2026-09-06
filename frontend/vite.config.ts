import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const aliases: Record<string, string> = mode === "webdriver"
    ? {}
    : {
        "@wdio/tauri-plugin": resolve(__dirname, "src/wdio-production-empty.ts"),
      };

  return {
    plugins: [react()],
    clearScreen: false,
    resolve: { alias: aliases },
    server: {
      host: "127.0.0.1",
      port: 1420,
      strictPort: true,
      watch: {
        ignored: ["**/src-tauri/**"],
      },
    },
    envPrefix: ["VITE_"],
  };
});
