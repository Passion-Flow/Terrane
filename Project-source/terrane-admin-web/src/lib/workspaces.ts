/** Workspaces list API (/admin-api/v1/workspaces) — read-only, page-number pagination, name/slug search. */

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { request } from "@/lib/api";

export interface WorkspaceItem {
  id: string;
  slug: string;
  name: string;
  kind: string;
  status: string;
  member_count: number;
  created_at: string | null;
}

export interface WorkspacePage {
  items: WorkspaceItem[];
  total: number;
  page: number;
  page_size: number;
}

export const WS_PAGE_SIZE = 12;

export function createWorkspace(input: { name: string; kind: string }): Promise<WorkspaceItem> {
  return request<WorkspaceItem>("/admin-api/v1/workspaces", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateWorkspace(id: string, input: { name?: string; status?: string }): Promise<unknown> {
  return request(`/admin-api/v1/workspaces/${id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deleteWorkspace(id: string): Promise<unknown> {
  return request(`/admin-api/v1/workspaces/${id}`, { method: "DELETE", credentials: "include" });
}

export function useWorkspaces(
  q: string, page: number, pageSize = WS_PAGE_SIZE,
): UseQueryResult<WorkspacePage, unknown> {
  return useQuery({
    queryKey: ["workspaces", q, page, pageSize],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (q) params.set("q", q);
      return request<WorkspacePage>(`/admin-api/v1/workspaces?${params}`, { credentials: "include" });
    },
    placeholderData: keepPreviousData,
  });
}
