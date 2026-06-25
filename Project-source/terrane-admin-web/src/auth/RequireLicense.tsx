/** License guard — wraps every post-activation area (login / management console).
 *  Continuously polls License status: when the backend detects revocation/deletion it re-locks, and the
 *  frontend kicks back to the activation page as soon as it polls !unlocked.
 *  Shares the ["license"] query cache with ActivatePage, so activation/revocation are reflected near-instantly in both directions. */

import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, useParams } from "react-router";

import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { getLicenseCard } from "@/lib/license";

export function RequireLicense() {
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const { data: card } = useQuery({
    queryKey: ["license"],
    queryFn: getLicenseCard,
    // Open-source edition (required===false) bypasses gating: no longer needs to poll for revocation/deletion.
    refetchInterval: (query) => (query.state.data?.required === false ? false : 8_000),
  });
  // Open-source edition: gating disabled → allow through immediately, never redirect to the activation page.
  if (card?.required === false) {
    return <Outlet />;
  }
  // Commercial edition (required is true or undefined while loading): keep the original guard — confirmed not unlocked → back to the activation page.
  if (card && !card.unlocked) {
    return <Navigate to={`/${seg}/activate`} replace />;
  }
  return <Outlet />;
}
