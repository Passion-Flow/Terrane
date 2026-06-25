/** Q&A subpage — reuses KbChat (KB-scoped RAG Q&A). Full-height flex layout; only the message area scrolls internally; responsive across resolutions. */

import { useTranslation } from "react-i18next";

import { KbChat } from "@/components/KbChat";
import { useKb } from "@/components/KbLayout";

export function QaPage() {
  const { t } = useTranslation();
  const { id } = useKb();
  return (
    <div className="flex h-full flex-col px-6 py-6 sm:px-8">
      <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col">
        <div className="shrink-0">
          <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kbNav.qa")}</h1>
          <p className="mt-1 text-sm text-ink-secondary">{t("kbPages.qaSubtitle")}</p>
        </div>
        <div className="mt-5 min-h-0 flex-1">
          <KbChat kbId={id} />
        </div>
      </div>
    </div>
  );
}
