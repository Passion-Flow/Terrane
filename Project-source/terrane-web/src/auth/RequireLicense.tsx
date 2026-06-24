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
    // 开源版（required===false）旁路门控：不再需要轮询吊销/删除。
    refetchInterval: (query) => (query.state.data?.required === false ? false : 8_000),
  });
  // 开源版：门控关闭 → 立即放行，永不触达 LockedPage。
  if (status?.required === false) {
    return <Outlet />;
  }
  // 商业版（required 为 true 或加载中未定义）：保持原守卫——确认未解锁 → 锁定页。
  if (status && !status.unlocked) {
    return <LockedPage />;
  }
  return <Outlet />;
}
