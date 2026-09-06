/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AIRBENCH_WDIO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __AIRBENCH_VERSION__: string;
