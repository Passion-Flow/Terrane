/** 运行时注入配置（public/app-config.js）——入口零硬编码 endpoint。 */
declare global {
  interface Window {
    __APP_CONFIG__?: { apiBase?: string };
  }
}
export function apiBase(): string {
  return window.__APP_CONFIG__?.apiBase ?? "";
}
