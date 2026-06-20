/** 初始化向导 API（/admin-api/v1/wizard）— 仅超管可操作。
 *  步骤：License→超管→邮件→Branding→完成。配置写平台库 terrane_main。 */

import { request } from "@/lib/api";

export type StepStatus = "done" | "current" | "pending";

export interface WizardStep {
  key: "license" | "super_admin" | "email" | "branding";
  status: StepStatus;
}

export type Encryption = "auto" | "ssl" | "starttls" | "none";

export interface EmailState {
  configured: boolean;
  host: string;
  port: number;
  encryption: Encryption;
  username: string;
  from_address: string;
  from_name: string;
  allow_insecure: boolean;
  has_password: boolean;
}

export interface EmailPreset {
  id: string;
  label: string;
  host: string;
  port: number;
  encryption: string;
  from_locked: boolean;
  password_hint: string;
}

export interface BrandingState {
  product_name: string;
  logo_data: string | null;
  login_logo: string | null;
  favicon: string | null;
  accent_color: string;
  login_subtitle: string | null;
  support_url: string | null;
  enabled: boolean;
}

export interface WizardState {
  completed: boolean;
  steps: WizardStep[];
  email: EmailState;
  branding: BrandingState;
  email_presets: EmailPreset[];
}

export interface EmailConfigInput {
  host: string;
  port: number;
  encryption: Encryption;
  username: string;
  password: string;
  from_address: string;
  from_name: string;
  allow_insecure: boolean;
}

export interface BrandingInput {
  product_name: string;
  logo_data: string | null;
  login_logo?: string | null;
  favicon?: string | null;
  accent_color: string;
  login_subtitle: string | null;
  support_url: string | null;
}

const opts = (body?: unknown): RequestInit => ({
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  ...(body ? { body: JSON.stringify(body) } : {}),
});

export function getWizard(): Promise<WizardState> {
  return request<WizardState>("/admin-api/v1/wizard", { credentials: "include" });
}

export function saveEmail(input: EmailConfigInput): Promise<unknown> {
  return request("/admin-api/v1/wizard/email", opts(input));
}

export function testEmail(to: string): Promise<unknown> {
  return request("/admin-api/v1/wizard/email/test", opts({ to }));
}

export function saveBranding(input: BrandingInput): Promise<unknown> {
  return request("/admin-api/v1/wizard/branding", opts(input));
}

export function completeWizard(): Promise<unknown> {
  return request("/admin-api/v1/wizard/complete", opts());
}
