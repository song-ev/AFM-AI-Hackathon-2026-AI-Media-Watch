"use client";

import { Maximize2, Minus, Plus } from "lucide-react";

import { fitView, zoomBy } from "@/lib/vis-interactions";

/**
 * Floating zoom / fit controls overlaid on a vis-network canvas. Renders
 * nothing until the network instance exists.
 */
function Btn({
    onClick,
    label,
    children,
  }: {
    onClick: () => void;
    label: string;
    children: React.ReactNode;
  }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-8 w-8 items-center justify-center rounded-md border bg-background/90 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:bg-accent hover:text-foreground"
    >
      {children}
    </button>
  );
}

export function GraphControls({ network }: { network: any }) {
  if (!network) return null;

  return (
    <div className="absolute right-2 top-2 z-10 flex flex-col gap-1">
      <Btn onClick={() => zoomBy(network, 1.25)} label="Приблизить">
        <Plus className="h-4 w-4" />
      </Btn>
      <Btn onClick={() => zoomBy(network, 0.8)} label="Отдалить">
        <Minus className="h-4 w-4" />
      </Btn>
      <Btn onClick={() => fitView(network)} label="Вписать в экран">
        <Maximize2 className="h-4 w-4" />
      </Btn>
    </div>
  );
}
