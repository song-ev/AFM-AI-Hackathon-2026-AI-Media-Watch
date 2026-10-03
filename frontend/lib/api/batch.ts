import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export interface BatchItem {
  video_id: number;
  url: string;
  overall: string;
  risk_score: number | null;
  incident_id: number | null;
  thumbnail_url?: string;
  caption?: string;
  platform?: string;
  username?: string;
}
export interface BatchProgress {
  batch_id: number;
  kind: "bulk_urls" | "folder" | "source_parse";
  source: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  total: number;
  done: number;
  progress?: number;
  in_progress?: number;
  counts: Record<string, number>;
  flagged: number;
  items: BatchItem[];
  created_at: string;
}

export interface Capabilities {
  youtube: boolean;
  tiktok: boolean;
  instagram: boolean;
  proxy: boolean;
  llm: boolean;
  ocr: boolean;
  ffmpeg: boolean;
}

export function useCapabilitiesQuery() {
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: async () => {
      const { data } = await apiClient.get<Capabilities>(
        "/api/ingestion/capabilities/"
      );
      return data;
    },
    staleTime: 60_000,
  });
}

export function useBulkSubmitMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (text: string) => {
      const { data } = await apiClient.post<{ batch_id: number; total: number }>(
        "/api/ingestion/bulk/",
        { text }
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["batches"] }),
  });
}

export function useParseSourceMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { source_url: string; limit: number }) => {
      const { data } = await apiClient.post<{ batch_id: number; total: number; note: string }>(
        "/api/ingestion/parse/",
        vars
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["batches"] }),
  });
}

export function useCancelBatchMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (batchId: number) => {
      const { data } = await apiClient.delete<BatchProgress>(
        `/api/ingestion/batches/${batchId}/`
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["batches"] }),
  });
}

export function useBatchesQuery() {
  return useQuery({
    queryKey: ["batches"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ batches: BatchProgress[] }>(
        "/api/ingestion/batches/"
      );
      return data.batches;
    },
    // Live-refresh while any batch is still running.
    refetchInterval: (query) => {
      const running = (query.state.data ?? []).some(
        (b) => b.status === "running" || b.status === "pending"
      );
      return running ? 3000 : false;
    },
  });
}
