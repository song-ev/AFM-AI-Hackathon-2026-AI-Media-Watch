import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export interface LiveAlert {
  id: number;
  chunk_index: number;
  risk_score: number;
  reasons: string[];
  incident_id: number | null;
  created_at: string;
}
export interface LiveSession {
  id: number;
  url: string;
  platform: string;
  title: string;
  streamer: string;
  status: "pending" | "live" | "stopped" | "ended" | "failed";
  chunk_seconds: number;
  chunks_captured: number;
  alerts_count: number;
  max_risk_score: number;
  last_chunk_at: string | null;
  last_chunk_url: string;
  note: string;
  created_at: string;
  alerts: LiveAlert[];
}

export function useStartLiveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { url: string; chunk_seconds: number }) => {
      const { data } = await apiClient.post<LiveSession>(
        "/api/ingestion/live/",
        vars
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["live"] }),
  });
}

export function useStopLiveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await apiClient.delete<LiveSession>(
        `/api/ingestion/live/${id}/`
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["live"] }),
  });
}

export function useLiveSessionsQuery() {
  return useQuery({
    queryKey: ["live"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ sessions: LiveSession[] }>(
        "/api/ingestion/live/list/"
      );
      return data.sessions;
    },
    refetchInterval: (query) => {
      const active = (query.state.data ?? []).some(
        (s) => s.status === "live" || s.status === "pending"
      );
      return active ? 4000 : false;
    },
  });
}
