"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Radio, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LiveConsole } from "@/components/analyze/LiveConsole";
import { useLiveSessionsQuery, useStartLiveMutation } from "@/lib/api/live";

export function LivePanel() {
  const [url, setUrl] = useState("");
  const [chunk, setChunk] = useState(30);
  const start = useStartLiveMutation();
  const { data: sessions } = useLiveSessionsQuery();

  const startLive = () => {
    if (!url.trim()) return;
    start.mutate(
      { url: url.trim(), chunk_seconds: chunk },
      {
        onSuccess: (s) => {
          toast.success(`Мониторинг эфира #${s.id} запущен`);
          setUrl("");
        },
        onError: () => toast.error("Не удалось запустить мониторинг эфира"),
      }
    );
  };

  return (
    <div className="space-y-5">
      <div className="panel-accent space-y-2 p-4">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-red-500" />
          <h3 className="text-sm font-semibold">Мониторинг эфира</h3>
        </div>
        <p className="text-xs text-muted-foreground">
          Захват идущей трансляции по чанкам в реальном времени с потоковым
          анализом и алертами. Акцент на TikTok Live (нужен cookies-файл на
          сервере — см. LIVE.md). YouTube Live работает без cookies.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            placeholder="https://www.tiktok.com/@user/live  /  youtube.com/watch?v=…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && startLive()}
            className="min-w-[280px] flex-1"
          />
          <div className="flex items-center gap-1.5">
            <Input
              type="number"
              min={10}
              max={120}
              value={chunk}
              onChange={(e) => setChunk(Number(e.target.value) || 30)}
              className="w-20"
            />
            <span className="text-xs text-muted-foreground">сек/чанк</span>
          </div>
          <Button onClick={startLive} disabled={start.isPending}>
            {start.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Radio className="mr-1.5 h-4 w-4" />
            )}
            Начать мониторинг
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-muted-foreground">Сессии эфиров</h3>
        {sessions?.length ? (
          sessions.map((s) => <LiveConsole key={s.id} session={s} />)
        ) : (
          <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
            Нет активных эфиров. Вставьте ссылку на трансляцию выше.
          </p>
        )}
      </div>
    </div>
  );
}

