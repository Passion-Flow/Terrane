/** fetch 封装 — 错误信封归一化（{code,message,details,request_id}），前端按 code 走 i18n。 */
import { apiBase } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public requestId: string = "",
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${apiBase()}${path}`, init);
  } catch {
    throw new ApiError("NETWORK_ERROR", "Network request failed.", 0);
  }
  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    /* 非 JSON 响应按状态码处理 */
  }
  if (!resp.ok) {
    const err = (body ?? {}) as {
      code?: string; message?: string; request_id?: string; details?: Record<string, unknown>;
    };
    throw new ApiError(
      err.code ?? "SYSTEM_HTTP_ERROR",
      err.message ?? resp.statusText,
      resp.status,
      err.request_id ?? "",
      err.details ?? {},
    );
  }
  return body as T;
}
