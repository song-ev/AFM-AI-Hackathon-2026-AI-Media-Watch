import type { VideoStatus } from "@/lib/api/ingestion";

/**
 * Shared derivation layer for the animated analysis pipeline.
 *
 * Both the real run (driven by `useVideoStatusQuery` polling) and the offline
 * demo mode (`useDemoPipeline`) produce the same `VideoStatus` shape, so every
 * visual — stage cards, live console and mini reasoning graph — is computed
 * here from a single source. Keep all "what does this status mean" logic in
 * this file.
 */

export type StageState = "pending" | "active" | "done" | "skipped" | "failed";

export type StageKey = "download" | "screening" | "deep" | "verdict";

export interface StageDetail {
  label: string;
  value: string;
  /** Hot (risk) styling when a signal fired. */
  triggered?: boolean;
}

export interface StageView {
  key: StageKey;
  /** Full label for the card heading. */
  label: string;
  /** Short label for the connector strip. */
  short: string;
  state: StageState;
  details: StageDetail[];
}

const ORDER: Record<string, number> = {
  downloading: 0,
  screening: 1,
  deep_analysis: 2,
  completed: 3,
  clean: 3,
  failed: 3,
};

/** Index of the stage that errored, for `overall === "failed"`. */
function failedAt(s: VideoStatus): number {
  if (s.download_status === "failed") return 0;
  if (s.screening_status === "error") return 1;
  return 2;
}

/** Index of the currently-running (or final) stage. */
export function currentStageIndex(s: VideoStatus): number {
  if (s.overall === "failed") return failedAt(s);
  return ORDER[s.overall] ?? 0;
}

function stageState(i: number, s: VideoStatus): StageState {
  if (s.overall === "failed") {
    const at = failedAt(s);
    if (i < at) return "done";
    if (i === at) return "failed";
    return "pending";
  }
  const cur = currentStageIndex(s);
  // Clean videos skip Stage 2 (deep analysis) entirely.
  if (s.overall === "clean" && i === 2) return "skipped";
  if (i < cur) return "done";
  if (i === cur) return cur === 3 ? "done" : "active";
  return "pending";
}

const STAGE_META: { key: StageKey; label: string; short: string }[] = [
  { key: "download", label: "Скачивание", short: "Скачивание" },
  { key: "screening", label: "Первичный скрининг", short: "Скрининг" },
  { key: "deep", label: "Глубокий анализ", short: "Глубокий" },
  { key: "verdict", label: "Синтез и вердикт", short: "Вердикт" },
];

export function derivePipeline(s: VideoStatus): StageView[] {
  const cur = currentStageIndex(s);
  const reached = (i: number) => cur >= i || s.overall === "failed";

  return STAGE_META.map((meta, i) => {
    const state = stageState(i, s);
    const details: StageDetail[] = [];

    if (meta.key === "download" && reached(0)) {
      if (state === "failed") {
        details.push({ label: "Статус", value: "недоступно", triggered: true });
      } else if (state === "active") {
        details.push({ label: "Статус", value: "загрузка…" });
      } else {
        details.push({ label: "Файл", value: "получен" });
        details.push({ label: "SHA-256", value: "зафиксирован" });
      }
    }

    if (meta.key === "screening" && reached(1)) {
      details.push({
        label: "Кадров извлечено",
        value: String(s.summary.frames_extracted),
      });
      const ocr = s.summary.ocr_keywords;
      details.push({
        label: "OCR",
        value: ocr.length ? ocr.join(", ") : "совпадений нет",
        triggered: ocr.length > 0,
      });
      details.push({
        label: "Аудио-триггер",
        value: s.summary.audio_triggered ? "сработал" : "чисто",
        triggered: s.summary.audio_triggered,
      });
    }

    if (meta.key === "deep" && reached(2) && state !== "skipped") {
      if (s.summary.signals.length === 0 && state === "active") {
        details.push({ label: "Статус", value: "анализ…" });
      }
      for (const sig of s.summary.signals) {
        details.push({
          label: sig.module,
          value: sig.is_triggered
            ? `сигнал · ${(sig.confidence * 100).toFixed(0)}%`
            : "чисто",
          triggered: sig.is_triggered,
        });
      }
    }

    if (meta.key === "verdict" && reached(3)) {
      if (s.overall === "clean") {
        details.push({ label: "Итог", value: "чисто" });
      } else if (s.overall === "completed") {
        details.push({
          label: "Risk score",
          value: s.risk_score?.toFixed(0) ?? "—",
          triggered: true,
        });
      } else if (s.overall === "failed") {
        details.push({ label: "Итог", value: "анализ прерван", triggered: true });
      }
    }

    return { ...meta, state, details };
  });
}

