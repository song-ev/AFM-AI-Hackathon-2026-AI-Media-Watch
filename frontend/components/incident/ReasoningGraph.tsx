"use client";

import { useState } from "react";
import { Maximize2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { GraphCanvas } from "@/components/incident/GraphCanvas";
import {
  useReasoningGraphQuery,
  type ReasoningNode,
} from "@/lib/api/incidents";
import { LEGEND } from "@/lib/reasoning-graph-vis";

interface ReasoningGraphProps {
  incidentId: number;
  /** Called when a node with a timestamp is clicked (sync with the player). */
  onNodeTimestampClick?: (sec: number) => void;
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-md border bg-card p-3 text-xs">
      <div className="flex flex-wrap items-center gap-3">
        {LEGEND.shapes.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5">
            <span className="text-base leading-none">{s.shape}</span>
            {s.label}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {LEGEND.colors.map((c) => (
          <span key={c.label} className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{ backgroundColor: c.color }}
            />
            {c.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ReasoningGraph({
  incidentId,
  onNodeTimestampClick,
}: ReasoningGraphProps) {
  const { data, isLoading, isError } = useReasoningGraphQuery(incidentId);
  const [showWeights, setShowWeights] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [selected, setSelected] = useState<ReasoningNode | null>(null);

  const handleNodeClick = (node: ReasoningNode) => {
    if (node.timestamp_sec != null && onNodeTimestampClick) {
      onNodeTimestampClick(node.timestamp_sec);
    } else {
      setSelected(node);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-[420px] flex-col items-center justify-center gap-3 rounded-lg border bg-card text-muted-foreground">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        <p className="text-sm">Строим граф рассуждений…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-lg border bg-card text-sm text-destructive">
        Не удалось загрузить граф рассуждений.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={showWeights}
            onChange={(e) => setShowWeights(e.target.checked)}
          />
          Показывать веса
        </label>
        <Button variant="outline" size="sm" onClick={() => setFullscreen(true)}>
          <Maximize2 className="mr-2 h-4 w-4" />
          Развернуть на весь экран
        </Button>
      </div>

      <GraphCanvas
        graph={data}
        showWeights={showWeights}
        onNodeClick={handleNodeClick}
        className="h-[480px] w-full rounded-lg border bg-card"
      />

      <Legend />

      {/* Node explanation modal (for nodes without a timestamp). */}
      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{selected?.label}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-2 text-sm">
              <p className="text-muted-foreground">
                Статус: {selected.status} · вклад в risk:{" "}
                {selected.score_contribution.toFixed(1)}
              </p>
              <p>{selected.explanation || "Нет дополнительного описания."}</p>
              {selected.timestamp_sec != null && (
                <button
                  className="text-sm underline"
                  onClick={() => {
                    onNodeTimestampClick?.(selected.timestamp_sec as number);
                    setSelected(null);
                  }}
                >
                  Перейти к {selected.timestamp_sec.toFixed(1)} c в видео
                </button>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Fullscreen graph. */}
      <Dialog open={fullscreen} onOpenChange={setFullscreen}>
        <DialogContent className="h-[92vh] w-[96vw] max-w-none">
          <DialogHeader>
            <DialogTitle>Граф рассуждений</DialogTitle>
          </DialogHeader>
          <GraphCanvas
            graph={data}
            showWeights={showWeights}
            onNodeClick={handleNodeClick}
            className="h-full w-full rounded-lg border bg-card"
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
