/** Available models API (synced with the admin "model channels") + the model selected per purpose (localStorage, per-kind). */
import { request } from "@/lib/api";

export interface ModelOption { name: string; model: string }
export type ModelKind = "chat" | "vl" | "embed" | "rerank";

export const getModels = () =>
  request<{ data: Record<string, ModelOption[]> }>("/api/v1/models", { credentials: "include" });

const KEY = "trn_model_prefs";
function readPrefs(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; }
}
export const getModelPref = (kind: ModelKind): string => readPrefs()[kind] || "";
export const setModelPref = (kind: ModelKind, model: string) => {
  const p = readPrefs();
  if (model) p[kind] = model; else delete p[kind];
  localStorage.setItem(KEY, JSON.stringify(p));
};
export const getChatModelPref = () => getModelPref("chat");
