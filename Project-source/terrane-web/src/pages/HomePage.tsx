/** 工作台首页 —— 知识库列表(网格卡片 + 新建)。点击进入库详情(源 + 检索)。 */

import { Books, Buildings, Lock, Plus, UsersThree } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { Select } from "@/components/ui/Select";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import { createKb, listKbs, type Kb, type Visibility } from "@/lib/kb";

const VIS_ICON = { private: Lock, shared: UsersThree, workspace: Buildings } as const;

export function HomePage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [kbs, setKbs] = useState<Kb[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [vis, setVis] = useState<Visibility>("private");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setKbs((await listKbs()).items); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function onCreate() {
    if (!name.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      const kb = await createKb({ name: name.trim(), description: desc || undefined, visibility: vis });
      setOpen(false); setName(""); setDesc(""); setVis("private");
      navigate(`/${seg}/kb/${kb.id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? t(`errors.${e.code}`, { defaultValue: e.message }) : t("errors.SYSTEM_HTTP_ERROR"));
    } finally { setBusy(false); }
  }

  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  return (
    <div className="px-8 py-10">
        <div className="mx-auto max-w-6xl">
          <div className="flex items-end justify-between gap-4">
            <div>
              <h1 className="text-[28px] font-semibold leading-none tracking-tight text-ink">{t("kb.title")}</h1>
              <p className="mt-2.5 text-sm text-ink-secondary">{t("kb.subtitle")}{!loading && kbs.length > 0 && <span className="text-ink-faint"> · {kbs.length}</span>}</p>
            </div>
            <button type="button" onClick={() => { setOpen(true); setErr(""); }}
              className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-sm transition active:translate-y-px hover:bg-accent-hover">
              <Plus className="size-4" weight="bold" /> {t("kb.create")}
            </button>
          </div>

          {loading ? (
            <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="rounded-(--radius-card) border border-border/60 bg-surface/40 p-5">
                  <div className="flex items-center gap-2"><div className="size-8 animate-pulse rounded-lg bg-canvas" /><div className="h-3.5 w-28 animate-pulse rounded bg-canvas" /></div>
                  <div className="mt-3.5 h-3 w-full animate-pulse rounded bg-canvas" />
                  <div className="mt-2 h-3 w-2/3 animate-pulse rounded bg-canvas" />
                  <div className="mt-4 h-2.5 w-24 animate-pulse rounded bg-canvas" />
                </div>
              ))}
            </div>
          ) : kbs.length === 0 ? (
            <div className="mt-8 flex flex-col items-center rounded-(--radius-card) border border-dashed border-border bg-surface/30 py-20 text-center">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-accent-soft"><Books className="size-7 text-accent" weight="duotone" /></div>
              <p className="mt-4 text-sm font-medium text-ink">{t("kb.empty")}</p>
              <button type="button" onClick={() => { setOpen(true); setErr(""); }}
                className="mt-4 flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-medium text-white transition active:translate-y-px hover:bg-accent-hover">
                <Plus className="size-4" weight="bold" /> {t("kb.create")}
              </button>
            </div>
          ) : (
            <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {kbs.map((kb) => {
                const Icon = VIS_ICON[kb.visibility];
                return (
                  <button key={kb.id} type="button" onClick={() => navigate(`/${seg}/kb/${kb.id}`)}
                    className="group flex flex-col rounded-(--radius-card) border border-border/70 bg-surface/40 p-5 text-start transition duration-150 active:translate-y-0 hover:-translate-y-0.5 hover:border-accent/50 hover:bg-surface hover:shadow-md">
                    <div className="flex items-center gap-2.5">
                      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft transition group-hover:bg-accent group-hover:text-white"><Books className="size-[18px] text-accent transition group-hover:text-white" weight="duotone" /></span>
                      <span className="line-clamp-1 font-medium text-ink transition group-hover:text-accent">{kb.name}</span>
                    </div>
                    <p className="mt-3 line-clamp-2 min-h-[2.5rem] text-[13px] leading-relaxed text-ink-secondary">{kb.description || t("kb.noDesc")}</p>
                    <div className="mt-4 flex items-center gap-1.5 border-t border-border/50 pt-3 text-xs text-ink-faint">
                      <Icon className="size-3.5" /> {t(`kb.vis.${kb.visibility}`)}
                      <span className="mx-0.5 text-border">·</span> {t(`kb.role.${kb.my_role ?? "viewer"}`)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setOpen(false)}>
          <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-ink">{t("kb.createTitle")}</h2>
            <div className="mt-4 space-y-3.5">
              <label className="block text-sm font-medium text-ink">{t("kb.fName")}
                <input value={name} onChange={(e) => setName(e.target.value)} autoFocus disabled={busy} className={`mt-1.5 ${field}`} /></label>
              <label className="block text-sm font-medium text-ink">{t("kb.fDesc")}
                <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} disabled={busy} className={`mt-1.5 ${field}`} /></label>
              <div className="block text-sm font-medium text-ink">{t("kb.fVis")}
                <Select className="mt-1.5" value={vis} onChange={(v) => setVis(v as Visibility)} disabled={busy}
                  options={[{ value: "private", label: t("kb.vis.private") }, { value: "shared", label: t("kb.vis.shared") }, { value: "workspace", label: t("kb.vis.workspace") }]} /></div>
              {err && <p className="text-[13px] text-danger">{err}</p>}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
              <button type="button" onClick={onCreate} disabled={busy || !name.trim()} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.saving") : t("kb.create")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
