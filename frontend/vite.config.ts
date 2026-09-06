import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const packageJson = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf8")) as { version: string };

export default defineConfig(({ mode }) => {
  const aliases: Record<string, string> = mode === "webdriver"
    ? {
        "@airbench/tauri-invoke": resolve(__dirname, "src/tauriInvoke.webdriver.ts"),
      }
    : {
        "@airbench/tauri-invoke": resolve(__dirname, "src/tauriInvoke.ts"),
        "@wdio/tauri-plugin": resolve(__dirname, "src/wdio-production-empty.ts"),
      };

  return {
    plugins: [react()],
    clearScreen: false,
    define: { __AIRBENCH_VERSION__: JSON.stringify(packageJson.version) },
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
