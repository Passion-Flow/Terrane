/** 记忆 API（前台 /api/v1/memories，per-user）。 */

import { request } from "@/lib/api";

export interface Memory { id: string; content: string; kind: string; source: string; created_at: string | null }
export interface MemoryHit { id: string; content: string; kind: string; score: number }

const opt = (method: string, body?: unknown): RequestInit => ({
  method, credentials: "include",
  headers: body ? { "Content-Type": "application/json" } : {},
  ...(body ? { body: JSON.stringify(body) } : {}),
});

export const listMemories = () =>
  request<{ items: Memory[] }>("/api/v1/memories", { credentials: "include" });

export const addMemory = (content: string, kind: "fact" | "preference" | "event" = "fact") =>
  request<Memory>("/api/v1/memories", opt("POST", { content, kind }));

export const recallMemories = (query: string) =>
  request<{ hits: MemoryHit[]; total: number }>("/api/v1/memories/recall", opt("POST", { query }));

export const deleteMemory = (id: string) =>
  request<{ ok: boolean }>(`/api/v1/memories/${id}`, opt("DELETE"));

export const getMemorySettings = () =>
  request<{ auto: boolean }>("/api/v1/memories/settings", { credentials: "include" });

export const setMemorySettings = (auto: boolean) =>
  request<{ auto: boolean }>("/api/v1/memories/settings", opt("PUT", { auto }));
