"use client";

import { Check, Loader2, Minus, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { StageState, StageView } from "@/lib/analyze/pipeline";

function StageIcon({ state }: { state: StageState }) {
  const base = "flex h-9 w-9 items-center justify-center rounded-full border-2";
  if (state === "done")
    return (
      <span className={cn(base, "border-emerald-500 bg-emerald-50 text-emerald-600")}>
        <Check className="h-4 w-4" />
      </span>
    );
  if (state === "active")
    return (
      <span className={cn(base, "glow-active border-primary bg-primary/5 text-primary")}>
        <Loader2 className="h-4 w-4 animate-spin" />
      </span>
    );
  if (state === "failed")
    return (
      <span className={cn(base, "border-red-500 bg-red-50 text-red-600")}>
        <X className="h-4 w-4" />
      </span>
    );
  if (state === "skipped")
    return (
      <span className={cn(base, "border-muted bg-muted/40 text-muted-foreground")}>
        <Minus className="h-4 w-4" />
      </span>
    );
  return <span className={cn(base, "border-muted bg-card text-muted-foreground/40")}>•</span>;
}

function StageCard({ stage, last }: { stage: StageView; last: boolean }) {
  const { state } = stage;
  const filled = state === "done" || state === "failed";
  return (
    <li className="flex gap-3">
      {/* Rail: icon + connector to the next stage */}
      <div className="flex flex-col items-center">
        <StageIcon state={state} />
        {!last && (
          <div className="connector my-1 w-0.5 flex-1 rounded">
            <div
              className={cn(
                "connector-fill transition-transform duration-700 ease-out",
                state === "active" && "connector-flow"
              )}
              style={{
                transform: filled
                  ? "scaleY(1)"
                  : state === "active"
                    ? "scaleY(0.5)"
                    : "scaleY(0)",
                transformOrigin: "top",
                width: "100%",
                height: "100%",
              }}
            />
          </div>
        )}
      </div>

      {/* Content card */}
      <div
        className={cn(
          "mb-3 flex-1 rounded-lg border bg-card p-3 transition-colors",
          state === "active" && "border-primary/40 bg-primary/[0.03]",
          state === "pending" && "opacity-60",
          state === "failed" && "border-red-500/40 bg-red-50/40"
        )}
      >
        <div className="flex items-center justify-between">
          <p
            className={cn(
              "text-sm font-medium",
              state === "pending" && "text-muted-foreground",
              state === "failed" && "text-red-600"
            )}
          >
            {stage.label}
          </p>
          {state === "skipped" && (
            <span className="text-[11px] text-muted-foreground">не требовался</span>
          )}
          {state === "active" && (
            <span className="text-[11px] font-medium text-primary">обработка…</span>
          )}
        </div>

        {stage.details.length > 0 && (
          <dl className="mt-2 flex flex-wrap gap-1.5">
            {stage.details.map((d, i) => (
              <span
                key={`${d.label}-${i}`}
                className={cn(
                  "animate-pop-in inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px]",
                  d.triggered
                    ? "border-red-200 bg-red-50 text-red-700"
                    : "border-border bg-muted/50 text-muted-foreground"
                )}
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <span className="font-medium">{d.label}:</span>
                <span>{d.value}</span>
              </span>
            ))}
          </dl>
        )}
      </div>
    </li>
  );
}

export function StageCards({ stages }: { stages: StageView[] }) {
  return (
    <ol className="flex flex-col">
      {stages.map((stage, i) => (
        <StageCard key={stage.key} stage={stage} last={i === stages.length - 1} />
      ))}
    </ol>
  );
}
