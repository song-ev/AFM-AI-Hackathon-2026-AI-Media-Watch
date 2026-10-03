import type { ConnectionGraphData, ConnectionNode } from "@/lib/api/connections";

export const PLATFORM_COLOR: Record<string, string> = {
  instagram: "#E1306C",
  tiktok: "#10b981",
  youtube: "#FF0000",
};

function nodeTypeMap(data: ConnectionGraphData): Record<string, ConnectionNode["type"]> {
  const map: Record<string, ConnectionNode["type"]> = {};
  for (const n of data.nodes) map[n.id] = n.type;
  return map;
}

function adjacency(data: ConnectionGraphData): Record<string, string[]> {
  const adj: Record<string, string[]> = {};
  for (const e of data.edges) {
    (adj[e.from] ??= []).push(e.to);
    (adj[e.to] ??= []).push(e.from);
  }
  return adj;
}

/**
 * Accounts hidden because every identity they belong to is collapsed AND they
 * have no other (promo/telegram) links worth showing.
 */
export function computeHidden(
  data: ConnectionGraphData,
  collapsed: Set<string>
): Set<string> {
  const types = nodeTypeMap(data);
  const adj = adjacency(data);
  const hidden = new Set<string>();

  for (const node of data.nodes) {
    if (node.type !== "account") continue;
    const neighbors = adj[node.id] ?? [];
    const identityNeighbors = neighbors.filter((n) => types[n] === "identity");
    const otherNeighbors = neighbors.filter(
      (n) => types[n] === "promo_code" || types[n] === "telegram_link"
    );
    if (
      identityNeighbors.length > 0 &&
      otherNeighbors.length === 0 &&
      identityNeighbors.every((id) => collapsed.has(id))
    ) {
      hidden.add(node.id);
    }
  }
  return hidden;
}

export function toVisNodes(
  data: ConnectionGraphData,
  collapsed: Set<string>,
  hidden: Set<string>
) {
  const adj = adjacency(data);
  return data.nodes
    .filter((n) => !hidden.has(n.id))
    .map((n) => {
      if (n.type === "identity") {
        const childCount = (adj[n.id] ?? []).filter((id) =>
          hidden.has(id)
        ).length;
        const isCollapsed = collapsed.has(n.id);
        return {
          id: n.id,
          label: isCollapsed && childCount ? `${n.label}  (+${childCount})` : n.label,
          shape: "dot",
          size: 28,
          color: { background: "#ede9fe", border: "#7c3aed" },
          font: { size: 14 },
          title: `Личность (${n.fingerprint_type}). Клик — свернуть/развернуть.`,
        };
      }
      if (n.type === "account") {
        const color = PLATFORM_COLOR[n.platform] ?? "#64748b";
        return {
          id: n.id,
          label: `@${n.username}`,
          shape: "box",
          color: { background: "#f8fafc", border: color },
          font: { size: 13 },
          title: `${n.platform} · ${n.followers_count} подписчиков`,
        };
      }
      if (n.type === "promo_code") {
        return {
          id: n.id,
          label: n.code,
          shape: "hexagon",
          size: 14,
          color: { background: "#fef3c7", border: "#f59e0b" },
          font: { size: 12 },
          title: "Промокод",
        };
      }
      return {
        id: n.id,
        label: "Telegram",
        shape: "triangle",
        size: 14,
        color: { background: "#e0f2fe", border: "#229ED9" },
        font: { size: 12 },
        title: n.url,
      };
    });
}

export function toVisEdges(data: ConnectionGraphData, hidden: Set<string>) {
  return data.edges
    .filter((e) => !hidden.has(e.from) && !hidden.has(e.to))
    .map((e, i) => ({ id: `ce${i}`, from: e.from, to: e.to }));
}

// Force-directed layout for free exploration (not hierarchical like G5).
export const CONNECTION_OPTIONS = {
  autoResize: true,
  physics: {
    enabled: true,
    stabilization: { iterations: 150 },
    barnesHut: { springLength: 130, gravitationalConstant: -3000 },
  },
  interaction: { hover: true, dragNodes: true, zoomView: true, tooltipDelay: 150 },
  edges: { color: { color: "#cbd5e1", highlight: "#64748b" }, smooth: false },
  nodes: {
    borderWidth: 2,
    shadow: { enabled: true, size: 8, x: 0, y: 2, color: "rgba(15,23,42,0.15)" },
    font: { face: "Inter, system-ui, sans-serif" },
  },
};

export const CONNECTION_LEGEND = [
  { color: "#7c3aed", label: "Личность (voice/face)" },
  { color: "#E1306C", label: "Instagram" },
  { color: "#10b981", label: "TikTok" },
  { color: "#FF0000", label: "YouTube" },
  { color: "#f59e0b", label: "Промокод" },
  { color: "#229ED9", label: "Telegram" },
];
