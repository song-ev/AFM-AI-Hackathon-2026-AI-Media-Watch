"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRoiQuery } from "@/lib/api/dashboard";

// Targets from the doc: Precision >85%, Recall >90%, FPR <10%.
const TARGETS = { precision: 0.85, recall: 0.9, fpr: 0.1 };

function MetricCard({
  title,
  value,
  met,
  hint,
}: {
  title: string;
  value: string;
  met: boolean | null;
  hint: string;
}) {
  const color =
    met === null ? "text-muted-foreground" : met ? "text-green-600" : "text-red-600";
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className={`text-3xl font-bold ${color}`}>{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

export function RoiCards() {
  const { data, isLoading, isError } = useRoiQuery();

  if (isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    );
  }
  if (isError || !data) {
    return <p className="text-sm text-destructive">Не удалось загрузить ROI.</p>;
  }

  const m = data.model;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <MetricCard
        title="Precision"
        value={pct(m?.precision)}
        met={m?.precision == null ? null : m.precision >= TARGETS.precision}
        hint="Цель > 85%"
      />
      <MetricCard
        title="Recall"
        value={pct(m?.recall)}
        met={m?.recall == null ? null : m.recall >= TARGETS.recall}
        hint="Цель > 90%"
      />
      <MetricCard
        title="False Positive Rate"
        value={pct(m?.false_positive_rate)}
        met={
          m?.false_positive_rate == null
            ? null
            : m.false_positive_rate <= TARGETS.fpr
        }
        hint="Цель < 10%"
      />
      <MetricCard
        title="Подтверждённых нарушений"
        value={String(data.confirmed_incidents)}
        met={null}
        hint={`за ${data.period_days} дней`}
      />
      <MetricCard
        title="Сэкономлено времени"
        value={`${data.analyst_time_saved_hours} ч`}
        met={null}
        hint={`авто-фильтр Этапа 1 (${data.auto_rejected_stage1} видео)`}
      />
    </div>
  );
}
