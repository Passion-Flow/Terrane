/** Admin operators (System Users) API (/admin-api/v1/operators, admin database terrane_admin).
 *  Permission platform.user.* (super_admin writes, admin is read-only). Page-number pagination + email/username search + status filter. */

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { request } from "@/lib/api";

export type OperatorRole = "super_admin" | "admin" | "auditor";

export interface OperatorItem {
  id: string;
  email: string;
  username: string;
  role: OperatorRole;
  status: "active" | "disabled";
  twofa_enabled: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

export interface OperatorPage {
  items: OperatorItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface OperatorFilters {
  q?: string;
  status?: string;
}

export const OPERATOR_PAGE_SIZE = 12;

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  ...(body ? { body: JSON.stringify(body) } : {}),
});

export function createOperator(input: {
  email: string; username: string; password?: string; role: OperatorRole;
}): Promise<{ id: string; email: string; generated_password: string | null }> {
  return request("/admin-api/v1/operators", json("POST", input));
}

export function updateOperator(id: string, input: {
  username?: string | null; role?: OperatorRole; status?: "active" | "disabled";
}): Promise<unknown> {
  return request(`/admin-api/v1/operators/${id}`, json("PATCH", input));
}

export function resetOperatorPassword(id: string): Promise<{ generated_password: string }> {
  return request(`/admin-api/v1/operators/${id}/reset-password`, json("POST"));
}

export function deleteOperator(id: string): Promise<unknown> {
  return request(`/admin-api/v1/operators/${id}`, json("DELETE"));
}

export function useOperators(
  filters: OperatorFilters, page: number, pageSize = OPERATOR_PAGE_SIZE,
): UseQueryResult<OperatorPage, unknown> {
  return useQuery({
    queryKey: ["operators", filters, page, pageSize],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (filters.q) params.set("q", filters.q);
      if (filters.status) params.set("status", filters.status);
      return request<OperatorPage>(`/admin-api/v1/operators?${params}`, { credentials: "include" });
    },
    placeholderData: keepPreviousData,
  });
}
