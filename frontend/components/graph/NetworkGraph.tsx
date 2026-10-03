"use client";

import { useEffect, useRef, useState } from "react";
import "vis-network/styles/vis-network.css";

import { cn } from "@/lib/utils";
import { GraphControls } from "@/components/graph/GraphControls";
import { attachHoverHighlight } from "@/lib/vis-interactions";

interface NetworkGraphProps {
  nodes: any[];
  edges: any[];
  options: any;
  onNodeClick?: (nodeId: string) => void;
  className?: string;
}

/**
 * Generic vis-network canvas. vis is imported dynamically inside the effect so
 * nothing browser-only runs during SSR/build. Rebuilds when nodes/edges change.
 * Adds neighbour-highlight on hover and zoom/fit controls.
 */
export function NetworkGraph({
  nodes,
  edges,
  options,
  onNodeClick,
  className,
}: NetworkGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
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

      const nodesDs = new DataSet(nodes as any);
      const edgesDs = new DataSet(edges as any);
      net = new Network(
        containerRef.current,
        { nodes: nodesDs, edges: edgesDs } as any,
        options
      );
      net.on("click", (params: { nodes: string[] }) => {
        if (params.nodes.length) clickRef.current?.(params.nodes[0]);
      });
      attachHoverHighlight(net, nodesDs, edgesDs);
      setNetwork(net);
    })();

    return () => {
      destroyed = true;
      if (net) net.destroy();
      setNetwork(null);
    };
  }, [nodes, edges, options]);

  return (
    <div className={cn("relative overflow-hidden", className)}>
      <div ref={containerRef} className="h-full w-full" />
      <GraphControls network={network} />
    </div>
  );
}
