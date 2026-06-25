/** Model channels API (/admin-api/v1/channels, admin database terrane_admin) — platform-level LLM/embedding/rerank/web-search backends.
 *  Variant pattern: getProviders() supplies the types for the "New channel" dropdown; each type is configured in a centered modal. The api_key GET is redacted (only has_key). */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { request } from "@/lib/api";

export type ChannelProvider = "openai_compatible" | "anthropic" | "tongyi" | "web_search" | "custom";
export type ChannelKind = "chat" | "embed" | "rerank" | "web_search" | "vl" | "asr" | "tts";

export interface ChannelItem {
  id: string;
  provider: ChannelProvider;
  kind: ChannelKind;
  name: string;
  base_url: string | null;
  model: string | null;
  enabled: boolean;
  has_key: boolean;
  created_at: string | null;
}

export interface ProviderPreset {
  id: ChannelProvider;
  label: string;
  kind: ChannelKind;
  base_url: string;
  needs_model: boolean;
  key_hint: string;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method, credentials: "include",
  headers: { "Content-Type": "application/json" },
  ...(body ? { body: JSON.stringify(body) } : {}),
});

export function getProviders(): Promise<{ providers: ProviderPreset[] }> {
  return request("/admin-api/v1/channels/providers", { credentials: "include" });
}

export function createChannel(input: {
  provider: ChannelProvider; kind: ChannelKind; name: string;
  base_url?: string; api_key?: string; model?: string;
}): Promise<ChannelItem> {
  return request("/admin-api/v1/channels", json("POST", input));
}

export function updateChannel(id: string, input: {
  name?: string; base_url?: string; api_key?: string; model?: string; kind?: ChannelKind; enabled?: boolean;
}): Promise<unknown> {
  return request(`/admin-api/v1/channels/${id}`, json("PATCH", input));
}

export function deleteChannel(id: string): Promise<unknown> {
  return request(`/admin-api/v1/channels/${id}`, json("DELETE"));
}

export function testChannel(id: string): Promise<{ data: { ok: boolean; detail: string } }> {
  return request(`/admin-api/v1/channels/${id}/test`, json("POST"));
}

export function useChannels(): UseQueryResult<{ items: ChannelItem[] }, unknown> {
  return useQuery({
    queryKey: ["channels"],
    queryFn: () => request<{ items: ChannelItem[] }>("/admin-api/v1/channels", { credentials: "include" }),
  });
}

export function useProviders(): UseQueryResult<{ providers: ProviderPreset[] }, unknown> {
  return useQuery({ queryKey: ["channel-providers"], queryFn: getProviders, staleTime: 60 * 60_000 });
}
