import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export interface IdentityNode {
  id: string;
  type: "identity";
  label: string;
  fingerprint_type: "voice" | "face";
  accounts: { id: string; username: string }[];
}

export interface AccountNode {
  id: string;
  type: "account";
  label: string;
  username: string;
  followers_count: number;
  platform: string;
}

export interface PromoNode {
  id: string;
  type: "promo_code";
  label: string;
  code: string;
}

export interface TelegramNode {
  id: string;
  type: "telegram_link";
  label: string;
  url: string;
}

export type ConnectionNode =
  | IdentityNode
  | AccountNode
  | PromoNode
  | TelegramNode;

export interface ConnectionEdge {
  from: string;
  to: string;
}

export interface ConnectionGraphData {
  nodes: ConnectionNode[];
  edges: ConnectionEdge[];
  truncated?: boolean;
}

export interface ConnectionFilters {
  account?: string;
  promo_code?: string;
  telegram_link?: string;
  identity?: string;
}

export interface SearchResult {
  type: "account" | "promo_code" | "telegram_link";
  value: string;
  label: string;
}

export function useConnectionGraphQuery(filters: ConnectionFilters) {
  return useQuery({
    queryKey: ["connections", "graph", filters],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (filters.account) params.account = filters.account;
      if (filters.promo_code) params.promo_code = filters.promo_code;
      if (filters.telegram_link) params.telegram_link = filters.telegram_link;
      if (filters.identity) params.identity = filters.identity;
      const { data } = await apiClient.get<ConnectionGraphData>(
        "/api/connections/graph/",
        { params }
      );
      return data;
    },
  });
}

export function useConnectionSearchQuery(q: string) {
  return useQuery({
    queryKey: ["connections", "search", q],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results: SearchResult[] }>(
        "/api/connections/search/",
        { params: { q } }
      );
      return data.results;
    },
    enabled: q.trim().length >= 2,
  });
}
