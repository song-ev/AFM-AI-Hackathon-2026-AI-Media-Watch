"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NetworkGraph } from "@/components/graph/NetworkGraph";
import { apiClient } from "@/lib/api/client";
import {
  useConnectionGraphQuery,
  type AccountNode,
  type ConnectionFilters,
} from "@/lib/api/connections";
import {
  CONNECTION_LEGEND,
  CONNECTION_OPTIONS,
  computeHidden,
  toVisEdges,
  toVisNodes,
} from "@/lib/connection-graph-vis";

interface ConnectionGraphProps {
  filters?: ConnectionFilters;
  compact?: boolean;
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 rounded-md border bg-card p-2 text-xs">
      {CONNECTION_LEGEND.map((l) => (
        <span key={l.label} className="flex items-center gap-1.5">
          <span
            className="inline-block h-3 w-3 rounded-full"
            style={{ backgroundColor: l.color }}
          />
          {l.label}
        </span>
      ))}
    </div>
  );
}

export function ConnectionGraph({ filters = {}, compact }: ConnectionGraphProps) {
  const router = useRouter();
  const { data, isLoading, isError } = useConnectionGraphQuery(filters);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<AccountNode | null>(null);

  const { visNodes, visEdges } = useMemo(() => {
    if (!data) return { visNodes: [], visEdges: [] };
    const hidden = computeHidden(data, collapsed);
    return {
      visNodes: toVisNodes(data, collapsed, hidden),
      visEdges: toVisEdges(data, hidden),
    };
  }, [data, collapsed]);

  const handleNodeClick = (id: string) => {
    const node = data?.nodes.find((n) => n.id === id);
    if (!node) return;
    if (node.type === "identity") {
      setCollapsed((prev) => {
        const next = new Set(prev);
        next.has(id) ? next.delete(id) : next.add(id);
        return next;
      });
    } else if (node.type === "account") {
      setSelected(node);
    }
  };

  const openIncident = async (username: string) => {
    try {
      const { data: page } = await apiClient.get("/api/incidents/", {
        params: { search: username, page_size: 1 },
      });
      const incident = page.results?.[0];
      if (incident) {
        router.push(`/incidents/${incident.id}`);
      } else {
        toast.info("У аккаунта нет связанных инцидентов");
      }
    } catch {
      toast.error("Не удалось найти инцидент");
    }
  };

  const height = compact ? "h-[360px]" : "h-[600px]";

  if (isLoading) {
    return (
      <div className={`flex ${height} flex-col items-center justify-center gap-3 rounded-lg border bg-card text-muted-foreground`}>
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        <p className="text-sm">Загрузка графа связей…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={`flex ${height} items-center justify-center rounded-lg border bg-card text-sm text-destructive`}>
        Не удалось загрузить граф связей.
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className={`flex ${height} items-center justify-center rounded-lg border bg-card text-sm text-muted-foreground`}>
        {filters.account
          ? "У этого аккаунта нет обнаруженных связей."
          : "Связи не обнаружены."}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <NetworkGraph
        nodes={visNodes}
        edges={visEdges}
        options={CONNECTION_OPTIONS}
        onNodeClick={handleNodeClick}
        className={`${height} w-full rounded-lg border bg-card`}
      />
      <Legend />

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>@{selected?.username}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-3 text-sm">
              <p className="text-muted-foreground">
                {selected.platform} · {selected.followers_count} подписчиков
              </p>
              <Button
                className="w-full"
                onClick={() => {
                  void openIncident(selected.username);
                  setSelected(null);
                }}
              >
                Открыть карточку инцидента
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
