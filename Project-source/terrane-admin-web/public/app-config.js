// 运行时注入配置（部署期可覆盖，不进构建产物）。空 apiBase = 同源（dev 走 vite 代理）。
window.__APP_CONFIG__ = { apiBase: "" };
