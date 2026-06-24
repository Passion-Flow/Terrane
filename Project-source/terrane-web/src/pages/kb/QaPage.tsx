/** 问答子页 —— 复用 KbChat（库范围 RAG 问答）。 */

import { useTranslation } from "react-i18next";

import { KbChat } from "@/components/KbChat";
import { useKb } from "@/components/KbLayout";

export function QaPage() {
  const { t } = useTranslation();
  const { id } = useKb();
  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kbNav.qa")}</h1>
        <p className="mt-1 text-sm text-ink-secondary">{t("kbPages.qaSubtitle")}</p>
        <div className="mt-6"><KbChat kbId={id} /></div>
      </div>
    </div>
  );
}
