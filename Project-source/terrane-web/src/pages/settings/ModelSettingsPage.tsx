/** Model settings —— the frontend picks, for each purpose (chat / multimodal / embedding / rerank), a model configured in the admin panel (synced from the admin "Model Channels"). */
import { ChatCircleText, Cpu, Image, MagnifyingGlass, Sparkle, type Icon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { getModelPref, getModels, setModelPref, type ModelKind, type ModelOption } from "@/lib/models";

const KINDS: { kind: ModelKind; icon: Icon }[] = [
  { kind: "chat", icon: ChatCircleText },
  { kind: "vl", icon: Image },
  { kind: "embed", icon: Cpu },
  { kind: "rerank", icon: MagnifyingGlass },
];

export function ModelSettingsPage() {
  const { t } = useTranslation();
  const [avail, setAvail] = useState<Record<string, ModelOption[]>>({});
  const [prefs, setPrefs] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    getModels().then((r) => setAvail(r.data || {})).finally(() => setLoaded(true));
    setPrefs(Object.fromEntries(KINDS.map((k) => [k.kind, getModelPref(k.kind)])));
  }, []);

  function pick(kind: ModelKind, model: string) {
    setModelPref(kind, model);
    setPrefs((p) => ({ ...p, [kind]: model }));
  }

  return (
    <div className="px-8 py-10">
      <div className="mx-auto max-w-2xl">
        <PageHeader title={t("nav.modelSettings")} subtitle={t("modelSettings.subtitle")} back />
        <div className="mt-6 space-y-3">
          {KINDS.map(({ kind, icon: Ic }) => {
            const opts = (avail[kind] || []).map((m) => ({ value: m.model, label: m.name, hint: m.model }));
            const def = avail[kind]?.[0]?.model;
            return (
              <div key={kind} className="rounded-(--radius-card) border border-border/70 bg-surface/40 p-5">
                <div className="flex items-center gap-2"><Ic className="size-4.5 text-accent" /><span className="text-sm font-medium text-ink">{t("modelSettings.kindFull." + kind)}</span></div>
                <p className="mt-1 text-[13px] text-ink-secondary">{t("modelSettings.kindHint." + kind)}</p>
                {!loaded ? <div className="mt-3 h-9 w-full animate-pulse rounded-(--radius-control) bg-canvas" />
                  : opts.length === 0 ? <p className="mt-3 rounded-(--radius-control) bg-canvas px-3 py-2 text-[13px] text-ink-faint">{t("modelSettings.noneKind")}</p>
                  : <div className="mt-3"><Select className="w-full" value={prefs[kind] || def || ""} options={opts} onChange={(v) => pick(kind, v)} /></div>}
              </div>
            );
          })}
        </div>
        <p className="mt-4 flex items-center gap-1.5 text-xs text-ink-faint"><Sparkle className="size-3.5" /> {t("modelSettings.syncNote")}</p>
      </div>
    </div>
  );
}
