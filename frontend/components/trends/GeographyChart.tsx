"use client";

import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGeographyQuery } from "@/lib/api/dashboard";

// Primary: horizontal bar chart of regions by account count. (An SVG map of
// Kazakhstan with intensity shading would be a nice optional enhancement, but
// the bar chart conveys the same information and is much faster to build.)
export function GeographyChart() {
  const { data, isLoading, isError } = useGeographyQuery();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">География аккаунтов</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <p className="text-sm text-destructive">Ошибка загрузки.</p>
        ) : !data || data.distribution.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted-foreground">
            Нет данных по регионам.
          </p>
        ) : (
          <ResponsiveContainer
            width="100%"
            height={Math.max(200, data.distribution.length * 32)}
          >
            <BarChart
              layout="vertical"
              data={data.distribution}
              margin={{ left: 16, right: 16 }}
            >
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="region"
                width={120}
                tick={{ fontSize: 12 }}
              />
              <Tooltip />
              <Bar
                dataKey="account_count"
                name="Аккаунты"
                fill="#2563eb"
                radius={[0, 4, 4, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
