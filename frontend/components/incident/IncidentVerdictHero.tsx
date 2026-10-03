"use client";

import { Dice5, TrendingUp, CreditCard, AudioLines, ShieldAlert, ShieldCheck } from "lucide-react";

import { RiskRing } from "@/components/ui/RiskRing";
import { Markdown } from "@/components/ui/markdown";
import { cn } from "@/lib/utils";
import { riskLevel } from "@/lib/utils/riskColor";
import type { IncidentDetail } from "@/lib/api/incidents";

const VERDICT_THRESHOLD = 60;

/** Infer a human scheme type from the evidence we have. */
function schemeType(detail: IncidentDetail): { label: string; icon: typeof Dice5 } {
  const cats = detail.categories || {};
  const brand = cats.brand_link?.detail as any;
  if (brand && (brand.brands?.length || brand.gambling_terms?.length || brand.qr_codes?.length)) {
    return { label: "Незаконное казино / ставки", icon: Dice5 };
  }
  const flagCats = new Set(detail.transcript_flags.map((f) => f.category));
  if (flagCats.has("referral")) return { label: "Финансовая пирамида", icon: TrendingUp };
  if (flagCats.has("guarantee")) return { label: "Инвестиционное мошенничество", icon: TrendingUp };
  if (cats.payment?.is_triggered) return { label: "Сбор платежей / мошенничество", icon: CreditCard };
  return { label: "Подозрительный контент", icon: ShieldAlert };
}

/** Top evidence chips from the risk breakdown + categories. */
function evidenceChips(detail: IncidentDetail): { icon: typeof Dice5; text: string }[] {
  const chips: { icon: typeof Dice5; text: string }[] = [];
  const cats = detail.categories || {};
  const brand = cats.brand_link?.detail as any;
  if (brand?.brands?.length) chips.push({ icon: Dice5, text: `Бренды: ${brand.brands.slice(0, 3).join(", ")}` });
  else if (brand?.gambling_terms?.length) chips.push({ icon: Dice5, text: `Казино-сленг: ${brand.gambling_terms.slice(0, 3).join(", ")}` });
  const pay = cats.payment?.detail as any;
  if (pay?.primary_identifier) chips.push({ icon: CreditCard, text: `Реквизиты: ${pay.primary_identifier}` });
  const audio = cats.audio_forensics?.detail as any;
  if (audio?.flags?.length) chips.push({ icon: AudioLines, text: audio.flags[0] });
  if (detail.telegram_links.length) chips.push({ icon: TrendingUp, text: `${detail.telegram_links.length} Telegram-ссылок` });
  return chips.slice(0, 4);
}

export function IncidentVerdictHero({ detail }: { detail: IncidentDetail }) {
  const risk = detail.risk_score;
  const triggered = risk >= VERDICT_THRESHOLD;
  const scheme = schemeType(detail);
  const SchemeIcon = scheme.icon;
  const chips = evidenceChips(detail);
  const level = riskLevel(risk);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border p-5",
        triggered
          ? "border-red-200 bg-gradient-to-br from-red-50 to-background"
          : level === "medium"
          ? "border-amber-200 bg-gradient-to-br from-amber-50 to-background"
          : "border-emerald-200 bg-gradient-to-br from-emerald-50 to-background"
      )}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        {/* Animated gauge (wow) */}
        <RiskRing score={risk} size={104} stroke={9} label="риск" />

        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-semibold",
                triggered ? "bg-red-600 text-white" : "bg-emerald-600 text-white"
              )}
            >
              {triggered ? <ShieldAlert className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
              {triggered ? "Триггерный контент" : "Низкий риск"}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 text-sm font-medium">
              <SchemeIcon className="h-4 w-4 text-primary" />
              {scheme.label}
            </span>
          </div>

          {detail.summary_text && (
            <div className="text-sm text-muted-foreground">
              <Markdown>{detail.summary_text}</Markdown>
            </div>
          )}

          {chips.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {chips.map((c, i) => {
                const Icon = c.icon;
                return (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700"
                  >
                    <Icon className="h-3 w-3" /> {c.text}
                  </span>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
