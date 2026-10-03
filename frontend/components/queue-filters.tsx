"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  RISK_MAX,
  RISK_MIN,
  useQueueFiltersStore,
} from "@/lib/stores/queueFiltersStore";
import { STATUS_LABELS } from "@/lib/incidents-ui";
import type { IncidentStatus } from "@/lib/api/incidents";

// Radix Select can't use an empty-string value, so "all" is a sentinel.
const ALL = "__all__";

const PLATFORMS = [
  { value: "instagram", label: "Instagram" },
  { value: "tiktok", label: "TikTok" },
  { value: "youtube", label: "YouTube" },
];

export function QueueFilters() {
  const {
    platform,
    status,
    riskMin,
    riskMax,
    dateFrom,
    dateTo,
    setPlatform,
    setStatus,
    setRiskRange,
    setDateFrom,
    setDateTo,
    reset,
  } = useQueueFiltersStore();

  const statuses = Object.keys(STATUS_LABELS) as IncidentStatus[];

  return (
    <div className="space-y-4 rounded-lg border bg-card p-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Платформа</label>
          <Select
            value={platform ?? ALL}
            onValueChange={(v) => setPlatform(v === ALL ? undefined : v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Все" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Все</SelectItem>
              {PLATFORMS.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Статус</label>
          <Select
            value={status ?? ALL}
            onValueChange={(v) => setStatus(v === ALL ? undefined : v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Все" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Все</SelectItem>
              {statuses.map((s) => (
                <SelectItem key={s} value={s}>
                  {STATUS_LABELS[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">С даты</label>
          <Input
            type="date"
            value={dateFrom ?? ""}
            onChange={(e) => setDateFrom(e.target.value || undefined)}
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">По дату</label>
          <Input
            type="date"
            value={dateTo ?? ""}
            onChange={(e) => setDateTo(e.target.value || undefined)}
          />
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground">
          Risk score: {riskMin}–{riskMax}
        </label>
        <Slider
          min={RISK_MIN}
          max={RISK_MAX}
          step={5}
          value={[riskMin, riskMax]}
          onValueChange={([min, max]) => setRiskRange(min, max)}
        />
      </div>

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={reset}>
          Сбросить фильтры
        </Button>
      </div>
    </div>
  );
}
