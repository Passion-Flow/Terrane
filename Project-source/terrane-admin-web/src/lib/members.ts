/** Members (frontend users) list API (/admin-api/v1/members) — read-only, page-number pagination, search + status filter. */

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { request } from "@/lib/api";

export interface MemberItem {
  id: string;
  email: string;
  username: string | null;
  status: string;
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  role: string;
  twofa_enabled: boolean;
  email_verified: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

export interface MemberPage {
  items: MemberItem[];
  total: number;
  page: number;
  page_size: number;
}

export const MEMBER_PAGE_SIZE = 12;

export interface CreateMemberInput {
  email: string;
  username?: string;
  password?: string;
  workspace_id: string;
  role: string;
}

export function createMember(
  input: CreateMemberInput,
): Promise<{ id: string; email: string; generated_password: string | null }> {
  return request("/admin-api/v1/members", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateMember(id: string, input: { username?: string | null; status?: string }): Promise<unknown> {
  return request(`/admin-api/v1/members/${id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function resetMemberPassword(id: string): Promise<{ generated_password: string }> {
  return request(`/admin-api/v1/members/${id}/reset-password`, { method: "POST", credentials: "include" });
}

export function deleteMember(id: string): Promise<unknown> {
  return request(`/admin-api/v1/members/${id}`, { method: "DELETE", credentials: "include" });
}

export interface MemberFilters {
  q?: string;
  status?: string;
  workspace_id?: string;
}

export function useMembers(
  filters: MemberFilters, page: number, pageSize = MEMBER_PAGE_SIZE,
): UseQueryResult<MemberPage, unknown> {
  return useQuery({
    queryKey: ["members", filters, page, pageSize],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (filters.q) params.set("q", filters.q);
      if (filters.status) params.set("status", filters.status);
      if (filters.workspace_id) params.set("workspace_id", filters.workspace_id);
      return request<MemberPage>(`/admin-api/v1/members?${params}`, { credentials: "include" });
    },
    placeholderData: keepPreviousData,
  });
}
