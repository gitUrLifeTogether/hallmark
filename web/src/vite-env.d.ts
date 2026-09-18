/// <reference types="vite/client" />

/* Typed build-time configuration.
 *
 * Only the gateway address is read this way. The API is reached through the dev server's
 * proxy instead, so the deployment's address never enters the bundle.
 */
interface ImportMetaEnv {
  readonly VITE_GATEWAY_WS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
