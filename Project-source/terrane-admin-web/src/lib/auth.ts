/** Admin console auth API (admin-api/v1/auth + me).
 *  Cookie session: every request carries credentials:"include" (HttpOnly cookie terrane_admin_session);
 *  reuses lib/api's request (errors normalized to ApiError; the frontend localizes by code). */

import { request } from "@/lib/api";

/** Currently logged-in admin (GET /me and a successful login return the same shape). */
export interface AdminUser {
  id: string;
  email: string;
  username: string;
  role: string;
  avatar: string | null;
  twofa_enabled: boolean;
  /** Forced first-login password change: the factory super-admin password equals the email; the console is blocked until it is changed. */
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
  /** 2FA code (sent back with the form only after receiving AUTH_2FA_REQUIRED). */
  code?: string;
}

/** Login — a successful 200 returns user info and the backend sets the session cookie. */
export function login(input: LoginInput): Promise<AdminUser> {
  return request<AdminUser>("/admin-api/v1/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** Passively restore the session — fetch the current user with the cookie; throws ApiError("AUTH_REQUIRED") if not logged in. */
export function fetchMe(): Promise<AdminUser> {
  return request<AdminUser>("/admin-api/v1/me", { credentials: "include" });
}

/** Logout — the backend clears the cookie and the server-side session. */
export function logout(): Promise<void> {
  return request<void>("/admin-api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
  });
}

/** Change password (entry point for the forced first-login change) — on success the backend rotates the session and issues a new cookie, returning the updated user. */
export function changePassword(input: ChangePasswordInput): Promise<AdminUser> {
  return request<AdminUser>("/admin-api/v1/auth/change-password", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}
