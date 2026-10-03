import { Instagram, Music2, Video as VideoIcon, Youtube } from "lucide-react";
import type { ComponentType } from "react";

import type { IncidentStatus } from "@/lib/api/incidents";

// Risk-score scale lives in one place; re-exported here for convenience.
export {
  RISK_THRESHOLDS,
  riskTextClass,
  riskDotClass,
  riskHex,
  riskLevel,
} from "@/lib/utils/riskColor";

export const STATUS_LABELS: Record<IncidentStatus, string> = {
  pending_review: "На проверке",
  confirmed: "Подтверждён",
  false_positive: "Ложное",
  borderline: "Пограничный",
};

export const STATUS_VARIANT: Record<
  IncidentStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending_review: "secondary",
  confirmed: "destructive",
  false_positive: "outline",
  borderline: "default",
};

const PLATFORM_ICON: Record<string, ComponentType<{ className?: string }>> = {
  instagram: Instagram,
  youtube: Youtube,
  tiktok: Music2,
};

export function platformIcon(code: string) {
  return PLATFORM_ICON[code] ?? VideoIcon;
}

export function PlatformIcon({ code, className }: { code: string; className?: string }) {
  const Icon = PLATFORM_ICON[code] ?? VideoIcon;
  return <Icon className={className} />;
}

export function formatFollowers(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
