import type {
  ReasoningGraphData,
  ReasoningNode,
  ReasoningNodeStatus,
  ReasoningNodeType,
} from "@/lib/api/incidents";
import { riskHex } from "@/lib/utils/riskColor";

// vis-network shapes per node type.
const SHAPE_BY_TYPE: Record<ReasoningNodeType, string> = {
  stage1_signal: "box",
  stage2_signal: "ellipse",
  synthesis: "diamond",
  verdict: "star",
};

interface VisColor {
  background: string;
  border: string;
}

const STATUS_COLOR: Record<ReasoningNodeStatus, VisColor> = {
  triggered: { background: "#fecaca", border: "#dc2626" }, // red/orange
  clean: { background: "#dce7dc", border: "#5f8a5f" }, // grey-green
  not_applicable: { background: "#f1f1f1", border: "#b8b8b8" }, // muted grey
};

// Same risk scale as the queue/card (G3/G4) — single source in riskColor.
export function verdictColor(risk: number): VisColor {
  return riskHex(risk);
}

const NOT_APPLICABLE_TITLE =
  "Этап не запускался (видео не прошло порог Этапа 1)";

export function toVisNodes(graph: ReasoningGraphData) {
  return graph.nodes.map((node) => {
    const isVerdict = node.type === "verdict";
    const color = isVerdict
      ? verdictColor(graph.verdict.risk_score)
      : STATUS_COLOR[node.status];

    const label = isVerdict
      ? `Вердикт\n${
          graph.verdict.label === "триггерный"
            ? "триггерный контент"
            : "не триггерный контент"
        }\nrisk: ${graph.verdict.risk_score.toFixed(0)}`
      : node.label;

    return {
      id: node.id,
      label,
      shape: SHAPE_BY_TYPE[node.type] ?? "box",
      color: { background: color.background, border: color.border },
      title:
        node.status === "not_applicable"
          ? NOT_APPLICABLE_TITLE
          : node.explanation || node.label,
      borderWidth: isVerdict ? 3 : 1,
      size: isVerdict ? 34 : 20,
      font: {
        size: isVerdict ? 18 : 14,
        color: node.status === "not_applicable" ? "#9ca3af" : "#0f172a",
        multi: false as const,
      },
      margin: 8,
    };
  });
}

export function toVisEdges(graph: ReasoningGraphData, showWeights: boolean) {
  const weights = graph.edges.map((e) => e.weight);
  const maxWeight = Math.max(1, ...weights);
  const sumWeight = weights.reduce((a, b) => a + b, 0) || 1;

  return graph.edges.map((edge, i) => ({
    id: `e${i}`,
    from: edge.from,
    to: edge.to,
    width: 1 + (edge.weight / maxWeight) * 7, // normalise to ~1–8px
    label: showWeights
      ? `${Math.round((edge.weight / sumWeight) * 100)}%`
      : undefined,
    font: { size: 10, align: "top", color: "#64748b" },
    color: { color: "#94a3b8", highlight: "#475569" },
  }));
}

// Left-to-right hierarchical layout: signals -> synthesis -> verdict.
export const GRAPH_OPTIONS = {
  layout: {
    hierarchical: {
      enabled: true,
      direction: "LR",
      sortMethod: "directed",
      nodeSpacing: 120,
      levelSeparation: 180,
    },
  },
  physics: false,
  interaction: { hover: true, dragNodes: false, zoomView: true, tooltipDelay: 150 },
  nodes: {
    borderWidth: 1,
    shadow: { enabled: true, size: 8, x: 0, y: 2, color: "rgba(15,23,42,0.18)" },
    font: { face: "Inter, system-ui, sans-serif" },
  },
  edges: {
    arrows: "to",
    smooth: { type: "cubicBezier", forceDirection: "horizontal", roundness: 0.5 },
  },
};

export const LEGEND = {
  shapes: [
    { shape: "▭", label: "Этап 1 — сигнал" },
    { shape: "◯", label: "Этап 2 — сигнал" },
    { shape: "◇", label: "Синтез" },
    { shape: "★", label: "Вердикт" },
  ],
  colors: [
    { color: "#dc2626", label: "Сработал (triggered)" },
    { color: "#5f8a5f", label: "Чисто (clean)" },
    { color: "#b8b8b8", label: "Этап не запускался" },
  ],
};

export function findNode(graph: ReasoningGraphData, id: string): ReasoningNode | undefined {
  return graph.nodes.find((n) => n.id === id);
}
