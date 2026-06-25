/** License guard — renders LockedPage when locked (directing users to activate in the admin console),
 *  and renders the child subtree when active.
 *  Continuous polling: when the backend detects revocation/deletion it re-locks, and once the frontend
 *  polls !unlocked it falls back to the lock page. */

import { useQuery } from "@tanstack/react-query";
import { Outlet } from "react-router";

import { getLicenseStatus } from "@/lib/license";
import { LockedPage } from "@/pages/LockedPage";

export function RequireLicense() {
  const { data: status } = useQuery({
    queryKey: ["license"],
    queryFn: getLicenseStatus,
    // Open-source build (required===false) bypasses gating: no need to poll for revocation/deletion.
    refetchInterval: (query) => (query.state.data?.required === false ? false : 8_000),
  });
  // Open-source build: gating disabled → pass through immediately, never reaching LockedPage.
  if (status?.required === false) {
    return <Outlet />;
  }
  // Commercial build (required is true, or undefined while loading): keep the original guard — once confirmed not unlocked → lock page.
  if (status && !status.unlocked) {
    return <LockedPage />;
  }
  return <Outlet />;
}
