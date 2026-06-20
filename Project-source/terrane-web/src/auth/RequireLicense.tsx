/** License 守卫 —— 锁定态渲染 LockedPage（引导去后台激活），激活态放行子树。
 *  持续轮询：后端检测吊销/删除会重新锁定，前端轮询到 !unlocked 即落回锁定页。 */

import { useQuery } from "@tanstack/react-query";
import { Outlet } from "react-router";

import { getLicenseStatus } from "@/lib/license";
import { LockedPage } from "@/pages/LockedPage";

export function RequireLicense() {
  const { data: status } = useQuery({
    queryKey: ["license"],
    queryFn: getLicenseStatus,
    refetchInterval: 8_000,
  });
  // 首次未知态放行（避免闪烁）；一旦确认未解锁 → 锁定页。
  if (status && !status.unlocked) {
    return <LockedPage />;
  }
  return <Outlet />;
}
