/** 激活页（licensing.md 标准激活流程，UX 参考 Dify Enterprise + 用户参考图）：
 *  锁定态 = 居中状态卡（图标 + 橙点徽标 + 逐字锁定文案 + 按 verdict 区分描述）+「激活」按钮唤起弹窗；
 *  弹窗 = 在线/离线单选；在线填「许可证 ID」，离线展示「集群 ID」可复制 +「离线激活码」粘贴；
 *  已激活 → 跳 /login。错误/成功经右上角 toast。 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckCircle,
  Copy,
  SealCheck,
  X,
  XCircle,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import { activateLicense, getLicenseCard, type LicenseCard } from "@/lib/license";

function errorKey(err: unknown): string {
  const code = err instanceof ApiError ? err.code : "SYSTEM_HTTP_ERROR";
  return `errors.${code}`;
}

/* ── toast（右上角，自动消失） ── */

interface ToastMsg {
  kind: "error" | "success";
  text: string;
}

function Toast({ toast, onDone }: { toast: ToastMsg | null; onDone: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onDone, 4000);
    return () => clearTimeout(timer);
  }, [toast, onDone]);
  if (!toast) return null;
  const error = toast.kind === "error";
  return (
    <div
      role="alert"
      className={`fixed end-6 top-6 z-50 flex max-w-sm items-center gap-2 rounded-(--radius-control) px-4 py-3 text-sm shadow-lg ${
        error ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent"
      }`}
    >
      {error ? <XCircle size={17} weight="fill" className="shrink-0" /> : <CheckCircle size={17} weight="fill" className="shrink-0" />}
      {toast.text}
    </div>
  );
}

/* ── 部署 ID（弹窗内固定展示，单行截断 + 复制；对齐 OpenRelay 激活弹窗） ── */

function DeploymentId({ value }: { value: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium text-ink">{t("activate.deploymentId")}</div>
      <div className="flex items-center gap-2">
        <code className="tnum min-w-0 flex-1 truncate font-mono text-sm text-ink-secondary" title={value}>
          {value}
        </code>
        <button
          type="button"
          aria-label={copied ? t("activate.copied") : t("activate.copy")}
          onClick={copy}
          className="shrink-0 rounded-(--radius-control) p-1.5 text-ink-secondary hover:bg-canvas hover:text-ink focus-visible:ring-2 focus-visible:ring-accent"
        >
          {copied ? <Check size={16} className="text-success" /> : <Copy size={16} />}
        </button>
      </div>
      <p className="mt-1.5 text-xs text-ink-faint">{t("activate.deploymentIdHint")}</p>
    </div>
  );
}

/* ── 激活弹窗 ── */

