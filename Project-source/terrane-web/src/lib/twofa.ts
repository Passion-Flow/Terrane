/** 2FA（TOTP）API。 */

import { request } from "@/lib/api";

const opt = (body?: unknown): RequestInit => ({
  method: "POST", credentials: "include",
  headers: body ? { "Content-Type": "application/json" } : {},
  ...(body ? { body: JSON.stringify(body) } : {}),
});

export const twofaBegin = () =>
  request<{ data: { secret: string; uri: string } }>("/api/v1/auth/2fa/begin", opt());

export const twofaEnable = (code: string) =>
  request<{ data: { backup_codes: string[] } }>("/api/v1/auth/2fa/enable", opt({ code }));

export const twofaDisable = (code: string) =>
  request<{ data: { ok: boolean } }>("/api/v1/auth/2fa/disable", opt({ code }));
