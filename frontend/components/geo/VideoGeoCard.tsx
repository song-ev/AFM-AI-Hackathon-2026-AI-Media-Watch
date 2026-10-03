"use client";

import dynamic from "next/dynamic";
import { MapPin, Satellite, Tag, Sparkles, HelpCircle } from "lucide-react";

import type { VideoGeo } from "@/lib/api/ingestion";
import { cn } from "@/lib/utils";

// Leaflet touches `window`, so the map is client-only (no SSR).
const LeafletMap = dynamic(() => import("@/components/geo/LeafletMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[260px] items-center justify-center rounded-xl bg-muted/40 text-xs text-muted-foreground">
      Загрузка карты…
    </div>
  ),
});

const SOURCE_META: Record<
  VideoGeo["source"],
  { label: string; icon: typeof MapPin; tone: string }
> = {
  file_gps: { label: "GPS из файла", icon: Satellite, tone: "text-emerald-600 bg-emerald-50 border-emerald-200" },
  platform_tag: { label: "Гео-тег платформы", icon: Tag, tone: "text-blue-600 bg-blue-50 border-blue-200" },
  ai_inference: { label: "AI-инференс по контенту", icon: Sparkles, tone: "text-violet-600 bg-violet-50 border-violet-200" },
  none: { label: "Не определено", icon: HelpCircle, tone: "text-muted-foreground bg-muted border-border" },
};

export function VideoGeoCard({ geo }: { geo: VideoGeo }) {
  const hasCoords = geo.lat != null && geo.lon != null;
  const meta = SOURCE_META[geo.source] ?? SOURCE_META.none;
  const Icon = meta.icon;
  const confPct = Math.round((geo.confidence || 0) * 100);

  return (
    <div className="panel-accent space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <MapPin className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Геолокация видео</h3>
        <span
          className={cn(
            "ml-auto inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            meta.tone
          )}
        >
          <Icon className="h-3 w-3" />
          {meta.label}
        </span>
      </div>

      {hasCoords ? (
        <>
          <LeafletMap
            mode="pin"
            height={240}
            points={[
              {
                lat: geo.lat as number,
                lon: geo.lon as number,
                label: geo.label,
                region: geo.region,
              },
            ]}
          />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <div>
              <span className="text-muted-foreground">Место: </span>
              <span className="font-medium">{geo.label || geo.region || "—"}</span>
            </div>
            {geo.country && (
              <div>
                <span className="text-muted-foreground">Страна: </span>
                <span className="font-medium">{geo.country}</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Уверенность:</span>
              <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                <div
                  className={cn(
                    "h-full rounded-full",
                    confPct >= 70 ? "bg-emerald-500" : confPct >= 40 ? "bg-amber-500" : "bg-rose-500"
                  )}
                  style={{ width: `${confPct}%` }}
                />
              </div>
              <span className="font-mono text-xs">{confPct}%</span>
            </div>
          </div>
          {geo.reasoning && (
            <p className="rounded-lg bg-muted/40 p-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Обоснование AI: </span>
              {geo.reasoning}
            </p>
          )}
        </>
      ) : (
        <p className="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">
          Геопризнаки в этом видео не обнаружены (нет GPS в файле, гео-тега платформы
          и упоминаний локаций в речи/тексте).
        </p>
      )}
    </div>
  );
}
