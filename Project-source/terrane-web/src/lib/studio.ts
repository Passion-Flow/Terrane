/** Studio generation API (NotebookLM-style artifacts). POST /knowledge-bases/{id}/studio/{kind}. */

import { request } from "@/lib/api";
import { apiBase } from "@/lib/config";

export type StudioKind =
  | "study_guide" | "faq" | "briefing" | "timeline"
  | "mind_map" | "flashcards" | "quiz" | "data_table"
  | "slide_deck" | "audio_overview";

export interface StudioResult {
  kind: StudioKind;
  format: "markdown" | "json" | "empty";
  content: unknown;
  ok?: boolean;
  reason?: string;
}

export interface Flashcard { front: string; back: string }
export interface QuizItem { q: string; options: string[]; answer: number; explain?: string }
export interface MindMapNode { id: string; label: string; parent: string }
export interface MindMap { root: string; nodes: MindMapNode[] }
export interface DataTable { columns: string[]; rows: string[][] }
export interface SlideDeck { title: string; subtitle?: string; slides: { title: string; bullets: string[] }[] }
export interface PodcastLine { speaker: string; text: string }
export interface Podcast { script: PodcastLine[]; audio: string }

export const generateStudio = (kbId: string, kind: StudioKind) =>
  request<StudioResult>(`/api/v1/knowledge-bases/${kbId}/studio/${kind}`, {
    method: "POST", credentials: "include",
  });

/** Podcast audio (two-speaker TTS); returns {script, audio(data url)} or {ok:false,reason}. */
export const generateAudioOverview = (kbId: string) =>
  request<{ kind: string; format: string; content: Podcast | null; ok?: boolean; reason?: string }>(
    `/api/v1/knowledge-bases/${kbId}/audio-overview`, { method: "POST", credentials: "include" });

/** Export the slide deck as a pptx download. */
export async function exportSlideDeck(kbId: string): Promise<void> {
  const resp = await fetch(`${apiBase()}/api/v1/knowledge-bases/${kbId}/slide-deck/export`, {
    method: "POST", credentials: "include",
  });
  if (!resp.ok) throw new Error("export failed");
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "terrane-slides.pptx";
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
