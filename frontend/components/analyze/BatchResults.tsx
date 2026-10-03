"use client";

import { useState } from "react";
import Link from "next/link";
import { Filter, ArrowUpDown, Film, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { RiskRing } from "@/components/ui/RiskRing";
import type { BatchItem } from "@/lib/api/batch";

const STATUS_META: Record<string, { label: string; tone: string; icon: typeof Film }> = {
  downloading: { label: "Скачивание", tone: "text-blue-600", icon: Loader2 },
  screening: { label: "Скрининг", tone: "text-blue-600", icon: Loader2 },
  deep_analysis: { label: "Глубокий анализ", tone: "text-violet-600", icon: Loader2 },
  completed: { label: "Найден риск", tone: "text-red-600", icon: AlertTriangle },
  clean: { label: "Чисто", tone: "text-emerald-600", icon: CheckCircle2 },
  failed: { label: "Ошибка", tone: "text-muted-foreground", icon: Film },
};

export function BatchResults({ items }: { items: BatchItem[] }) {
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [sortRisk, setSortRisk] = useState(true);

  let shown = onlyFlagged ? items.filter((i) => (i.risk_score ?? 0) > 0 || i.incident_id) : items;
  shown = [...shown].sort((a, b) =>
    sortRisk ? (b.risk_score ?? 0) - (a.risk_score ?? 0) : a.video_id - b.video_id
  );

  if (!items.length) return null;

  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button
          onClick={() => setOnlyFlagged((v) => !v)}
          className={cn(
            "inline-flex items-center gap-1 rounded-md border px-2 py-1 transition",
            onlyFlagged ? "border-red-300 bg-red-50 text-red-700" : "text-muted-foreground hover:bg-muted"
          )}
        >
          <Filter className="h-3 w-3" /> Только с риском
        </button>
        <button
          onClick={() => setSortRisk((v) => !v)}
          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-muted-foreground hover:bg-muted"
        >
          <ArrowUpDown className="h-3 w-3" /> {sortRisk ? "По риску" : "По порядку"}
        </button>
        <span className="ml-auto text-muted-foreground">{shown.length} видео</span>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {shown.map((it) => (
          <VideoCard key={it.video_id} item={it} />
        ))}
      </div>
    </div>
  );
}

function VideoCard({ item }: { item: BatchItem }) {
  const meta = STATUS_META[item.overall] ?? STATUS_META.failed;
  const Icon = meta.icon;
  const risk = item.risk_score ?? 0;
  const flagged = item.overall === "completed" || risk >= 40;
  const inFlight = ["downloading", "screening", "deep_analysis"].includes(item.overall);

  const card = (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-card transition-all hover:shadow-md",
        flagged && "border-red-300 ring-1 ring-red-200"
      )}
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-muted">
        {item.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumbnail_url}
            alt=""
            className="h-full w-full object-cover transition group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Film className="h-6 w-6 opacity-40" />
          </div>
        )}
        {/* Risk ring overlay (the wow element) */}
        {(item.overall === "completed" || item.overall === "clean") && (
          <div className="absolute right-1.5 top-1.5 rounded-full bg-background/85 p-0.5 backdrop-blur">
            <RiskRing score={risk} size={38} stroke={4} />
          </div>
        )}
        {inFlight && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/50">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
        )}
      </div>
      {/* Footer */}
      <div className="space-y-0.5 p-2">
        <div className={cn("flex items-center gap-1 text-[11px] font-medium", meta.tone)}>
          <Icon className={cn("h-3 w-3", inFlight && "animate-spin")} />
          {meta.label}
        </div>
        <p className="truncate text-[11px] text-muted-foreground">
          {item.caption || `#${item.video_id}`}
        </p>
      </div>
    </div>
  );

  return item.incident_id ? (
    <Link href={`/incidents/${item.incident_id}`}>{card}</Link>
  ) : (
    card
  );
}
