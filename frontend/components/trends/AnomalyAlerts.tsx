"use client";

import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";
import { Activity, Flame, TrendingUp, MapPin, Info } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip as UITooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  useKeywordAnomaliesQuery,
  type KeywordAnomaly,
} from "@/lib/api/dashboard";

const SEVERITY: Record<
  KeywordAnomaly["severity"],
  { label: string; ring: string; chip: string; fill: string }
> = {
  high: {
    label: "Высокая",
    ring: "border-red-300 bg-red-50/70",
    chip: "bg-red-600 text-white",
    fill: "#dc2626",
  },
  medium: {
    label: "Средняя",
    ring: "border-amber-300 bg-amber-50/70",
    chip: "bg-amber-500 text-white",
    fill: "#f59e0b",
  },
  low: {
    label: "Низкая",
    ring: "border-sky-200 bg-sky-50/60",
    chip: "bg-sky-500 text-white",
    fill: "#0ea5e9",
  },
};

function pctLabel(pct: number) {
  if (pct >= 999) return "+999%+";
  return `${pct >= 0 ? "+" : ""}${Math.round(pct)}%`;
}

function AnomalyRow({ a }: { a: KeywordAnomaly }) {
  const sev = SEVERITY[a.severity];
  const series = a.series ?? [];
  return (
    <div className={cn("rounded-xl border p-3", sev.ring)}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Flame
              className={cn(
                "h-4 w-4 shrink-0",
                a.severity === "high" ? "text-red-600" : "text-amber-500"
              )}
            />
            <span className="truncate text-sm font-semibold">«{a.term}»</span>
            <span
              className={cn(
                "ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                sev.chip
              )}
            >
              {sev.label}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Частотность выросла на{" "}
            <span className="font-semibold text-foreground">
              {pctLabel(a.pct_change)}
            </span>{" "}
            за 24 часа
            {a.region ? (
              <span className="inline-flex items-center gap-0.5">
                {" "}
                · <MapPin className="h-3 w-3" /> {a.region}
              </span>
            ) : null}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            сейчас {a.current_count} · база {a.baseline_avg.toFixed(1)}/день · z=
            {a.z_score.toFixed(1)}
          </p>
        </div>

        <div className="h-12 w-28 shrink-0">
          {series.length > 1 && (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
                <defs>
                  <linearGradient id={`g-${a.term}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={sev.fill} stopOpacity={0.5} />
                    <stop offset="100%" stopColor={sev.fill} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis hide domain={[0, "dataMax"]} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke={sev.fill}
                  strokeWidth={1.6}
                  fill={`url(#g-${a.term})`}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}

export function AnomalyAlerts() {
  const { data, isLoading, isError } = useKeywordAnomaliesQuery();
  const anomalies = data?.anomalies ?? [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-red-600" />
          <CardTitle className="text-base">
            Прогноз трендов · всплески ключевых слов
          </CardTitle>
          {data?.high ? (
            <span className="rounded-full bg-red-600 px-2 py-0.5 text-[11px] font-medium text-white">
              {data.high} критич.
            </span>
          ) : null}
          <TooltipProvider>
            <UITooltip>
              <TooltipTrigger asChild>
                <button className="ml-auto text-muted-foreground hover:text-foreground">
                  <Info className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                Детектор аномалий сравнивает частоту каждого термина за последние
                сутки со скользящим базовым уровнем (7 дней) по регионам.
                Резкий рост (z-оценка и % прироста выше порога) поднимает алерт —
                ранний сигнал о новой схеме до роста числа инцидентов.
              </TooltipContent>
            </UITooltip>
          </TooltipProvider>
        </div>
        <p className="text-xs text-muted-foreground">
          Раннее предупреждение: новые фрод-слова, набирающие обороты по регионам
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : isError ? (
          <p className="text-sm text-destructive">Ошибка загрузки.</p>
        ) : anomalies.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <TrendingUp className="h-7 w-7 text-muted-foreground/50" />
            <p className="text-sm font-medium">Всплесков не обнаружено</p>
            <p className="max-w-sm text-xs text-muted-foreground">
              Частотность ключевых слов в норме. Для демо засейте всплеск:
              <code className="mx-1 rounded bg-muted px-1 py-0.5">
                manage.py seed_keyword_spike --term авиатор --region Алматы
              </code>
            </p>
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {anomalies.map((a) => (
              <AnomalyRow key={`${a.term}-${a.region}`} a={a} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
