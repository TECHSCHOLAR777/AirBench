/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AIRBENCH_WDIO?: string;
  readonly VITE_GEMINI_API_KEYS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __AIRBENCH_VERSION__: string;
