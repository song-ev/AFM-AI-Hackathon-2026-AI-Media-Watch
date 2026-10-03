"use client";

import { cn } from "@/lib/utils";
import { currentStageIndex } from "@/lib/analyze/pipeline";
import { riskLevel } from "@/lib/utils/riskColor";
import type { VideoStatus } from "@/lib/api/ingestion";

/**
 * Schematic mini reasoning graph that assembles itself as the pipeline runs:
 * signal nodes (left) → synthesis (centre) → verdict (right). Pure SVG + CSS so
 * it stays cheap on the analyze screen; the full vis-network reasoning graph
 * lives on the incident card.
 */

interface SignalNode {
  id: string;
  label: string;
  triggered: boolean;
}

function shorten(label: string, n = 14) {
  return label.length > n ? label.slice(0, n - 1) + "…" : label;
}

export function MiniReasoningGraph({ status }: { status: VideoStatus }) {
  const cur = currentStageIndex(status);
  const isClean = status.overall === "clean";
  const isFailed = status.overall === "failed";

  const signals: SignalNode[] = [];
  if (cur >= 1) {
    signals.push({
      id: "ocr",
      label: "OCR",
      triggered: status.summary.ocr_keywords.length > 0,
    });
    signals.push({
      id: "audio",
      label: "Аудио",
      triggered: status.summary.audio_triggered,
    });
  }
  if (cur >= 2 && !isClean) {
    for (const s of status.summary.signals) {
      signals.push({
        id: s.module,
        label: shorten(s.module),
        triggered: s.is_triggered,
      });
    }
  }

  const showSynthesis = cur >= 2 || (isClean && cur >= 3);
  const showVerdict = cur >= 3;

  const verdictTone = isFailed
    ? "fail"
    : isClean
      ? "clean"
      : status.risk_score != null
        ? riskLevel(status.risk_score)
        : "clean";

  // viewBox coordinate helpers (0–100).
  const sx = 16;
  const cx = 52;
  const vx = 86;
  const yOf = (i: number, n: number) => ((i + 1) / (n + 1)) * 100;

  const edgeClass = (triggered: boolean) =>
    triggered ? "stroke-red-400" : "stroke-slate-300";

  return (
    <div className="relative h-[200px] w-full overflow-hidden rounded-lg border bg-card">
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        {showSynthesis &&
          signals.map((s, i) => (
            <line
              key={s.id}
              x1={sx}
              y1={yOf(i, signals.length)}
              x2={cx}
              y2={50}
              className={cn("animate-line-in", edgeClass(s.triggered))}
              strokeWidth={s.triggered ? 0.7 : 0.4}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        {showVerdict && showSynthesis && (
          <line
            x1={cx}
            y1={50}
            x2={vx}
            y2={50}
            className={cn(
              "animate-line-in",
              verdictTone === "high" || verdictTone === "fail"
                ? "stroke-red-400"
                : verdictTone === "medium"
                  ? "stroke-amber-400"
                  : "stroke-emerald-400"
            )}
            strokeWidth={0.9}
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      {/* Signal nodes */}
      {signals.map((s, i) => (
        <Node
          key={s.id}
          left={sx}
          top={yOf(i, signals.length)}
          className={cn(
            "animate-pop-in border",
            s.triggered
              ? "border-red-300 bg-red-50 text-red-700"
              : "border-emerald-300 bg-emerald-50 text-emerald-700"
          )}
        >
          {s.label}
        </Node>
      ))}

      {/* Synthesis */}
      {showSynthesis && (
        <Node
          left={cx}
          top={50}
          className="animate-pop-in border-2 border-primary bg-primary/10 font-medium text-primary"
        >
          Синтез
        </Node>
      )}

      {/* Verdict */}
      {showVerdict && (
        <Node
          left={vx}
          top={50}
          className={cn(
            "animate-pop-in border-2 font-semibold",
            verdictTone === "high" || verdictTone === "fail"
              ? "glow-active border-red-500 bg-red-50 text-red-700"
              : verdictTone === "medium"
                ? "border-amber-500 bg-amber-50 text-amber-700"
                : "border-emerald-500 bg-emerald-50 text-emerald-700"
          )}
        >
          {isFailed
            ? "Прервано"
            : isClean
              ? "Чисто"
              : `Risk ${status.risk_score?.toFixed(0) ?? "—"}`}
        </Node>
      )}

      {signals.length === 0 && (
        <p className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
          Граф соберётся по мере анализа…
        </p>
      )}
    </div>
  );
}

function Node({
  left,
  top,
  className,
  children,
}: {
  left: number;
  top: number;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-md px-2 py-1 text-[11px] shadow-sm",
        className
      )}
      style={{ left: `${left}%`, top: `${top}%` }}
    >
      {children}
    </div>
  );
}
