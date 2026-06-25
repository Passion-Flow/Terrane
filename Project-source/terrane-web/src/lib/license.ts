/** Frontend License status, read-only (03-api.md: locked-state exception route /api/v1/license/status).
 *  The frontend has no activation rights — it only polls status; activation happens in the admin console. */
import { request } from "@/lib/api";

export interface LicenseStatus {
  status: "active" | "expiring" | "expired" | "revoked" | "binding_mismatch" | "invalid_signature" | "locked";
  /** Whether gating is enabled: the open-source backend returns false → frontend is fully unlocked
   *  (no lock page / no activation badge).
   *  When absent (old backend / undefined while loading), treated as commercial mode, preserving the original guard behavior. */
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
