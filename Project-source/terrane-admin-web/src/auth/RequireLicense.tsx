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
    refetchInterval: 8_000, // active 态轮询，捕获吊销/删除/过期
  });
  // 首次加载未知态时放行渲染（避免闪烁）；一旦确认未解锁 → 回激活页。
  if (card && !card.unlocked) {
    return <Navigate to={`/${seg}/activate`} replace />;
  }
  return <Outlet />;
}
