/** 后台设置 API（/admin-api/v1/settings）— 向导后随时编辑邮件 / 品牌。
 *  复用向导的 Email/Branding/Preset 类型；邮件 GET 脱敏（不回传密码）。 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { request } from "@/lib/api";
import type { BrandingInput, EmailConfigInput, EmailPreset, EmailState, BrandingState } from "@/lib/wizard";

export interface SettingsState {
  email: EmailState;
  branding: BrandingState;
  email_presets: EmailPreset[];
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  ...(body ? { body: JSON.stringify(body) } : {}),
});

export function getSettings(): Promise<SettingsState> {
  return request<SettingsState>("/admin-api/v1/settings", { credentials: "include" });
}

export function updateEmail(input: EmailConfigInput): Promise<unknown> {
  return request("/admin-api/v1/settings/email", json("PATCH", input));
}

export function testEmail(to: string): Promise<unknown> {
  return request("/admin-api/v1/settings/email/test", json("POST", { to }));
}

export function updateBranding(input: BrandingInput): Promise<unknown> {
  return request("/admin-api/v1/settings/branding", json("PATCH", input));
}

export function useSettings(): UseQueryResult<SettingsState, unknown> {
  return useQuery({ queryKey: ["settings"], queryFn: getSettings });
}

// ── 安全策略（密码规则）──
export interface SecurityPolicy {
  password_min_length: number;
  password_require_char_classes: number;
  login_lock_threshold: number;
  login_lock_seconds: number;
  session_absolute_ttl_seconds: number;
}

export function getSecurity(): Promise<SecurityPolicy> {
  return request<SecurityPolicy>("/admin-api/v1/settings/security", { credentials: "include" });
}

export function updateSecurity(input: SecurityPolicy): Promise<unknown> {
  return request("/admin-api/v1/settings/security", json("PATCH", input));
}

export function useSecurity(): UseQueryResult<SecurityPolicy, unknown> {
  return useQuery({ queryKey: ["settings", "security"], queryFn: getSecurity });
}
