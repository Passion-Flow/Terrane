/** Runtime-injected config (public/app-config.js) — no hardcoded endpoint at the entry point. */
declare global {
  interface Window {
    __APP_CONFIG__?: { apiBase?: string };
  }
}
export function apiBase(): string {
  return window.__APP_CONFIG__?.apiBase ?? "";
}
