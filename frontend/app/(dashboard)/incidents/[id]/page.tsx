"use client";

import { use, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { FileText, Loader2 } from "lucide-react";

import { apiClient } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConnectionGraph } from "@/components/connections/ConnectionGraph";
import { IncidentSidebar } from "@/components/incident/IncidentSidebar";
import { IncidentVerdictHero } from "@/components/incident/IncidentVerdictHero";
import { CategoryFindings } from "@/components/analyze/CategoryFindings";
import { VideoGeoCard } from "@/components/geo/VideoGeoCard";
import { ReasoningGraph } from "@/components/incident/ReasoningGraph";
import {
  TriggerTimeline,
  type TimelineMarker,
} from "@/components/incident/TriggerTimeline";
import {
  VideoPlayer,
  type VideoPlayerHandle,
} from "@/components/incident/VideoPlayer";
import { useIncidentDetailQuery, type IncidentDetail } from "@/lib/api/incidents";

function severityColor(severity: number): string {
  if (severity >= 0.7) return "#dc2626";
  if (severity >= 0.4) return "#f59e0b";
  return "#64748b";
}

function buildMarkers(detail: IncidentDetail): TimelineMarker[] {
  const markers: TimelineMarker[] = [];
  detail.transcript_flags.forEach((f, i) => {
    if (f.start_sec == null) return;
    markers.push({
      id: `flag-${i}`,
      timestamp: f.start_sec,
      color: severityColor(f.severity),
      title: f.phrase,
      subtitle: "Подозрительная фраза",
      category: f.category,
      severity: f.severity,
    });
  });
  detail.fake_screenshots.forEach((s) => {
    if (s.frame_timestamp_sec == null || !s.is_fake) return;
    markers.push({
      id: `fake-${s.id}`,
      timestamp: s.frame_timestamp_sec,
      color: "#9333ea",
      title: `Поддельный скриншот выплаты ${s.bank_name || ""}`.trim(),
      subtitle: "Детекция фейкового скриншота",
      category: "fake_screenshot",
      severity: s.confidence,
    });
  });
  return markers;
}

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function IncidentDetailPage({
  params
}: 
  PageProps
) {
  const unwrappedParams = use(params);
  const incidentId = Number(unwrappedParams.id);
  const playerRef = useRef<VideoPlayerHandle>(null);
  const seekTo = (sec: number) => playerRef.current?.seekTo(sec);

  const { data, isLoading, isError } = useIncidentDetailQuery(incidentId);
  const [playerDuration, setPlayerDuration] = useState(0);
  const [dossierLoading, setDossierLoading] = useState(false);

  const downloadDossier = async () => {
    setDossierLoading(true);
    try {
      const res = await apiClient.get(`/api/incidents/${incidentId}/dossier/`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dossier_incident_${incidentId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      alert("Не удалось сформировать досье. Попробуйте позже.");
    } finally {
      setDossierLoading(false);
    }
  };

  const markers = useMemo(() => (data ? buildMarkers(data) : []), [data]);
  const duration = data?.video.duration_seconds || playerDuration;

  if (isError) {
    return (
      <div className="rounded-lg border bg-card p-10 text-center text-sm text-destructive">
        Не удалось загрузить карточку инцидента.
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Skeleton className="aspect-video w-full" />
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Карточка инцидента #{incidentId}</h1>
          <p className="text-sm text-muted-foreground">
            @{data.social_account.username} · {data.video.platform.name}
          </p>
        </div>
        <Button onClick={downloadDossier} disabled={dossierLoading}>
          {dossierLoading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <FileText className="mr-2 h-4 w-4" />
          )}
          Собрать досье (PDF)
        </Button>
      </div>

      <IncidentVerdictHero detail={data} />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div>
          <Tabs defaultValue="timeline">
            <TabsList>
              <TabsTrigger value="timeline">Таймлайн</TabsTrigger>
              <TabsTrigger value="evidence">Улики</TabsTrigger>
              <TabsTrigger value="graph">Граф рассуждений</TabsTrigger>
              <TabsTrigger value="connections">Связи</TabsTrigger>
            </TabsList>

            <TabsContent value="timeline" className="space-y-4">
              <VideoPlayer
                ref={playerRef}
                src={data.video.url}
                onDuration={setPlayerDuration}
              />
              <TriggerTimeline
                durationSeconds={duration}
                markers={markers}
                onSeek={seekTo}
              />
            </TabsContent>

            <TabsContent value="evidence" className="space-y-4">
              <CategoryFindings categories={data.categories} />
              {data.geo && <VideoGeoCard geo={data.geo} />}
              {!data.geo &&
                !data.categories?.payment?.is_triggered &&
                !data.categories?.brand_link?.is_triggered &&
                !data.categories?.audio_forensics?.is_triggered && (
                  <p className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
                    Для этого инцидента нет данных новых категорий (реквизиты,
                    бренды, аудио-форензика, гео).
                  </p>
                )}
            </TabsContent>

            <TabsContent value="graph">
              <ReasoningGraph
                incidentId={incidentId}
                onNodeTimestampClick={seekTo}
              />
            </TabsContent>

            <TabsContent value="connections" className="space-y-3">
              <div className="flex justify-end">
                <Button variant="outline" size="sm" asChild>
                  <Link
                    href={`/connections?account=${encodeURIComponent(
                      data.social_account.username
                    )}`}
                  >
                    Открыть в полном графе связей
                  </Link>
                </Button>
              </div>
              <ConnectionGraph
                filters={{ account: data.social_account.username }}
                compact
              />
            </TabsContent>
          </Tabs>
        </div>

        <IncidentSidebar detail={data} />
      </div>
    </div>
  );
}
