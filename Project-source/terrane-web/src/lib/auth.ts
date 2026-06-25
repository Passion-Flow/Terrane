/** Frontend user auth API (/api/v1/auth). Cookie session (HttpOnly terrane_session).
 *  Errors resolve i18n by code (lib/api normalizes into ApiError). */

import { request } from "@/lib/api";

export interface AppUser {
  id: string;
  email: string;
  username: string | null;
  avatar: string | null;
  status: string;
  workspace_id: string;
  role: string;
  twofa_enabled: boolean;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface RegisterInput { email: string; password: string; username?: string }
export interface LoginInput { email: string; password: string; code?: string }

export function register(input: RegisterInput): Promise<{ id: string; email: string; status: string }> {
  return request("/api/v1/auth/register", json(input));
}

export function login(input: LoginInput): Promise<AppUser> {
  return request<AppUser>("/api/v1/auth/login", json(input));
}

export function fetchMe(): Promise<AppUser> {
  return request<AppUser>("/api/v1/auth/me", { credentials: "include" });
}

export function updateProfile(input: { username?: string; avatar?: string | null }): Promise<{ data: { ok: boolean } }> {
  return request("/api/v1/auth/profile", {
    method: "PATCH", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}

export function logout(): Promise<void> {
  return request<void>("/api/v1/auth/logout", { method: "POST", credentials: "include" });
}

export function verifyEmail(token: string): Promise<unknown> {
  return request("/api/v1/auth/verify-email", json({ token }));
}

export function requestReset(email: string): Promise<unknown> {
  return request("/api/v1/auth/request-reset", json({ email }));
}

export function resetPassword(token: string, newPassword: string): Promise<unknown> {
  return request("/api/v1/auth/reset-password", json({ token, new_password: newPassword }));
}
