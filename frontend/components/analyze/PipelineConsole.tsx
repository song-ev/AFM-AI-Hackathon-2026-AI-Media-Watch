"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import type { EventTone, PipelineEvent } from "@/lib/analyze/pipeline";

const REVEAL_MS = 260;

// Console runs on a dark surface, so it uses the 400-weight scale (static class
// strings so Tailwind keeps them).
const CONSOLE_TONE: Record<EventTone, string> = {
  info: "text-slate-400",
  ok: "text-emerald-400",
  warn: "text-amber-400",
  err: "text-red-400",
};

/**
 * Live "analysis.log" panel. Accumulates every event id it has seen and reveals
 * newly-arrived ones one at a time, so a status that jumps stages between polls
 * still reads as a stream. Pure CSS animation — no animation library.
 */
export function PipelineConsole({
  events,
  active,
}: {
  events: PipelineEvent[];
  active: boolean;
}) {
  const [all, setAll] = useState<PipelineEvent[]>(events);
  const [previousEvents, setPreviousEvents] = useState(events);
  const [visible, setVisible] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Merge any never-seen events onto the ordered list (keeps order stable).
  if (previousEvents !== events) {
    setPreviousEvents(events);
    const ids = new Set(all.map((event) => event.id));
    const merged = all.slice();
    for (const event of events) {
      if (!ids.has(event.id)) {
        ids.add(event.id);
        merged.push(event);
      }
    }
    setAll(merged);
  }

  // Reveal one queued line at a time.
  useEffect(() => {
    if (visible >= all.length) return;
    const t = setInterval(() => {
      setVisible((v) => (v >= all.length ? v : v + 1));
    }, REVEAL_MS);
    return () => clearInterval(t);
  }, [all.length, visible]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [visible]);

  const lines = all.slice(0, visible);
  const streaming = active || visible < all.length;

  return (
    <div className="flex h-full min-h-[340px] flex-col overflow-hidden rounded-lg border bg-slate-950 text-slate-200">
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
        <span className="ml-2 font-mono text-xs text-slate-400">Console</span>
        {streaming && (
          <span className="ml-auto flex items-center gap-1.5 text-[11px] text-slate-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            live
          </span>
        )}
      </div>

      <div
        ref={scrollRef}
        className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2.5 font-mono text-[12.5px] leading-relaxed"
      >
        {lines.map((e, i) => (
          <p
            key={e.id}
            className={cn(
              "animate-line-in whitespace-pre-wrap break-words",
              CONSOLE_TONE[e.tone],
              i === lines.length - 1 && streaming && "console-cursor"
            )}
          >
            <span className="select-none text-slate-600">{">"} </span>
            {e.text}
          </p>
        ))}
        {lines.length === 0 && (
          <p className="text-slate-500">
            <span className="console-cursor">ожидание данных пайплайна</span>
          </p>
        )}
      </div>
    </div>
  );
}
