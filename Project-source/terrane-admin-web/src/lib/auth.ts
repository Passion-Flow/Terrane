/** 后台管理端鉴权 API（admin-api/v1/auth + me）。
 *  cookie 会话：所有请求带 credentials:"include"（HttpOnly cookie terrane_admin_session）；
 *  复用 lib/api 的 request（错误归一化为 ApiError，前端按 code 走 i18n）。 */

import { request } from "@/lib/api";

/** 当前登录管理员（GET /me 与 login 成功返回同构）。 */
export interface AdminUser {
  id: string;
  email: string;
  username: string;
  role: string;
  avatar: string | null;
  twofa_enabled: boolean;
  /** 首登强制改密：出厂超管密码=邮箱，未改密前不放行控制台。 */
  must_change_password: boolean;
  permissions: string[];
}

export interface ChangePasswordInput {
  current_password: string;
  new_password: string;
}

export interface LoginInput {
  email: string;
  password: string;
  /** 2FA 验证码（仅在收到 AUTH_2FA_REQUIRED 后随表单回传）。 */
  code?: string;
}

/** 登录 —— 成功 200 返回用户信息并由后端设置会话 cookie。 */
export function login(input: LoginInput): Promise<AdminUser> {
  return request<AdminUser>("/admin-api/v1/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** 被动恢复登录态 —— 带 cookie 拉取当前用户；未登录抛 ApiError("AUTH_REQUIRED")。 */
export function fetchMe(): Promise<AdminUser> {
  return request<AdminUser>("/admin-api/v1/me", { credentials: "include" });
}

/** 登出 —— 后端清 cookie + 清服务端会话。 */
export function logout(): Promise<void> {
  return request<void>("/admin-api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
  });
}

/** 改密（首登强制改密入口）—— 成功后端轮换会话并换发新 cookie，返回更新后的用户。 */
export function changePassword(input: ChangePasswordInput): Promise<AdminUser> {
  return request<AdminUser>("/admin-api/v1/auth/change-password", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}
