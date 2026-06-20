/** License 区 API（03-api.md + 阶段①后端契约）。 */
import { request } from "@/lib/api";

export interface LicenseCard {
  status: "active" | "expiring" | "expired" | "revoked" | "binding_mismatch" | "invalid_signature" | "locked";
  unlocked: boolean;
  fingerprint: string;
  license_id_masked: string | null;
  cluster_id_masked: string | null;
  customer: string | null;
  product: string | null;
  subscription: string | null;
  active_from: string | null;
  active_until: string | null;
  days_left: number | null;
  quotas: Record<string, number | null> | null;
  features: string[] | null;
  mode: string | null;
  binding: string | null;
  alg: string | null;
}

interface Envelope {
  data: LicenseCard;
  request_id: string;
}

export function getLicenseCard(): Promise<LicenseCard> {
  return request<Envelope>("/admin-api/v1/license").then((r) => r.data);
}

export function activateLicense(method: "offline" | "online", credential: string): Promise<LicenseCard> {
  return request<Envelope>("/admin-api/v1/license/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ method, credential }),
  }).then((r) => r.data);
}
