"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RiskBreakdownItem } from "@/lib/api/incidents";

// Weight for each source: explicit score_contribution, else confidence (0-1 -> %).
function contribution(item: RiskBreakdownItem): number {
  if (item.score_contribution != null) return Math.max(0, item.score_contribution);
  if (item.confidence != null) return Math.max(0, item.confidence * 100);
  return 0;
}

export function RiskBreakdownChart({ items }: { items: RiskBreakdownItem[] }) {
  const withValues = items
    .map((it) => ({ label: it.label, status: it.status, value: contribution(it) }))
    .filter((it) => it.value > 0);

  if (withValues.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">Нет данных о вкладах.</p>
    );
  }

  const total = withValues.reduce((a, b) => a + b.value, 0) || 1;
  const data = withValues
    .map((it) => ({ ...it, pct: Math.round((it.value / total) * 100) }))
    .sort((a, b) => b.pct - a.pct);

  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 34)}>
      <BarChart layout="vertical" data={data} margin={{ left: 8, right: 24 }}>
        <XAxis type="number" hide domain={[0, 100]} />
        <YAxis
          type="category"
          dataKey="label"
          width={130}
          tick={{ fontSize: 12 }}
        />
        <Tooltip formatter={(v: number) => `${v}%`} />
        <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.status === "triggered" ? "#dc2626" : "#94a3b8"}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
