"use client";

import Link from "next/link";
import { Radio, Square, AlertTriangle, ShieldAlert, ExternalLink, Film } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RiskRing } from "@/components/ui/RiskRing";
import { cn } from "@/lib/utils";
import { useStopLiveMutation, type LiveSession } from "@/lib/api/live";

const STATUS_META: Record<LiveSession["status"], { label: string; tone: string }> = {
  pending: { label: "Подключение…", tone: "bg-amber-100 text-amber-700" },
  live: { label: "В ЭФИРЕ", tone: "bg-red-100 text-red-700" },
  stopped: { label: "Остановлен", tone: "bg-muted text-muted-foreground" },
  ended: { label: "Завершён", tone: "bg-muted text-muted-foreground" },
  failed: { label: "Ошибка", tone: "bg-rose-100 text-rose-700" },
};

export function LiveConsole({ session }: { session: LiveSession }) {
  const stop = useStopLiveMutation();
  const meta = STATUS_META[session.status];
  const live = session.status === "live" || session.status === "pending";
  const escalated = session.max_risk_score >= 60;

  // Build a per-chunk timeline: a tick for each captured chunk, coloured red
  // where an alert landed on it.
  const alertByChunk = new Map(session.alerts.map((a) => [a.chunk_index, a]));
  const ticks = Array.from({ length: Math.max(session.chunks_captured, 1) }, (_, i) => {
    const a = alertByChunk.get(i);
    return { i, risk: a?.risk_score ?? 0, alert: !!a };
  });

  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border bg-card",
        escalated && "border-red-300 ring-1 ring-red-200"
      )}
    >
      {/* Escalation banner */}
      {escalated && (
        <div className="flex items-center gap-2 bg-gradient-to-r from-red-600 to-rose-500 px-4 py-2 text-sm font-semibold text-white">
          <ShieldAlert className="h-4 w-4 animate-pulse" />
          Нарушение в прямом эфире — риск {Math.round(session.max_risk_score)}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-bold tracking-wide",
            meta.tone
          )}
        >
          {live && <span className="h-2 w-2 animate-pulse rounded-full bg-current" />}
          {meta.label}
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">
            {session.title || session.streamer || session.url}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {session.streamer && `@${session.streamer} · `}
            {session.platform.toUpperCase()} · чанков: {session.chunks_captured}
          </div>
        </div>
        {live && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => stop.mutate(session.id)}
            disabled={stop.isPending}
            className="ml-auto h-7 text-red-600 hover:bg-red-50"
          >
            <Square className="mr-1 h-3 w-3" /> Стоп
          </Button>
        )}
      </div>

      <div className="grid gap-4 p-4 md:grid-cols-[2fr_1fr]">
        {/* Preview: the last captured chunk (the actual analysed segment).
            The platform's live page itself can't be embedded. */}
        <div className="relative aspect-video overflow-hidden rounded-xl border bg-black">
          {session.last_chunk_url ? (
            <video
              key={session.last_chunk_url}
              src={session.last_chunk_url}
              controls
              autoPlay
              muted
              loop
              playsInline
              className="h-full w-full object-contain"
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
              <Film className="h-7 w-7 opacity-40" />
              <span className="text-xs">Захват первого чанка…</span>
            </div>
          )}
          <div className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white">
            захваченный сегмент
          </div>
          <Link
            href={session.url}
            target="_blank"
            className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded bg-black/60 px-2 py-1 text-[11px] font-medium text-white hover:bg-black/80"
          >
            <ExternalLink className="h-3 w-3" /> Открыть эфир
          </Link>
        </div>

        {/* Live risk meter (wow) */}
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border bg-muted/30 p-3">
          <RiskRing score={session.max_risk_score} size={108} stroke={9} label="риск" />
          <div className="text-center text-xs text-muted-foreground">
            Макс. риск эфира
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <Radio className={cn("h-3.5 w-3.5", live ? "text-red-500" : "text-muted-foreground")} />
            {session.alerts_count} алертов
          </div>
        </div>
      </div>

      {/* Chunk timeline */}
      <div className="px-4 pb-2">
        <div className="mb-1 text-[11px] text-muted-foreground">
          Таймлайн чанков ({session.chunk_seconds}с каждый)
        </div>
        <div className="flex flex-wrap gap-1">
          {ticks.map((t) => (
            <div
              key={t.i}
              title={t.alert ? `Чанк ${t.i}: риск ${Math.round(t.risk)}` : `Чанк ${t.i}`}
              className={cn(
                "h-6 w-3 rounded-sm transition-all",
                t.alert
                  ? t.risk >= 60
                    ? "bg-red-500"
                    : "bg-amber-400"
                  : "bg-emerald-400/60"
              )}
            />
          ))}
          {live && (
            <div className="h-6 w-3 animate-pulse rounded-sm bg-primary/40" title="захват…" />
          )}
        </div>
      </div>

      {/* Alert feed */}
      {session.alerts.length > 0 && (
        <div className="space-y-1 border-t px-4 py-2">
          {session.alerts.slice(0, 8).map((a) => (
            <div
              key={a.id}
              className="flex items-center gap-2 rounded-md bg-red-50/60 px-2 py-1 text-xs"
            >
              <AlertTriangle className="h-3 w-3 shrink-0 text-red-600" />
              <span className="text-muted-foreground">
                чанк {a.chunk_index} · риск {Math.round(a.risk_score)}
              </span>
              <span className="truncate text-[11px] text-muted-foreground">
                {a.reasons.join(", ")}
              </span>
              {a.incident_id && (
                <Link
                  href={`/incidents/${a.incident_id}`}
                  className="ml-auto font-medium text-red-700 underline"
                >
                  инцидент #{a.incident_id}
                </Link>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
