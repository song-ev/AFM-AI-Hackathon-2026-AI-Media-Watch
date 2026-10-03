"use client";

import {
  CreditCard,
  Dice5,
  AudioLines,
  Link2,
  QrCode,
  AlertTriangle,
  MessagesSquare,
  Bot,
  ShieldAlert,
} from "lucide-react";

import type { CategoryFinding, VideoStatus } from "@/lib/api/ingestion";
import { cn } from "@/lib/utils";

/**
 * Rich render of the new high-value analysis categories (payment identifiers,
 * casino brands / links / QR, audio forensics). Only shows what was found.
 * Accepts the categories map directly so it works from both the analyze
 * pipeline (VideoStatus) and the incident card.
 */
export function CategoryFindings({
  categories,
}: {
  categories?: VideoStatus["categories"];
}) {
  const cats = categories || {};
  const payment = cats.payment;
  const brand = cats.brand_link;
  const audio = cats.audio_forensics;
  const social = cats.social_context;

  const socialShown =
    social &&
    (social.is_triggered ||
      social.error ||
      ((social.detail as any)?.total_comments ?? 0) > 0);

  const anyShown =
    (payment && (payment.is_triggered || payment.error)) ||
    (brand && (brand.is_triggered || brand.error)) ||
    (audio && (audio.is_triggered || audio.error)) ||
    socialShown;
  if (!anyShown) return null;

  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {payment && <PaymentCard f={payment} />}
      {brand && <BrandCard f={brand} />}
      {audio && <AudioCard f={audio} />}
      {socialShown && social && <CommentsCard f={social} />}
    </div>
  );
}

function Shell({
  icon: Icon,
  title,
  confidence,
  triggered,
  error,
  children,
}: {
  icon: typeof CreditCard;
  title: string;
  confidence: number;
  triggered: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border p-3",
        error
          ? "border-amber-200 bg-amber-50/50"
          : triggered
          ? "border-red-200 bg-red-50/60"
          : "border-border bg-card"
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <Icon
          className={cn(
            "h-4 w-4",
            triggered ? "text-red-600" : "text-muted-foreground"
          )}
        />
        <span className="text-sm font-semibold">{title}</span>
        {!error && (
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">
            {Math.round(confidence * 100)}%
          </span>
        )}
      </div>
      {error ? (
        <p className="flex items-start gap-1 text-xs text-amber-700">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> Модуль недоступен:{" "}
          {error}
        </p>
      ) : (
        children
      )}
    </div>
  );
}

function Chip({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "danger" }) {
  return (
    <span
      className={cn(
        "inline-block rounded-md px-1.5 py-0.5 font-mono text-[11px]",
        tone === "danger"
          ? "bg-red-100 text-red-700"
          : "bg-muted text-foreground/80"
      )}
    >
      {children}
    </span>
  );
}

function PaymentCard({ f }: { f: CategoryFinding }) {
  const d = (f.detail || {}) as any;
  const ids = d.identifiers || {};
  return (
    <Shell icon={CreditCard} title="Платёжные реквизиты" confidence={f.confidence} triggered={f.is_triggered} error={f.error}>
      <div className="space-y-1.5 text-xs">
        {ids.phones?.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">Тел/Kaspi:</span>
            {ids.phones.map((p: string) => <Chip key={p} tone="danger">{p}</Chip>)}
          </div>
        ) : null}
        {ids.cards?.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">Карты:</span>
            {ids.cards.map((c: string) => <Chip key={c} tone="danger">{c}</Chip>)}
          </div>
        ) : null}
        {ids.ibans?.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">IBAN:</span>
            {ids.ibans.map((c: string) => <Chip key={c} tone="danger">{c}</Chip>)}
          </div>
        ) : null}
        {ids.crypto?.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">Крипто:</span>
            {ids.crypto.map((c: any, i: number) => <Chip key={i} tone="danger">{c.type}:{String(c.address).slice(0, 10)}…</Chip>)}
          </div>
        ) : null}
        {d.primary_identifier ? (
          <p className="text-[11px] text-muted-foreground">
            → передаётся в bank API для риск-чека
          </p>
        ) : ids.cues?.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">Маркеры оплаты:</span>
            {ids.cues.map((c: string) => <Chip key={c}>{c}</Chip>)}
          </div>
        ) : null}
      </div>
    </Shell>
  );
}

