import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";

const STAGES = [
  { n: 1, title: "Первичный скрининг", desc: "Быстрый отсев чистого контента" },
  { n: 2, title: "Глубокий анализ", desc: "Транскрипция, OCR, идентичность" },
  { n: 3, title: "Синтез и вывод", desc: "Risk score, граф рассуждений" },
  { n: 4, title: "Самообучение", desc: "Словарь кодовых слов, дообучение" },
];

const METRICS = [
  { value: "> 85%", label: "Precision" },
  { value: "> 90%", label: "Recall" },
  { value: "< 10%", label: "False Positive Rate" },
  { value: "< 200 мс", label: "SLA ответа для банков" },
];

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-background px-6 py-16">
      <div className="w-full max-w-4xl space-y-12">
        <header className="space-y-4 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border bg-card px-4 py-1.5 text-sm text-muted-foreground">
            <ShieldCheck className="h-4 w-4 text-primary" />
            АФМ Казахстана · мониторинг соцсетей
          </div>
          <h1 className="text-4xl font-bold tracking-tight">AI Media Watch</h1>
          <p className="mx-auto max-w-2xl text-muted-foreground">
            Система выявления нелегальных казино, финансовых пирамид и
            инвест-мошенничества в Instagram, TikTok и YouTube. Объясняемый
            ИИ-конвейер из четырёх этапов.
          </p>
          <Button asChild size="lg">
            <Link href="/login">Войти в систему</Link>
          </Button>
        </header>

        {/* Четыре этапа архитектуры (статичная схема). */}
        <section>
          <div className="flex flex-col gap-3 md:flex-row md:items-stretch">
            {STAGES.map((stage, i) => (
              <div
                key={stage.n}
                className="flex flex-1 items-center gap-3 md:flex-col md:items-stretch"
              >
                <div className="flex-1 rounded-lg border bg-card p-4">
                  <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                    {stage.n}
                  </div>
                  <p className="text-sm font-medium">{stage.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{stage.desc}</p>
                </div>
                {i < STAGES.length - 1 && (
                  <ArrowRight className="h-5 w-5 shrink-0 rotate-90 text-muted-foreground md:rotate-0 md:self-center" />
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Целевые метрики (раздел 4.4). */}
        <section>
          <h2 className="mb-3 text-center text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Целевые метрики
          </h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {METRICS.map((m) => (
              <div
                key={m.label}
                className="rounded-lg border bg-card p-4 text-center"
              >
                <p className="text-2xl font-bold text-primary">{m.value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{m.label}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
