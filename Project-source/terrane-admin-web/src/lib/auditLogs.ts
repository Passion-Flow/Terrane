/** Audit log API (/admin-api/v1/audit-logs) — read-only, page-number pagination.
 *  Append-only table: no write endpoints. A trailing dot on action = prefix match (e.g. 'wizard.'). */

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { request } from "@/lib/api";

export interface AuditLogItem {
  id: string;
  workspace_id: string | null;
  actor_type: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  target_name: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  user_agent: string | null;
  request_id: string | null;
  created_at: string | null;
}

export interface AuditLogPage {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditLogFilters {
  actor?: string;
  action?: string;
  target_type?: string;
  from?: string;
  to?: string;
}

export const AUDIT_PAGE_SIZE = 12;

function buildQuery(filters: AuditLogFilters, page: number, pageSize: number): string {
  const params = new URLSearchParams();
  if (filters.actor) params.set("actor", filters.actor);
  if (filters.action) params.set("action", filters.action);
  if (filters.target_type) params.set("target_type", filters.target_type);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return `?${params.toString()}`;
}

export function fetchAuditLogs(filters: AuditLogFilters, page: number, pageSize: number): Promise<AuditLogPage> {
  return request<AuditLogPage>(`/admin-api/v1/audit-logs${buildQuery(filters, page, pageSize)}`, {
    method: "GET",
    credentials: "include",
  });
}

export function useAuditLogs(
  filters: AuditLogFilters,
  page: number,
  pageSize: number = AUDIT_PAGE_SIZE,
): UseQueryResult<AuditLogPage, unknown> {
  return useQuery({
    queryKey: ["audit-logs", filters, page, pageSize],
    queryFn: () => fetchAuditLogs(filters, page, pageSize),
    placeholderData: keepPreviousData, // Keep the previous page's data while paging to avoid flicker
  });
}
