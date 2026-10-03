"use client";

import { useEffect, useRef, useState } from "react";
import "vis-network/styles/vis-network.css";

import { cn } from "@/lib/utils";
import { GraphControls } from "@/components/graph/GraphControls";
import { attachHoverHighlight } from "@/lib/vis-interactions";
import type { ReasoningGraphData, ReasoningNode } from "@/lib/api/incidents";
import {
  GRAPH_OPTIONS,
  findNode,
  toVisEdges,
  toVisNodes,
} from "@/lib/reasoning-graph-vis";

interface GraphCanvasProps {
  graph: ReasoningGraphData;
  showWeights: boolean;
  onNodeClick: (node: ReasoningNode) => void;
  className?: string;
}

/**
 * Renders the reasoning graph with vis-network. vis is loaded dynamically
 * inside the effect so nothing browser-only runs during SSR/build. Adds
 * neighbour-highlight on hover and zoom/fit controls.
 */
export function GraphCanvas({
  graph,
  showWeights,
  onNodeClick,
  className,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Keep the latest click handler without re-initialising the network.
  const clickRef = useRef(onNodeClick);
  useEffect(() => {
    clickRef.current = onNodeClick;
  }, [onNodeClick]);
  const [network, setNetwork] = useState<any>(null);

  useEffect(() => {
    let destroyed = false;
    let net: any = null;

    (async () => {
      const [{ Network }, { DataSet }] = await Promise.all([
        import("vis-network"),
        import("vis-data"),
      ]);
      if (destroyed || !containerRef.current) return;

      const nodesDs = new DataSet(toVisNodes(graph) as any);
      const edgesDs = new DataSet(toVisEdges(graph, showWeights) as any);
      net = new Network(
        containerRef.current,
        { nodes: nodesDs, edges: edgesDs } as any,
        GRAPH_OPTIONS as any
      );
      net.on("click", (params: { nodes: string[] }) => {
        if (params.nodes.length === 0) return;
        const node = findNode(graph, params.nodes[0]);
        if (node) clickRef.current(node);
      });
      attachHoverHighlight(net, nodesDs, edgesDs);
      setNetwork(net);
    })();

    return () => {
      destroyed = true;
      if (net) net.destroy();
      setNetwork(null);
    };
  }, [graph, showWeights]);

  return (
    <div className={cn("relative overflow-hidden", className)}>
      <div ref={containerRef} className="h-full w-full" />
      <GraphControls network={network} />
    </div>
  );
}
