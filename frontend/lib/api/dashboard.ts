import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

// --- Trends (C5) -----------------------------------------------------------
export interface TrendsSeriesPoint {
  day: string;
  incidents: number;
  followers_reach: number;
  by_category: Record<string, number>;
}
export interface TrendsResponse {
  days: number;
  since: string;
  series: TrendsSeriesPoint[];
}

export function useTrendsQuery(days: number) {
  return useQuery({
    queryKey: ["dashboard", "trends", days],
    queryFn: async () => {
      const { data } = await apiClient.get<TrendsResponse>(
        "/api/dashboard/trends/",
        { params: { days } }
      );
      return data;
    },
  });
}

// --- Geography (C5) --------------------------------------------------------
export interface GeographyResponse {
  distribution: { region: string; account_count: number; followers: number }[];
}

export function useGeographyQuery() {
  return useQuery({
    queryKey: ["dashboard", "geography"],
    queryFn: async () => {
      const { data } = await apiClient.get<GeographyResponse>(
        "/api/dashboard/geography/"
      );
      return data;
    },
  });
}

// --- Geo points (map of geolocated videos) ---------------------------------
export interface GeoPoint {
  video_id: number;
  incident_id: number | null;
  lat: number;
  lon: number;
  label: string;
  region: string;
  country: string;
  source: string;
  confidence: number;
  risk_score: number;
  platform: string;
  username: string;
  caption: string;
}
export interface GeoRegion {
  region: string;
  count: number;
  lat: number;
  lon: number;
  max_risk: number;
}
export interface GeoPointsResponse {
  points: GeoPoint[];
  regions: GeoRegion[];
  total: number;
}

export function useGeoPointsQuery() {
  return useQuery({
    queryKey: ["dashboard", "geo-points"],
    queryFn: async () => {
      const { data } = await apiClient.get<GeoPointsResponse>(
        "/api/dashboard/geo-points/"
      );
      return data;
    },
  });
}

// --- Keyword trends (C5) ---------------------------------------------------
export interface KeywordTerm {
  term: string;
  category: string;
  status: string;
  added_automatically: boolean;
  added_at: string | null;
}
export interface KeywordTrendsResponse {
  series: { week: string; total: number; by_category: Record<string, number> }[];
  terms?: KeywordTerm[];
  total_terms?: number;
  auto_learned?: number;
}

export function useKeywordTrendsQuery() {
  return useQuery({
    queryKey: ["dashboard", "keyword-trends"],
    queryFn: async () => {
      const { data } = await apiClient.get<KeywordTrendsResponse>(
        "/api/dashboard/keyword-trends/"
      );
      return data;
    },
  });
}

// --- Keyword anomalies (trend prediction / spike detection) ----------------
export interface KeywordAnomalySeriesPoint {
  day: string;
  count: number;
}
export interface KeywordAnomaly {
  term: string;
  category: string;
  region: string;
  observed_on: string;
  window_days: number;
  current_count: number;
  baseline_avg: number;
  pct_change: number;
  z_score: number;
  severity: "low" | "medium" | "high";
  sample_video_ids: number[];
  series?: KeywordAnomalySeriesPoint[];
}
export interface KeywordAnomaliesResponse {
  anomalies: KeywordAnomaly[];
  total: number;
  high: number;
}

export function useKeywordAnomaliesQuery() {
  return useQuery({
    queryKey: ["dashboard", "keyword-anomalies"],
    queryFn: async () => {
      const { data } = await apiClient.get<KeywordAnomaliesResponse>(
        "/api/dashboard/keyword-anomalies/"
      );
      return data;
    },
    refetchInterval: 60_000,
  });
}

// --- ROI (C5) --------------------------------------------------------------
export interface RoiResponse {
  period_days: number;
  model: {
    run_id: number;
    status: string;
    precision: number | null;
    recall: number | null;
    false_positive_rate: number | null;
  } | null;
  confirmed_incidents: number;
  auto_rejected_stage1: number;
  analyst_time_saved_hours: number;
}

export function useRoiQuery() {
  return useQuery({
    queryKey: ["dashboard", "roi"],
    queryFn: async () => {
      const { data } = await apiClient.get<RoiResponse>("/api/dashboard/roi/");
      return data;
    },
  });
}

// --- Dictionary review (F1, + read endpoints added for G7) -----------------
export interface PendingEntry {
  id: number;
  term: string;
  category: string;
  added_automatically: boolean;
  confirmation_count: number;
  added_at: string;
}

export interface DictionaryVersion {
  id: number;
  note: string;
  created_at: string;
  term_count: number;
  snapshot: unknown[];
}

export function usePendingDictionaryQuery() {
  return useQuery({
    queryKey: ["learning", "pending"],
    queryFn: async () => {
      const { data } = await apiClient.get<PendingEntry[]>(
        "/api/learning/dictionary/pending/"
      );
      return data;
    },
  });
}

export function useDictionaryVersionsQuery() {
  return useQuery({
    queryKey: ["learning", "versions"],
    queryFn: async () => {
      const { data } = await apiClient.get<DictionaryVersion[]>(
        "/api/learning/dictionary/versions/"
      );
      return data;
    },
  });
}

export function useDictionaryReviewMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { id: number; decision: "approve" | "reject" }) => {
      const { data } = await apiClient.post(
        `/api/learning/dictionary/${vars.id}/review/`,
        { decision: vars.decision }
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["learning", "pending"] });
      qc.invalidateQueries({ queryKey: ["learning", "versions"] });
    },
  });
}

export function useDictionaryRollbackMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (versionId: number) => {
      const { data } = await apiClient.post(
        `/api/learning/dictionary/rollback/${versionId}/`
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["learning", "versions"] });
    },
  });
}
