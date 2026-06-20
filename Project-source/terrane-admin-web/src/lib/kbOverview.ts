/** 后台库总览 API（/admin-api/v1/knowledge-bases，只读元数据)。 */

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { request } from "@/lib/api";

export interface KbOverviewItem {
  id: string;
  name: string;
  slug: string;
  visibility: "private" | "shared" | "workspace";
  status: string;
  workspace_name: string;
  source_count: number;
  created_at: string | null;
}

export interface KbOverviewResp {
  items: KbOverviewItem[];
  total: number;
  page: number;
  page_size: number;
}

export function useKbOverview(params: { page: number; q: string; visibility: string }): UseQueryResult<KbOverviewResp, unknown> {
  const qs = new URLSearchParams({ page: String(params.page), page_size: "20" });
  if (params.q) qs.set("q", params.q);
  if (params.visibility) qs.set("visibility", params.visibility);
  return useQuery({
    queryKey: ["kb-overview", params],
    queryFn: () => request<KbOverviewResp>(`/admin-api/v1/knowledge-bases?${qs}`, { credentials: "include" }),
    placeholderData: keepPreviousData,
  });
}
