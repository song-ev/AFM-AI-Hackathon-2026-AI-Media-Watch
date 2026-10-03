/**
 * Single source of truth for the risk-score colour scale, used consistently
 * across the queue (G3), incident card (G4), reasoning graph (G5) and ROI
 * indicators (G7). Do not re-implement these thresholds elsewhere.
 */
export const RISK_THRESHOLDS = { medium: 40, high: 70 };

export type RiskLevel = "low" | "medium" | "high";

export function riskLevel(score: number): RiskLevel {
  if (score > RISK_THRESHOLDS.high) return "high";
  if (score >= RISK_THRESHOLDS.medium) return "medium";
  return "low";
}

const TEXT: Record<RiskLevel, string> = {
  low: "text-emerald-600",
  medium: "text-amber-600",
  high: "text-red-600",
};

const DOT: Record<RiskLevel, string> = {
  low: "bg-emerald-500",
  medium: "bg-amber-500",
  high: "bg-red-500",
};

// Hex pairs for non-CSS consumers (e.g. vis-network nodes).
const HEX: Record<RiskLevel, { background: string; border: string }> = {
  low: { background: "#d1fae5", border: "#059669" },
  medium: { background: "#fef3c7", border: "#d97706" },
  high: { background: "#fee2e2", border: "#dc2626" },
};

export function riskTextClass(score: number): string {
  return TEXT[riskLevel(score)];
}

export function riskDotClass(score: number): string {
  return DOT[riskLevel(score)];
}

export function riskHex(score: number): { background: string; border: string } {
  return HEX[riskLevel(score)];
}
