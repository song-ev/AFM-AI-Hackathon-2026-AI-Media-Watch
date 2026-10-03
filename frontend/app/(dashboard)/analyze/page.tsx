"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { isAxiosError } from "axios";
import { PlayCircle, RotateCcw, Sparkles, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PipelineView } from "@/components/analyze/PipelineView";
import { BatchPanel } from "@/components/analyze/BatchPanel";
import { LivePanel } from "@/components/analyze/LivePanel";
import { useDemoPipeline } from "@/lib/analyze/useDemoPipeline";
import {
  useSubmitVideoMutation,
  useUploadVideoMutation,
  useVideoStatusQuery,
} from "@/lib/api/ingestion";

const TERMINAL = new Set(["clean", "completed", "failed"]);

export default function AnalyzePage() {
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [mode, setMode] = useState<"single" | "batch" | "live">("single");

  const submit = useSubmitVideoMutation();
  const upload = useUploadVideoMutation();
  const { data: status } = useVideoStatusQuery(videoId);
  const demo = useDemoPipeline();

  const analyze = () => {
    if (!url.trim()) return;
    demo.reset();
    setVideoId(null);
    submit.mutate(url.trim(), {
      onSuccess: (res) => setVideoId(res.video_id),
      onError: (err) => {
        if (isAxiosError(err) && err.response?.status === 400) {
          toast.error(err.response.data?.detail ?? "Неподдерживаемая ссылка");
        } else {
          toast.error("Не удалось запустить анализ");
        }
      },
    });
  };

  const analyzeFile = () => {
    if (!file) return;
    demo.reset();
    setVideoId(null);
    upload.mutate(file, {
      onSuccess: (res) => setVideoId(res.video_id),
      onError: () => toast.error("Не удалось загрузить видео"),
    });
  };

  const runDemo = () => {
    setVideoId(null);
    demo.start();
  };

  // Demo takes precedence over a real run when active.
  const showDemo = demo.status != null;
  const realActive = !!status && !TERMINAL.has(status.overall);

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Анализ видео</h1>
          <p className="text-sm text-muted-foreground">
            Вставьте ссылку и наблюдайте пайплайн в реальном времени - от
            скачивания до вердикта.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border bg-card p-0.5 text-sm">
            <button
              onClick={() => setMode("single")}
              className={
                mode === "single"
                  ? "rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground"
                  : "rounded-md px-3 py-1.5 text-muted-foreground"
              }
            >
              Одно видео
            </button>
            <button
              onClick={() => setMode("batch")}
              className={
                mode === "batch"
                  ? "rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground"
                  : "rounded-md px-3 py-1.5 text-muted-foreground"
              }
            >
              Поток / пакет
            </button>
            <button
              onClick={() => setMode("live")}
              className={
                mode === "live"
                  ? "rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground"
                  : "rounded-md px-3 py-1.5 text-muted-foreground"
              }
            >
              Эфиры
            </button>
          </div>
          <Button
            variant="outline"
            onClick={runDemo}
            className="border-primary/40 text-primary hover:bg-primary/5"
          >
            <Sparkles className="mr-1.5 h-4 w-4" />
            Запустить демо
          </Button>
        </div>
      </div>

      {mode === "batch" && <BatchPanel />}
      {mode === "live" && <LivePanel />}

      {mode === "single" && (
      <div className="panel-accent space-y-4 p-4">
        <div className="space-y-2">
          <div className="flex gap-2">
            <Input
              placeholder="https://www.youtube.com/watch?v=…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && analyze()}
            />
            <Button onClick={analyze} disabled={submit.isPending}>
              <PlayCircle className="mr-1.5 h-4 w-4" />
              {submit.isPending ? "Запуск…" : "Анализировать"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Если скачивание недоступно в этой сети — нажмите{" "}
            <span className="font-medium text-primary">«Запустить демо»</span>{" "}
            или используйте видео из{" "}
            <Link href="/queue" className="underline">
              очереди
            </Link>
            .
          </p>
        </div>

        <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
          <p className="text-sm font-medium">Или загрузите локальное видео</p>
          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="file"
              accept="video/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="max-w-sm"
            />
            <Button
              variant="outline"
              onClick={analyzeFile}
              disabled={!file || upload.isPending}
            >
              <Upload className="mr-1.5 h-4 w-4" />
              {upload.isPending ? "Загрузка…" : "Загрузить и проанализировать"}
            </Button>
          </div>
        </div>
      </div>
      )}

      {showDemo && demo.status && (
        <div className="space-y-2">
          <PipelineView status={demo.status} active={demo.running} demo />
          <div className="flex justify-end">
            <Button variant="ghost" size="sm" onClick={demo.reset}>
              <RotateCcw className="mr-1.5 h-4 w-4" />
              Сбросить демо
            </Button>
          </div>
        </div>
      )}

      {!showDemo && videoId && status && (
        <PipelineView status={status} active={realActive} />
      )}
    </div>
  );
}