// --- Live console -----------------------------------------------------------

export type EventTone = "info" | "ok" | "warn" | "err";

export interface PipelineEvent {
  id: string;
  text: string;
  tone: EventTone;
}

/**
 * Ordered set of console lines implied by the current status. The console
 * component diffs this against what it has already shown and reveals the new
 * ones one-by-one, so a status that jumps two stages between polls still reads
 * as a stream rather than a dump.
 */
export function statusToEvents(s: VideoStatus): PipelineEvent[] {
  const ev: PipelineEvent[] = [];
  const cur = currentStageIndex(s);
  const reached = (i: number) => cur >= i || s.overall === "failed";
  const failed = s.overall === "failed";
  const at = failed ? failedAt(s) : -1;

  // Stage 0 — download
  ev.push({ id: "dl-start", text: "▸ Скачивание видео…", tone: "info" });
  if (failed && at === 0) {
    ev.push({ id: "dl-fail", text: "✗ Скачивание не удалось — источник недоступен", tone: "err" });
  } else if (reached(0) && cur > 0) {
    ev.push({ id: "dl-ok", text: "✓ Файл получен, метаданные разобраны", tone: "ok" });
    ev.push({ id: "dl-hash", text: "✓ SHA-256 зафиксирован в цепочке доказательств", tone: "ok" });
  }

  // Stage 1 — screening
  if (reached(1)) {
    ev.push({ id: "sc-start", text: "▸ Первичный скрининг (Этап 1)…", tone: "info" });
    if (cur >= 1 && s.summary.frames_extracted > 0) {
      ev.push({
        id: "sc-frames",
        text: `✓ Извлечено кадров: ${s.summary.frames_extracted}`,
        tone: "ok",
      });
    }
    if (cur > 1 || s.overall === "screening") {
      const ocr = s.summary.ocr_keywords;
      ev.push(
        ocr.length
          ? { id: "sc-ocr", text: `⚠ OCR-совпадения: ${ocr.join(", ")}`, tone: "warn" }
          : { id: "sc-ocr", text: "✓ OCR: ключевых слов не найдено", tone: "ok" }
      );
      ev.push(
        s.summary.audio_triggered
          ? { id: "sc-audio", text: "⚠ Быстрый аудио-анализ: триггер сработал", tone: "warn" }
          : { id: "sc-audio", text: "✓ Быстрый аудио-анализ: чисто", tone: "ok" }
      );
    }
    if (failed && at === 1) {
      ev.push({ id: "sc-fail", text: "✗ Скрининг остановлен с ошибкой", tone: "err" });
    }
  }

  // Stage 2 — deep analysis
  if (reached(2) && s.overall !== "clean") {
    ev.push({ id: "dp-start", text: "▸ Глубокий анализ (Этап 2)…", tone: "info" });
    for (const sig of s.summary.signals) {
      ev.push(
        sig.is_triggered
          ? {
              id: `dp-${sig.module}`,
              text: `⚠ ${sig.module}: сигнал (${(sig.confidence * 100).toFixed(0)}%)`,
              tone: "warn",
            }
          : { id: `dp-${sig.module}`, text: `✓ ${sig.module}: чисто`, tone: "ok" }
      );
    }
    if (failed && at === 2) {
      ev.push({ id: "dp-fail", text: "✗ Глубокий анализ прерван", tone: "err" });
    }
  } else if (s.overall === "clean") {
    ev.push({ id: "dp-skip", text: "— Глубокий анализ не требуется (видео чистое)", tone: "info" });
  }

  // Stage 3 — verdict
  if (reached(3)) {
    ev.push({ id: "synth", text: "▸ Синтез сигналов в граф рассуждений…", tone: "info" });
    if (s.overall === "clean") {
      ev.push({ id: "verdict", text: "★ Вердикт: признаков нарушения не обнаружено", tone: "ok" });
    } else if (s.overall === "completed") {
      ev.push({
        id: "verdict",
        text: `★ Вердикт: триггерный контент · risk ${s.risk_score?.toFixed(0) ?? "—"}`,
        tone: "err",
      });
    } else if (failed) {
      ev.push({ id: "verdict", text: "✗ Вердикт не вынесен — анализ прерван", tone: "err" });
    }
  }

  return ev;
}

export const TONE_CLASS: Record<EventTone, string> = {
  info: "text-muted-foreground",
  ok: "text-emerald-600",
  warn: "text-amber-600",
  err: "text-red-600",
};
