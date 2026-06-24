/** 前台 License 状态只读（03-api.md：锁定态例外路由 /api/v1/license/status）。
 *  前台无激活权——仅轮询状态，激活动作在管理后台。 */
import { request } from "@/lib/api";

export interface LicenseStatus {
  status: "active" | "expiring" | "expired" | "revoked" | "binding_mismatch" | "invalid_signature" | "locked";
  /** 门控是否启用：开源版后端返回 false → 前端完全解锁（无锁定页/无激活徽章）。
   *  缺省（旧后端/加载中未定义）按商业模式处理，保持原守卫行为。 */
  required?: boolean;
  unlocked: boolean;
  active_until: string | null;
  days_left: number | null;
}

interface Envelope {
  data: LicenseStatus;
  request_id: string;
}

export function getLicenseStatus(): Promise<LicenseStatus> {
  return request<Envelope>("/api/v1/license/status").then((r) => r.data);
}
