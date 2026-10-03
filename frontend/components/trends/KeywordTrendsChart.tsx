"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Info, Sparkles, BookOpen } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip as UITooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useKeywordTrendsQuery } from "@/lib/api/dashboard";

const CATEGORY_COLORS: Record<string, string> = {
  guarantee: "#dc2626",
  urgency: "#f59e0b",
  referral: "#8b5cf6",
  casino_slang: "#0ea5e9",
  other: "#94a3b8",
};
const CATEGORY_LABEL: Record<string, string> = {
  guarantee: "Гарантии дохода",
  urgency: "Срочность",
  referral: "Рефералки",
  casino_slang: "Казино-сленг",
  other: "Прочее",
};

export function KeywordTrendsChart() {
  const { data, isLoading, isError } = useKeywordTrendsQuery();

  const categories = data
    ? Array.from(new Set(data.series.flatMap((s) => Object.keys(s.by_category))))
    : [];
  const rows = data
    ? data.series.map((s) => ({ week: s.week, ...s.by_category }))
    : [];
  const terms = data?.terms ?? [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Динамика кодовых слов</CardTitle>
          <TooltipProvider>
            <UITooltip>
              <TooltipTrigger asChild>
                <button className="text-muted-foreground hover:text-foreground">
                  <Info className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                Новые фрод-термины, которые система выучила из подтверждённых
                инцидентов (Stage-4 само-обучение). Когда одинаковая фраза
                повторяется в подтверждённых делах, она добавляется в словарь —
                график показывает рост словаря по неделям и категориям.
              </TooltipContent>
            </UITooltip>
          </TooltipProvider>
        </div>
        <p className="text-xs text-muted-foreground">
          Сленг мошенников, выученный из подтверждённых инцидентов
          {data?.total_terms != null && (
            <>
              {" "}· всего {data.total_terms}
              {data.auto_learned ? (
                <span className="ml-1 inline-flex items-center gap-0.5 text-violet-600">
                  <Sparkles className="h-3 w-3" />
                  {data.auto_learned} авто
                </span>
              ) : null}
            </>
          )}
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <p className="text-sm text-destructive">Ошибка загрузки.</p>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <BookOpen className="h-7 w-7 text-muted-foreground/50" />
            <p className="text-sm font-medium">Словарь пока пуст</p>
            <p className="max-w-sm text-xs text-muted-foreground">
              Термины появляются, когда аналитик подтверждает инциденты и
              одинаковые фразы повторяются. Для демо засейте словарь:
              <code className="mx-1 rounded bg-muted px-1 py-0.5">
                manage.py seed_keyword_dictionary
              </code>
            </p>
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={224}>
              <BarChart data={rows} margin={{ left: -10, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="week"
                  tickFormatter={(d: string) => d.slice(5)}
                  tick={{ fontSize: 12 }}
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Legend formatter={(v: string) => CATEGORY_LABEL[v] ?? v} />
                {categories.map((cat) => (
                  <Bar
                    key={cat}
                    dataKey={cat}
                    stackId="kw"
                    name={cat}
                    fill={CATEGORY_COLORS[cat] ?? "#94a3b8"}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>

            {/* Term cloud — the actual learned slang (the wow detail). */}
            {terms.length > 0 && (
              <div className="mt-3">
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                  Недавно выученные термины
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {terms.slice(0, 30).map((t, i) => {
                    const color = CATEGORY_COLORS[t.category] ?? "#94a3b8";
                    return (
                      <span
                        key={`${t.term}-${i}`}
                        title={`${CATEGORY_LABEL[t.category] ?? t.category}${
                          t.added_automatically ? " · выучено автоматически" : ""
                        }`}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition hover:scale-105"
                        )}
                        style={{
                          borderColor: `${color}55`,
                          backgroundColor: `${color}12`,
                          color,
                        }}
                      >
                        {t.added_automatically && <Sparkles className="h-2.5 w-2.5" />}
                        {t.term}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
