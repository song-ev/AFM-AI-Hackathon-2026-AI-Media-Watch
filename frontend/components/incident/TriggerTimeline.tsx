"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export interface TimelineMarker {
  id: string;
  timestamp: number;
  color: string;
  title: string;
  subtitle: string;
  category: string;
  severity?: number;
}

interface TriggerTimelineProps {
  durationSeconds: number;
  markers: TimelineMarker[];
  onSeek: (seconds: number) => void;
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function TriggerTimeline({
  durationSeconds,
  markers,
  onSeek,
}: TriggerTimelineProps) {
  if (!durationSeconds || durationSeconds <= 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Длительность видео неизвестна — таймлайн недоступен.
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <TooltipProvider delayDuration={100}>
        <div className="relative h-10 w-full rounded-md border bg-muted">
          {markers.map((marker) => {
            const left = Math.min(
              100,
              Math.max(0, (marker.timestamp / durationSeconds) * 100)
            );
            return (
              <Tooltip key={marker.id}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => onSeek(marker.timestamp)}
                    aria-label={marker.title}
                    className="absolute top-0 h-full w-1 -translate-x-1/2 rounded-full focus:outline-none focus:ring-2 focus:ring-ring"
                    style={{ left: `${left}%`, backgroundColor: marker.color }}
                  />
                </TooltipTrigger>
                <TooltipContent>
                  <p className="font-medium">{marker.title}</p>
                  <p className="text-muted-foreground">{marker.subtitle}</p>
                  <p className="mt-1 text-muted-foreground">
                    {formatTime(marker.timestamp)} · {marker.category}
                    {marker.severity != null
                      ? ` · severity ${marker.severity.toFixed(2)}`
                      : ""}
                  </p>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
      </TooltipProvider>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>0:00</span>
        <span>{formatTime(durationSeconds)}</span>
      </div>
    </div>
  );
}
