/** 公开品牌（白标）API（/admin-api/v1/branding）— 免登录、锁定态可取。
 *  供 Logo / 登录页 / 标题栏在认证前展示部署方品牌（产品名 / 主题色 / 登录副标题）。 */

import { request } from "@/lib/api";

export interface Branding {
  product_name: string;
  logo_data: string | null;     // 控制台/工作区 Logo
  login_logo: string | null;    // 登录页 Logo
  favicon: string | null;       // 站点 favicon
  accent_color: string;
  login_subtitle: string | null;
  support_url: string | null;
  enabled: boolean;
}

export const DEFAULT_BRANDING: Branding = {
  product_name: "Terrane",
  logo_data: null,
  login_logo: null,
  favicon: null,
  accent_color: "#0f9b8e",
  login_subtitle: null,
  support_url: null,
  enabled: true,
};

export function getBranding(): Promise<Branding> {
  return request<Branding>("/admin-api/v1/branding", { credentials: "include" });
}
