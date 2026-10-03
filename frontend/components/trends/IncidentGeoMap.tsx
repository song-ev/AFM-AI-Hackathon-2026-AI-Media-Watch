"use client";

import dynamic from "next/dynamic";
import { MapPinned } from "lucide-react";

import { useGeoPointsQuery } from "@/lib/api/dashboard";
import { Skeleton } from "@/components/ui/skeleton";

const LeafletMap = dynamic(() => import("@/components/geo/LeafletMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-[360px] w-full rounded-xl" />,
});

export function IncidentGeoMap() {
  const { data, isLoading } = useGeoPointsQuery();

  const points = (data?.points ?? []).map((p) => ({
    lat: p.lat,
    lon: p.lon,
    label: p.label,
    region: p.region,
    risk: p.risk_score,
    username: p.username,
    platform: p.platform,
    caption: p.caption,
  }));

  return (
    <section className="panel-accent p-4">
      <div className="mb-3 flex items-center gap-2">
        <MapPinned className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Карта геолокаций</h2>
        <span className="ml-auto text-xs text-muted-foreground">
          {data?.total ?? 0} точек · размер/цвет = риск
        </span>
      </div>

      {isLoading ? (
        <Skeleton className="h-[360px] w-full rounded-xl" />
      ) : points.length ? (
        <LeafletMap mode="bubbles" points={points} height={360} zoom={5} />
      ) : (
        <div className="flex h-[360px] flex-col items-center justify-center rounded-xl bg-muted/30 text-center text-sm text-muted-foreground">
          <MapPinned className="mb-2 h-6 w-6 opacity-50" />
          Пока нет геолоцированных видео.
          <span className="text-xs">
            Карта наполняется по мере анализа контента с гео-признаками
            (GPS, гео-теги, упоминания локаций).
          </span>
        </div>
      )}

      {data?.regions?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {data.regions.slice(0, 8).map((r) => (
            <span
              key={r.region}
              className="inline-flex items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 text-xs"
            >
              <span className="font-medium">{r.region}</span>
              <span className="text-muted-foreground">{r.count}</span>
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
