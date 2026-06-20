/** 知识图谱（顶级页)—— 选库 → 展示图谱。 */
import { Graph } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { KbGraph } from "@/components/KbGraph";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { listKbs, type Kb } from "@/lib/kb";

export function GraphPage() {
  const { t } = useTranslation();
  const [kbs, setKbs] = useState<Kb[]>([]);
  const [kbId, setKbId] = useState("");
  const load = useCallback(async () => { const it = (await listKbs()).items; setKbs(it); if (it[0] && !kbId) setKbId(it[0].id); }, [kbId]);
  useEffect(() => { void load(); }, [load]);
  return (
    <div className="px-8 py-10">
      <div className="mx-auto max-w-6xl">
        <PageHeader title={t("nav.graph")} subtitle={t("graphPage.subtitle")} back
          actions={kbs.length > 0 ? <Select className="w-56" value={kbId} onChange={setKbId} options={kbs.map((k) => ({ value: k.id, label: k.name }))} /> : undefined} />
        <div className="mt-6">
          {kbs.length === 0 ? (
            <div className="flex flex-col items-center rounded-(--radius-card) border border-dashed border-border bg-surface/30 py-20 text-center">
              <Graph className="size-9 text-ink-faint" /><p className="mt-3 text-sm text-ink-secondary">{t("kb.empty")}</p>
            </div>
          ) : kbId ? <KbGraph kbId={kbId} canEdit /> : null}
        </div>
      </div>
    </div>
  );
}
