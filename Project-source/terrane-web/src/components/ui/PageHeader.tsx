/** 页面头 —— 可选返回键 + 标题 + 副标题 + 右侧操作位。全前台页统一。 */

import { ArrowLeft } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

export function PageHeader({ title, subtitle, back, actions }: {
  title: string; subtitle?: string; back?: boolean; actions?: ReactNode;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        {back && (
          <button onClick={() => navigate(-1)} className="mb-2 flex items-center gap-1 text-[13px] text-ink-secondary transition hover:text-ink">
            <ArrowLeft className="size-4" /> {t("common.back")}
          </button>
        )}
        <h1 className="text-[26px] font-semibold leading-none tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-2.5 text-sm text-ink-secondary">{subtitle}</p>}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}
