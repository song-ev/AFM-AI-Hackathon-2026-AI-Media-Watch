"use client";

import { Check, Loader2, Minus, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { VideoStatus } from "@/lib/api/ingestion";

const STEPS = [
  { label: "Скачивание" },
  { label: "Первичный скрининг (Этап 1)" },
  { label: "Глубокий анализ (Этап 2)" },
  { label: "Готово" },
];

type StepState = "done" | "active" | "pending" | "failed" | "skipped";

function stepState(i: number, s: VideoStatus): StepState {
  if (s.overall === "failed") {
    const failedAt =
      s.download_status === "failed" ? 0 : s.screening_status === "error" ? 1 : 2;
    if (i < failedAt) return "done";
    if (i === failedAt) return "failed";
    return "pending";
  }
  const cur: Record<string, number> = {
    downloading: 0,
    screening: 1,
    deep_analysis: 2,
    completed: 3,
    clean: 3,
  };
  const c = cur[s.overall];
  if (s.overall === "clean" && i === 2) return "skipped";
  if (i < c) return "done";
  if (i === c) return c === 3 ? "done" : "active";
  return "pending";
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done")
    return <Check className="h-5 w-5 text-green-600" />;
  if (state === "active")
    return <Loader2 className="h-5 w-5 animate-spin text-blue-600" />;
  if (state === "failed") return <X className="h-5 w-5 text-red-600" />;
  if (state === "skipped")
    return <Minus className="h-5 w-5 text-muted-foreground" />;
  return <span className="h-5 w-5 rounded-full border-2 border-muted" />;
}

export function PipelineStepper({ status }: { status: VideoStatus }) {
  return (
    <ol className="space-y-3">
      {STEPS.map((step, i) => {
        const state = stepState(i, status);
        return (
          <li key={i} className="flex items-center gap-3">
            <StepIcon state={state} />
            <span
              className={cn(
                "text-sm",
                state === "done" && "text-muted-foreground line-through",
                state === "active" && "font-medium",
                state === "pending" && "text-muted-foreground",
                state === "failed" && "font-medium text-red-600"
              )}
            >
              {step.label}
              {state === "skipped" && (
                <span className="ml-2 text-xs text-muted-foreground">
                  не требовался (видео чистое)
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
