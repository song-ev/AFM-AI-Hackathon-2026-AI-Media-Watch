import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export type IncidentStatus =
  | "pending_review"
  | "confirmed"
  | "false_positive"
  | "borderline";

// Mirrors IncidentListSerializer (backend C1).
export interface VideoCompact {
  thumbnail_url: string;
  platform: string;
  posted_at: string | null;
  caption: string;
}

export interface SocialAccountCompact {
  username: string;
  followers_count: number;
}

export interface IncidentListItem {
  id: number;
  video: VideoCompact;
  social_account: SocialAccountCompact;
  risk_score: number;
  priority_score: number;
  status: IncidentStatus;
  created_at: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface IncidentStats {
  queue_total: number;
  total: number;
  status_breakdown: Record<string, number>;
  avg_risk_score_24h: number;
}

export interface IncidentFilters {
  platform?: string;
  status?: string;
  riskMin: number;
  riskMax: number;
  dateFrom?: string;
  dateTo?: string;
  search: string;
}

export const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 30_000;

function buildParams(filters: IncidentFilters, page: number) {
  const params: Record<string, string | number> = {
    page,
    page_size: PAGE_SIZE,
    risk_score_min: filters.riskMin,
    risk_score_max: filters.riskMax,
  };
  if (filters.platform) params.platform = filters.platform;
  if (filters.status) params.status = filters.status;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  if (filters.search.trim()) params.search = filters.search.trim();
  return params;
}

export function useIncidentsQuery(filters: IncidentFilters, page: number) {
  return useQuery({
    queryKey: ["incidents", filters, page],
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<IncidentListItem>>(
        "/api/incidents/",
        { params: buildParams(filters, page) }
      );
      return data;
    },
    placeholderData: keepPreviousData, // avoid flicker when paging/filtering
    refetchInterval: POLL_INTERVAL_MS, // new incidents arrive via Celery
  });
}

/**
 * Infinite/virtualized variant of the queue query. Pages are fetched on demand
 * as the analyst scrolls (see the virtualized list in queue/page.tsx), which
 * keeps the DOM and network footprint flat even with tens of thousands of
 * incidents. Numbered paging (`useIncidentsQuery`) is kept for any non-scroll
 * consumers.
 */
export function useInfiniteIncidentsQuery(filters: IncidentFilters) {
  return useInfiniteQuery({
    queryKey: ["incidents", "infinite", filters],
    queryFn: async ({ pageParam }) => {
      const { data } = await apiClient.get<Paginated<IncidentListItem>>(
        "/api/incidents/",
        { params: buildParams(filters, pageParam) }
      );
      return data;
    },
    initialPageParam: 1,
    // The API returns an absolute `next` URL; we only need to know whether one
    // more page exists, then ask for the next sequential page number.
    getNextPageParam: (lastPage, allPages) =>
      lastPage.next ? allPages.length + 1 : undefined,
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useIncidentStatsQuery() {
  return useQuery({
    queryKey: ["incidents", "stats"],
    queryFn: async () => {
      const { data } = await apiClient.get<IncidentStats>(
        "/api/incidents/stats/"
      );
      return data;
    },
    refetchInterval: POLL_INTERVAL_MS,
  });
}

// --- Incident detail (subset used by the card host: player + timeline) -----
export interface TranscriptFlag {
  phrase: string;
  start_sec: number | null;
  end_sec: number | null;
  category: string;
  severity: number;
}

export interface FakeScreenshotDetection {
  id: number;
  frame_timestamp_sec: number | null;
  bank_name: string;
  is_fake: boolean;
  confidence: number;
  artifacts_found: string[];
}

export interface RiskBreakdownItem {
  source: string;
  label: string;
  node_type: string;
  status: string;
  score_contribution: number | null;
  confidence: number | null;
}

export interface EvidenceEntry {
  id: number;
  file_type: string;
  file_path: string;
  sha256_hash: string;
  collected_at: string;
  collection_method: string;
}

export interface PromoCode {
  id: number;
  code: string;
  extracted_from: string;
}

export interface TelegramLink {
  id: number;
  url: string;
  extracted_from: string;
}

export interface AnalystLabel {
  id: number;
  decision: DecisionValue;
  comment: string | null;
  analyst: string;
  decided_at: string;
}

export interface IncidentDetail {
  id: number;
  status: IncidentStatus;
  summary_text: string;
  risk_score: number;
  priority_score: number;
  created_at: string;
  video: {
    url: string;
    local_file_path: string | null;
    thumbnail_url: string;
    caption: string;
    duration_seconds: number | null;
    platform: { code: string; name: string };
  };
  social_account: SocialAccountCompact;
  risk_breakdown: RiskBreakdownItem[];
  transcript_flags: TranscriptFlag[];
  fake_screenshots: FakeScreenshotDetection[];
  evidence_chain: EvidenceEntry[];
  geo: import("@/lib/api/ingestion").VideoGeo | null;
  categories: import("@/lib/api/ingestion").VideoStatus["categories"];
  promo_codes: PromoCode[];
  telegram_links: TelegramLink[];
  analyst_labels: AnalystLabel[];
}

export function useIncidentDetailQuery(incidentId: number) {
  return useQuery({
    queryKey: ["incident", incidentId],
    queryFn: async () => {
      const { data } = await apiClient.get<IncidentDetail>(
        `/api/incidents/${incidentId}/`
      );
      return data;
    },
    enabled: Number.isFinite(incidentId),
  });
}

export type DecisionValue = "confirmed" | "false_positive" | "borderline";

export function useIncidentDecisionMutation(incidentId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { decision: DecisionValue; comment?: string }) => {
      const { data } = await apiClient.post(
        `/api/incidents/${incidentId}/decision/`,
        payload
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incident", incidentId] });
      qc.invalidateQueries({ queryKey: ["incidents"] }); // queue + stats
    },
  });
}

// --- Reasoning graph (C3) ---------------------------------------------------
export type ReasoningNodeType =
  | "stage1_signal"
  | "stage2_signal"
  | "synthesis"
  | "verdict";

export type ReasoningNodeStatus = "triggered" | "clean" | "not_applicable";

export interface ReasoningNode {
  id: string;
  type: ReasoningNodeType;
  label: string;
  status: ReasoningNodeStatus;
  score_contribution: number;
  timestamp_sec: number | null;
  explanation: string;
  confidence?: number | null;
}

export interface ReasoningEdge {
  from: string;
  to: string;
  weight: number;
}

export interface ReasoningVerdict {
  risk_score: number;
  label: string;
  threshold: number;
}

export interface ReasoningGraphData {
  nodes: ReasoningNode[];
  edges: ReasoningEdge[];
  verdict: ReasoningVerdict;
}

export function useReasoningGraphQuery(incidentId: number) {
  return useQuery({
    queryKey: ["incident", incidentId, "reasoning-graph"],
    queryFn: async () => {
      const { data } = await apiClient.get<ReasoningGraphData>(
        `/api/incidents/${incidentId}/reasoning-graph/`
      );
      return data;
    },
    enabled: Number.isFinite(incidentId),
  });
}
