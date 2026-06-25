/** fetch wrapper — normalizes the error envelope ({code,message,details,request_id});
 *  the frontend resolves i18n by code. */
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
    /* Non-JSON responses are handled by status code */
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