function ActivateModal({
  fingerprint,
  onClose,
  onToast,
}: {
  fingerprint: string;
  onClose: () => void;
  onToast: (toast: ToastMsg) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [method, setMethod] = useState<"offline" | "online">("online");
  const [credential, setCredential] = useState("");

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ["license"] });
    onToast({ kind: "success", text: t("activate.success") });
    onClose();
  };
  const fail = (err: unknown) => onToast({ kind: "error", text: t(errorKey(err)) });

  const paste = useMutation({
    mutationFn: () => activateLicense(method, credential.trim()),
    onSuccess: done,
    onError: fail,
  });
  const busy = paste.isPending;
  const offline = method === "offline";

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("activate.modalTitle")}
        className="w-full max-w-md rounded-(--radius-card) bg-surface p-6 shadow-xl"
      >
        <div className="mb-1 flex items-start justify-between">
          <h2 className="text-lg font-semibold text-ink">{t("activate.modalTitle")}</h2>
          <button
            type="button"
            aria-label={t("activate.cancel")}
            onClick={onClose}
            className="rounded-(--radius-control) p-1 text-ink-faint hover:bg-canvas hover:text-ink"
          >
            <X size={17} />
          </button>
        </div>
        <p className="mb-5 text-sm text-ink-secondary">{t("activate.modalSubtitle")}</p>

        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (credential.trim()) paste.mutate();
          }}
        >
          <div>
            <div className="mb-2 text-sm font-medium text-ink">{t("activate.method")}</div>
            <fieldset className="flex gap-6" disabled={busy}>
              {(["online", "offline"] as const).map((m) => (
                <label key={m} className="inline-flex items-center gap-2 text-sm text-ink">
                  <input
                    type="radio"
                    name="method"
                    checked={method === m}
                    onChange={() => {
                      setMethod(m);
                      setCredential("");
                    }}
                    className="accent-(--color-accent)"
                  />
                  {t(`activate.${m}`)}
                </label>
              ))}
            </fieldset>
          </div>

          {/* 部署 ID 固定展示（对齐 OpenRelay：在线/离线都展示，硬绑定身份供厂商签发） */}
          <DeploymentId value={fingerprint} />

          <div>
            <label htmlFor="credential" className="mb-1.5 block text-sm font-medium text-ink">
              {t(offline ? "activate.pasteLabel" : "activate.codeLabel")}
            </label>
            <textarea
              id="credential"
              rows={4}
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
              placeholder={t(offline ? "activate.pastePlaceholder" : "activate.codePlaceholder")}
              disabled={busy}
              className="w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 font-mono text-xs text-ink outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-(--radius-control) border border-border bg-surface px-4 py-2 text-sm text-ink hover:bg-canvas focus-visible:ring-2 focus-visible:ring-accent"
            >
              {t("activate.cancel")}
            </button>
            <button
              type="submit"
              disabled={busy || !credential.trim()}
              className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
            >
              {busy ? t("activate.submitting") : t("activate.submit")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── 锁定状态卡（图标 + 橙点徽标 + 逐字锁定文案 + 按状态区分描述 + 激活按钮） ── */

function lockedDescKey(status: LicenseCard["status"]): string {
  if (status === "expired") return "locked.expiredDesc";
  if (status === "revoked") return "locked.revokedDesc";
  if (status === "binding_mismatch") return "locked.mismatchDesc";
  return "locked.desc";
}

function LockedCard({ card, onActivate }: { card: LicenseCard; onActivate: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="w-full max-w-sm rounded-xl border border-border/70 bg-surface p-5 shadow-sm">
      <div className="relative mb-4 inline-block">
        <span className="flex size-10 items-center justify-center rounded-lg border border-border/70 bg-canvas">
          <SealCheck size={20} className="text-ink" />
        </span>
        <span className="absolute -end-1 -top-1 flex size-4 items-center justify-center rounded-full bg-warning text-[10px] font-bold text-white">
          !
        </span>
      </div>
      {/* 锁定提示 —— 文案逐字锁定（licensing.md） */}
      <h2 className="mb-1.5 text-[15px] font-semibold text-ink">{t("locked.message")}</h2>
      <p className="mb-4 text-[13px] leading-relaxed text-ink-secondary">{t(lockedDescKey(card.status))}</p>
      <button
        type="button"
        onClick={onActivate}
        className="rounded-lg bg-accent px-4 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent"
      >
        {t("activate.openButton")}
      </button>
    </div>
  );
}

/* ── 页面 ── */

export function ActivatePage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const [modalOpen, setModalOpen] = useState(false);
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const { data: card, error } = useQuery({
    queryKey: ["license"],
    queryFn: getLicenseCard,
    // 锁定时快轮询（3s）让激活近即时反映；已激活后回落 8s（仍能捕获吊销→重新落锁定页）。
    refetchInterval: (query) => (query.state.data?.unlocked ? 8_000 : 3_000),
  });

  // 激活成功（解锁）→ 跳登录页（认证在后续阶段落地）。
  useEffect(() => {
    if (card?.unlocked) navigate(`/${seg}/login`, { replace: true });
  }, [card?.unlocked, navigate, seg]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-8 py-5">
        <Logo />
        <div className="flex items-center gap-2.5">
          <LanguageSelect />
          <span aria-hidden="true" className="h-5 w-px bg-border" />
          <ThemeToggle />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 pb-24">
        {card?.unlocked ? null : card ? (
          <LockedCard card={card} onActivate={() => setModalOpen(true)} />
        ) : error != null ? (
          <p role="alert" className="text-sm text-danger">
            {t(errorKey(error))}
          </p>
        ) : null}
      </main>

      {modalOpen && card && !card.unlocked && (
        <ActivateModal
          fingerprint={card.fingerprint}
          onClose={() => setModalOpen(false)}
          onToast={setToast}
        />
      )}
      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  );
}
