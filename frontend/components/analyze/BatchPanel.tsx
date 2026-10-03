"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Layers, ListPlus, Radar, Loader2, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { BatchResults } from "@/components/analyze/BatchResults";
import {
  useBatchesQuery,
  useBulkSubmitMutation,
  useCancelBatchMutation,
  useCapabilitiesQuery,
  useParseSourceMutation,
  type BatchProgress,
} from "@/lib/api/batch";

export function BatchPanel() {
  const [bulkText, setBulkText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [limit, setLimit] = useState(30);

  const bulk = useBulkSubmitMutation();
  const parse = useParseSourceMutation();
  const { data: batches } = useBatchesQuery();

  const submitBulk = () => {
    if (!bulkText.trim()) return;
    bulk.mutate(bulkText, {
      onSuccess: (r) =>
        toast.success(`Пакет #${r.batch_id}: ${r.total} видео отправлено`),
      onError: () => toast.error("Не удалось отправить пакет"),
    });
  };

  const submitParse = () => {
    if (!sourceUrl.trim()) return;
    parse.mutate(
      { source_url: sourceUrl.trim(), limit },
      {
        onSuccess: (r) =>
          toast.success(
            r.total
              ? `Пакет #${r.batch_id}: найдено ${r.total} видео`
              : `Источник обработан (${r.note})`
          ),
        onError: () => toast.error("Не удалось разобрать источник"),
      }
    );
  };

  return (
    <div className="space-y-5">
      <ReadinessStrip />
      <div className="grid gap-4 md:grid-cols-2">
        {/* Bulk URLs */}
        <div className="panel-accent space-y-2 p-4">
          <div className="flex items-center gap-2">
            <ListPlus className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">Массовый ввод ссылок</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            Вставьте до 200 ссылок (с новой строки или через пробел) — каждая
            скачается и проанализируется в фоне.
          </p>
          <Textarea
            rows={5}
            placeholder={"https://www.youtube.com/watch?v=…\nhttps://www.tiktok.com/@user/video/…"}
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            className="font-mono text-xs"
          />
          <Button onClick={submitBulk} disabled={bulk.isPending} size="sm">
            {bulk.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Layers className="mr-1.5 h-4 w-4" />
            )}
            Запустить пакет
          </Button>
        </div>

        {/* Parse source */}
        <div className="panel-accent space-y-2 p-4">
          <div className="flex items-center gap-2">
            <Radar className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">Парсинг источника</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            Канал YouTube, <span className="font-mono">@аккаунт</span> TikTok или
            страница хэштега. Соберём последние N видео и проанализируем.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {[
              { label: "YouTube канал", tone: "border-red-200 text-red-600", v: "https://www.youtube.com/@" },
              { label: "TikTok @акк", tone: "border-foreground/20", v: "https://www.tiktok.com/@" },
              { label: "TikTok #хэштег", tone: "border-foreground/20", v: "https://www.tiktok.com/tag/" },
            ].map((p) => (
              <button
                key={p.label}
                onClick={() => setSourceUrl(p.v)}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px] font-medium hover:bg-muted",
                  p.tone
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <Input
            placeholder="https://www.tiktok.com/@username  /  youtube.com/@channel"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={1}
              max={100}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 30)}
              className="w-24"
            />
            <span className="text-xs text-muted-foreground">видео</span>
            <Button
              onClick={submitParse}
              disabled={parse.isPending}
              size="sm"
              className="ml-auto"
            >
              {parse.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Radar className="mr-1.5 h-4 w-4" />
              )}
              Собрать и анализировать
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            TikTok/Instagram требуют cookies-файл на сервере (см. PARSING.md).
          </p>
        </div>
      </div>

      {/* Batches progress */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">
          Пакеты обработки
        </h3>
        {batches?.length ? (
          <div className="space-y-2">
            {batches.map((b) => (
              <BatchRow key={b.batch_id} batch={b} />
            ))}
          </div>
        ) : (
          <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
            Пока нет пакетов. Запустите массовый ввод или парсинг источника.
          </p>
        )}
      </div>
    </div>
  );
}

function ReadinessStrip() {
  const { data } = useCapabilitiesQuery();
  if (!data) return null;
  const caps: { key: keyof typeof data; label: string }[] = [
    { key: "youtube", label: "YouTube" },
    { key: "tiktok", label: "TikTok" },
    { key: "instagram", label: "Instagram" },
    { key: "llm", label: "LLM" },
    { key: "ocr", label: "OCR" },
    { key: "ffmpeg", label: "Эфиры" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card/60 px-3 py-2 text-xs">
      <span className="text-muted-foreground">Готовность:</span>
      {caps.map((c) => (
        <span key={c.key} className="inline-flex items-center gap-1">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              data[c.key] ? "bg-emerald-500" : "bg-muted-foreground/30"
            )}
          />
          {c.label}
        </span>
      ))}
      {!data.tiktok && (
        <span className="text-[11px] text-muted-foreground">
          · TikTok/Instagram — нужен cookies-файл (PARSING.md)
        </span>
      )}
    </div>
  );
}

const KIND_LABEL: Record<BatchProgress["kind"], string> = {
  bulk_urls: "Массовые ссылки",
  folder: "Офлайн-папка",
  source_parse: "Парсинг источника",
};

function BatchRow({ batch }: { batch: BatchProgress }) {
  const cancel = useCancelBatchMutation();
  const [expanded, setExpanded] = useState(false);
  const pct =
    batch.progress ??
    (batch.total ? Math.round((batch.done / batch.total) * 100) : 0);
  const running = batch.status === "running" || batch.status === "pending";
  const cancelled = batch.status === "cancelled";

  return (
    <div className="rounded-xl border bg-card p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold">#{batch.batch_id}</span>
        <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px]">
          {KIND_LABEL[batch.kind]}
        </span>
        {cancelled && (
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            остановлен
          </span>
        )}
        {batch.source && (
          <span className="max-w-[240px] truncate font-mono text-[11px] text-muted-foreground">
            {batch.source}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1.5 text-xs">
          {running && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
          {batch.done}/{batch.total}
          {batch.in_progress ? (
            <span className="rounded-md bg-blue-100 px-1.5 py-0.5 text-[11px] font-medium text-blue-700">
              {batch.in_progress} в анализе
            </span>
          ) : null}
          {batch.flagged > 0 && (
            <span className="rounded-md bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-700">
              {batch.flagged} с риском
            </span>
          )}
          {running && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => cancel.mutate(batch.batch_id)}
              disabled={cancel.isPending}
              className="h-7 text-red-600 hover:bg-red-50"
            >
              <Square className="mr-1 h-3 w-3" /> Стоп
            </Button>
          )}
        </span>
      </div>

      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            batch.status === "completed"
              ? "bg-emerald-500"
              : cancelled
              ? "bg-muted-foreground/40"
              : "bg-primary"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      {batch.items.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs font-medium text-primary hover:underline"
          >
            {expanded ? "Скрыть видео" : `Показать видео (${batch.items.length})`}
          </button>
          {expanded && <BatchResults items={batch.items} />}
        </div>
      )}
    </div>
  );
}
