import { useMutation, useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export type PipelineStage =
  | "downloading"
  | "screening"
  | "deep_analysis"
  | "completed"
  | "clean"
  | "failed";

export interface VideoGeo {
  lat: number | null;
  lon: number | null;
  label: string;
  region: string;
  country: string;
  source: "file_gps" | "platform_tag" | "ai_inference" | "none";
  confidence: number;
  reasoning?: string;
}

export interface CategoryFinding {
  is_triggered: boolean;
  confidence: number;
  error: string;
  // Module-specific blob (identifiers / brands / links / audio metrics).
  detail: Record<string, unknown>;
}

export interface VideoStatus {
  video_id: number;
  download_status: string;
  screening_status: string | null;
  stage2_status: string | null;
  overall: PipelineStage;
  incident_id: number | null;
  risk_score: number | null;
  processing_time_ms: number;
  geo?: VideoGeo | null;
  categories?: Partial<
    Record<
      "payment" | "brand_link" | "audio_forensics" | "social_context",
      CategoryFinding
    >
  >;
  summary: {
    frames_extracted: number;
    ocr_keywords: string[];
    audio_triggered: boolean;
    signals: { module: string; is_triggered: boolean; confidence: number }[];
  };
}

const TERMINAL: PipelineStage[] = ["completed", "clean", "failed"];

export function useSubmitVideoMutation() {
  return useMutation({
    mutationFn: async (url: string) => {
      const { data } = await apiClient.post<{ video_id: number; status: string }>(
        "/api/ingestion/videos/",
        { url }
      );
      return data;
    },
  });
}

export function useUploadVideoMutation() {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await apiClient.post<{ video_id: number; status: string }>(
        "/api/ingestion/videos/upload/",
        form,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      return data;
    },
  });
}

export function useVideoStatusQuery(videoId: number | null) {
  return useQuery({
    queryKey: ["ingestion", "status", videoId],
    queryFn: async () => {
      const { data } = await apiClient.get<VideoStatus>(
        `/api/ingestion/videos/${videoId}/status/`
      );
      return data;
    },
    enabled: videoId != null,
    // Poll every 2.5s until the pipeline reaches a terminal state.
    refetchInterval: (query) => {
      const overall = query.state.data?.overall;
      return overall && TERMINAL.includes(overall) ? false : 2500;
    },
  });
}
