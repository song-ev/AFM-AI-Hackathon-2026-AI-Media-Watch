"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { useIncidentStatsQuery } from "@/lib/api/incidents";
import { STATUS_LABELS } from "@/lib/incidents-ui";
import type { IncidentStatus } from "@/lib/api/incidents";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}

export function QueueStats() {
  const { data, isLoading } = useIncidentStatsQuery();

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[68px]" />
        ))}
      </div>
    );
  }

  const statuses = Object.keys(STATUS_LABELS) as IncidentStatus[];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="В очереди" value={data.queue_total} />
        <Stat label="Всего" value={data.total} />
        <Stat label="Средний risk (24ч)" value={data.avg_risk_score_24h} />
      </div>
      <div className="flex flex-wrap gap-2">
        {statuses.map((status) => (
          <span
            key={status}
            className="rounded-md border bg-card px-3 py-1 text-xs text-muted-foreground"
          >
            {STATUS_LABELS[status]}: {data.status_breakdown[status] ?? 0}
          </span>
        ))}
      </div>
    </div>
  );
}