function BrandCard({ f }: { f: CategoryFinding }) {
  const d = (f.detail || {}) as any;
  const brands: string[] = d.brands || [];
  const gambling: string[] = d.gambling_terms || [];
  const links = d.suspicious_links || [];
  const qr = d.qr_codes || [];
  return (
    <Shell icon={Dice5} title="Казино-бренды / ссылки" confidence={f.confidence} triggered={f.is_triggered} error={f.error}>
      <div className="space-y-1.5 text-xs">
        {brands.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">Бренды:</span>
            {brands.map((b) => <Chip key={b} tone="danger">{b}</Chip>)}
          </div>
        ) : null}
        {gambling.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">Азартные термины:</span>
            {gambling.map((b) => <Chip key={b} tone="danger">{b}</Chip>)}
          </div>
        ) : null}
        {links.length ? (
          <div className="space-y-1">
            {links.slice(0, 3).map((l: any) => (
              <div key={l.domain} className="flex items-center gap-1">
                <Link2 className="h-3 w-3 text-red-500" />
                <span className="truncate font-mono text-[11px]">{l.domain}</span>
              </div>
            ))}
          </div>
        ) : null}
        {qr.length ? (
          <div className="space-y-1 rounded-md border border-red-200 bg-red-50/60 p-1.5">
            <div className="flex items-center gap-1 text-[11px] font-medium text-red-600">
              <QrCode className="h-3 w-3" /> QR-коды с экрана ({qr.length})
            </div>
            {qr.slice(0, 3).map((q: any, i: number) => {
              const link = q.link || {};
              const score = Math.round((link.score ?? 0) * 100);
              return (
                <div key={i} className="text-[11px]">
                  <div className="truncate font-mono text-foreground/80">
                    {String(q.data || "").slice(0, 56)}
                  </div>
                  {link.domain ? (
                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Link2 className="h-3 w-3 text-red-500" />
                      <span className="font-mono">{link.domain}</span>
                      <span
                        className={cn(
                          "ml-auto font-mono",
                          score >= 50 ? "text-red-600" : "text-muted-foreground"
                        )}
                      >
                        репутация {score}%
                      </span>
                    </div>
                  ) : null}
                  {link.reasons?.length ? (
                    <p className="text-[10px] text-red-600/80">
                      {link.reasons.join("; ")}
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}
        {!brands.length && !gambling.length && !links.length && !qr.length && (
          <p className="text-[11px] text-muted-foreground">Подозрительного не найдено.</p>
        )}
      </div>
    </Shell>
  );
}

function AudioCard({ f }: { f: CategoryFinding }) {
  const d = (f.detail || {}) as any;
  const pressure = Math.round((d.pressure_score ?? 0) * 100);
  const synth = Math.round((d.synthetic_voice_indicator ?? 0) * 100);
  return (
    <Shell icon={AudioLines} title="Аудио-форензика" confidence={f.confidence} triggered={f.is_triggered} error={f.error}>
      <div className="space-y-1.5 text-xs">
        <Meter label="Давление в подаче" value={pressure} />
        <Meter label="Индикатор синтез. голоса" value={synth} />
        {d.languages?.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">Языки:</span>
            {d.languages.map((l: string) => <Chip key={l}>{l}</Chip>)}
          </div>
        ) : null}
        {d.flags?.length ? (
          <ul className="mt-1 space-y-0.5">
            {d.flags.map((fl: string) => (
              <li key={fl} className="flex items-start gap-1 text-[11px] text-red-600">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{fl}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </Shell>
  );
}

function CommentsCard({ f }: { f: CategoryFinding }) {
  const d = (f.detail || {}) as any;
  const mi = Math.round((d.manipulation_index ?? 0) * 100);
  const sentiment = d.sentiment || {};
  const bots: any[] = d.bot_comments || [];
  const skeptics: any[] = d.skeptic_comments || [];
  return (
    <Shell
      icon={MessagesSquare}
      title="Комментарии: накрутка"
      confidence={f.confidence}
      triggered={f.is_triggered}
      error={f.error}
    >
      <div className="space-y-2 text-xs">
        <Meter label="Индекс накрутки" value={mi} />
        <div className="flex flex-wrap gap-1">
          <Chip tone="danger">боты: {d.bot_count ?? 0}</Chip>
          <Chip>люди: {d.human_count ?? 0}</Chip>
          <Chip>всего: {d.total_comments ?? 0}</Chip>
        </div>
        <div className="flex flex-wrap gap-1 text-[11px] text-muted-foreground">
          <span className="text-emerald-600">+{sentiment.positive ?? 0}</span>
          <span className="text-red-600">−{sentiment.negative ?? 0}</span>
          <span>○{sentiment.neutral ?? 0}</span>
        </div>
        {d.verdict ? (
          <p className="text-[11px] text-muted-foreground">{d.verdict}</p>
        ) : null}
        {bots.slice(0, 2).map((c, i) => (
          <p key={`b${i}`} className="flex items-start gap-1 text-[11px] text-red-600">
            <Bot className="mt-0.5 h-3 w-3 shrink-0" />
            <span className="line-clamp-2">«{c.text}»</span>
          </p>
        ))}
        {skeptics.slice(0, 2).map((c, i) => (
          <p key={`s${i}`} className="flex items-start gap-1 text-[11px] text-amber-700">
            <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0" />
            <span className="line-clamp-2">«{c.text}»</span>
          </p>
        ))}
      </div>
    </Shell>
  );
}

function Meter({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-0.5 flex justify-between text-[11px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono">{value}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full",
            value >= 70 ? "bg-red-500" : value >= 40 ? "bg-amber-500" : "bg-emerald-500"
          )}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}
