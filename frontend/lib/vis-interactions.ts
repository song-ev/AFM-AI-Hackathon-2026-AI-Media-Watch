/**
 * Shared vis-network interaction helpers used by both the connection graph and
 * the reasoning graph. Kept framework-agnostic (no React) so the wrappers stay
 * thin.
 */

const DIM_OPACITY = 0.18;
const DIM_EDGE = { color: "#e2e8f0", opacity: 0.25 };
const HOT_EDGE = { color: "#475569", opacity: 1 };

/**
 * Highlight the hovered node and its immediate neighbourhood, dimming
 * everything else — makes dense graphs readable. Restores original styling on
 * blur. Originals are captured up front so per-edge colours survive.
 */
export function attachHoverHighlight(
  network: any,
  nodes: any,
  edges: any
): void {
  const origEdgeColor = new Map<string, any>();
  edges.forEach((e: any) => origEdgeColor.set(e.id, e.color));

  const allNodeIds = (): string[] => nodes.getIds();
  const allEdgeIds = (): string[] => edges.getIds();

  network.on("hoverNode", (params: { node: string }) => {
    const id = params.node;
    const keep = new Set<string>(network.getConnectedNodes(id));
    keep.add(id);
    const keepEdges = new Set<string>(network.getConnectedEdges(id));

    nodes.update(
      allNodeIds().map((nid) => ({
        id: nid,
        opacity: keep.has(nid) ? 1 : DIM_OPACITY,
      }))
    );
    edges.update(
      allEdgeIds().map((eid) => ({
        id: eid,
        color: keepEdges.has(eid) ? HOT_EDGE : DIM_EDGE,
      }))
    );
  });

  network.on("blurNode", () => {
    nodes.update(allNodeIds().map((nid) => ({ id: nid, opacity: 1 })));
    edges.update(
      allEdgeIds().map((eid) => ({ id: eid, color: origEdgeColor.get(eid) }))
    );
  });
}

/** Zoom by a multiplicative factor around the current view. */
export function zoomBy(network: any, factor: number): void {
  if (!network) return;
  const scale = network.getScale() * factor;
  network.moveTo({
    scale: Math.min(4, Math.max(0.1, scale)),
    animation: { duration: 200, easingFunction: "easeInOutQuad" },
  });
}

export function fitView(network: any): void {
  if (!network) return;
  network.fit({ animation: { duration: 350, easingFunction: "easeInOutQuad" } });
}
