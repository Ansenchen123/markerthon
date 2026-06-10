/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEMO_GOVERNMENT_EMAIL?: string;
  readonly VITE_DEMO_GOVERNMENT_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
