/** License 守卫 —— 包住激活后的所有区域（登录/管理控制台）。
 *  持续轮询 License 状态：后端检测到吊销/删除会重新锁定，前端轮询到 !unlocked 即踢回激活页。
 *  与 ActivatePage 共用 ["license"] 查询缓存，激活/吊销双向近即时反映。 */

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
    // 开源版（required===false）旁路门控：不再需要轮询吊销/删除。
    refetchInterval: (query) => (query.state.data?.required === false ? false : 8_000),
  });
  // 开源版：门控关闭 → 立即放行，永不重定向到激活页。
  if (card?.required === false) {
    return <Outlet />;
  }
  // 商业版（required 为 true 或加载中未定义）：保持原守卫——确认未解锁 → 回激活页。
  if (card && !card.unlocked) {
    return <Navigate to={`/${seg}/activate`} replace />;
  }
  return <Outlet />;
}
