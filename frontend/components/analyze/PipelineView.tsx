"use client";

import { useMemo } from "react";
import Link from "next/link";
import { ArrowRight, Clapperboard, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PipelineConsole } from "@/components/analyze/PipelineConsole";
import { StageCards } from "@/components/analyze/StageCards";
import { MiniReasoningGraph } from "@/components/analyze/MiniReasoningGraph";
import { CategoryFindings } from "@/components/analyze/CategoryFindings";
import { VideoGeoCard } from "@/components/geo/VideoGeoCard";
import { derivePipeline, statusToEvents } from "@/lib/analyze/pipeline";
import type { VideoStatus } from "@/lib/api/ingestion";

interface PipelineViewProps {
  status: VideoStatus;
  /** Pipeline still running (controls the "live" indicator). */
  active: boolean;
  /** Rendered from the offline demo simulator rather than a real run. */
  demo?: boolean;
}

export function PipelineView({ status, active, demo }: PipelineViewProps) {
  const stages = useMemo(() => derivePipeline(status), [status]);
  const events = useMemo(() => statusToEvents(status), [status]);
  const seconds = (status.processing_time_ms / 1000).toFixed(1);

  return (
    <section className="panel-accent animate-fade-up p-4 sm:p-5">
      <header className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1">
        <Clapperboard className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">
          {demo ? "Демонстрация пайплайна" : `Обработка видео #${status.video_id}`}
        </h2>
        {demo && (
          <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
            <Sparkles className="h-3 w-3" /> demo
          </span>
        )}
        <span className="ml-auto font-mono text-xs text-muted-foreground">
          {seconds} c
        </span>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Left: live console */}
        <PipelineConsole events={events} active={active} />

        {/* Right: stage cards + assembling reasoning graph */}
        <div className="space-y-4">
          <StageCards stages={stages} />
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              Граф рассуждений
            </p>
            <MiniReasoningGraph status={status} />
          </div>
        </div>
      </div>

      <VerdictBanner status={status} demo={demo} />

      <CategoryFindings categories={status.categories} />

      {status.geo && (
        <div className="mt-4">
          <VideoGeoCard geo={status.geo} />
        </div>
      )}
    </section>
  );
}

function VerdictBanner({ status, demo }: { status: VideoStatus; demo?: boolean }) {
  const seconds = (status.processing_time_ms / 1000).toFixed(1);

  if (status.overall === "clean") {
    return (
      <Banner tone="ok">
        Видео проверено, признаков нарушения не обнаружено — обработка заняла{" "}
        {seconds} c.
      </Banner>
    );
  }

  if (status.overall === "completed") {
    return (
      <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-3">
        <div className="text-sm">
          <span className="font-semibold text-red-700">
            Обнаружены признаки нарушения.
          </span>{" "}
          Risk score:{" "}
          <span className="font-semibold">
            {status.risk_score?.toFixed(0) ?? "—"}
          </span>
          .
        </div>
        {status.incident_id ? (
          <Button asChild size="sm" className="ml-auto">
            <Link href={`/incidents/${status.incident_id}`}>
              Открыть карточку инцидента
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Link>
          </Button>
        ) : (
          demo && (
            <span className="ml-auto text-xs text-muted-foreground">
              демо — карточка инцидента не создаётся
            </span>
          )
        )}
      </div>
    );
  }

  if (status.overall === "failed") {
    return (
      <Banner tone="err">
        Обработка не удалась. Возможно, видео недоступно для скачивания в этой
        сети — попробуйте демо-режим или демо-видео из очереди.
      </Banner>
    );
  }

  return null;
}

function Banner({
  tone,
  children,
}: {
  tone: "ok" | "err";
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mt-4 rounded-lg border p-3 text-sm",
        tone === "ok"
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-red-200 bg-red-50 text-red-700"
      )}
    >
      {children}
    </div>
  );
}
