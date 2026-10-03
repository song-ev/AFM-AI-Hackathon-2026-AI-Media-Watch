"use client";

import { useState } from "react";
import Link from "next/link";
import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/ui/markdown";
import { RiskBreakdownChart } from "@/components/incident/RiskBreakdownChart";
import {
  useIncidentDecisionMutation,
  type DecisionValue,
  type IncidentDetail,
} from "@/lib/api/incidents";
import { STATUS_LABELS, STATUS_VARIANT, riskTextClass } from "@/lib/incidents-ui";

const DECISIONS: { value: DecisionValue; label: string; className: string }[] = [
  { value: "confirmed", label: "Подтверждено", className: "bg-green-600 hover:bg-green-700 text-white" },
  { value: "false_positive", label: "Ложное срабатывание", className: "bg-destructive hover:bg-destructive/90 text-destructive-foreground" },
  { value: "borderline", label: "Граничный случай", className: "bg-amber-500 hover:bg-amber-600 text-white" },
];

function formatUtc(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { timeZone: "UTC" }) + " UTC";
}

function EvidenceRow({
  hash,
  collectedAt,
  method,
  fileType,
}: {
  hash: string;
  collectedAt: string;
  method: string;
  fileType: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? hash : `${hash.slice(0, 12)}…`;
  return (
    <li className="rounded-md border p-2 text-xs">
      <p className="text-muted-foreground">
        {fileType} · Собрано: {formatUtc(collectedAt)}
      </p>
      <p className="mt-1 break-all font-mono">
        hash: {shown}{" "}
        <button className="underline" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "свернуть" : "развернуть"}
        </button>
        <button
          className="ml-2 inline-flex items-center gap-1 underline"
          onClick={() => {
            navigator.clipboard?.writeText(hash);
            toast.success("Hash скопирован");
          }}
        >
          <Copy className="h-3 w-3" /> копировать
        </button>
      </p>
      <p className="mt-1 text-muted-foreground">{method}</p>
    </li>
  );
}

export function IncidentSidebar({ detail }: { detail: IncidentDetail }) {
  const mutation = useIncidentDecisionMutation(detail.id);
  const currentLabel = detail.analyst_labels[0]; // backend orders by -decided_at
  const [decision, setDecision] = useState<DecisionValue | null>(
    currentLabel?.decision ?? null
  );
  const [comment, setComment] = useState(currentLabel?.comment ?? "");

  const save = () => {
    if (!decision) return;
    mutation.mutate(
      { decision, comment: comment || undefined },
      {
        onSuccess: () => toast.success("Решение сохранено"),
        onError: () => toast.error("Не удалось сохранить решение"),
      }
    );
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Резюме</CardTitle>
        </CardHeader>
        <CardContent>
          {detail.summary_text ? (
            <Markdown>{detail.summary_text}</Markdown>
          ) : (
            <p className="text-sm text-muted-foreground">Резюме отсутствует.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Risk Score</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className={`text-4xl font-bold ${riskTextClass(detail.risk_score)}`}>
            {detail.risk_score.toFixed(0)}
          </p>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">Вклад по источникам</p>
            <RiskBreakdownChart items={detail.risk_breakdown} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Связанные аккаунты и промокоды</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {detail.promo_codes.length === 0 && detail.telegram_links.length === 0 ? (
            <p className="text-muted-foreground">Связей не найдено.</p>
          ) : (
            <ul className="space-y-1">
              {detail.promo_codes.map((p) => (
                <li key={`p${p.id}`}>
                  <span className="font-mono">{p.code}</span>{" "}
                  <span className="text-muted-foreground">· промокод ({p.extracted_from})</span>
                </li>
              ))}
              {detail.telegram_links.map((t) => (
                <li key={`t${t.id}`} className="break-all">
                  {t.url}{" "}
                  <span className="text-muted-foreground">· telegram ({t.extracted_from})</span>
                </li>
              ))}
            </ul>
          )}
          <Link href="/connections" className="text-xs underline">
            Открыть граф связей →
          </Link>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Цепочка хранения доказательств</CardTitle>
        </CardHeader>
        <CardContent>
          {detail.evidence_chain.length === 0 ? (
            <p className="text-sm text-muted-foreground">Записей нет.</p>
          ) : (
            <ul className="space-y-2">
              {detail.evidence_chain.map((e) => (
                <EvidenceRow
                  key={e.id}
                  hash={e.sha256_hash}
                  collectedAt={e.collected_at}
                  method={e.collection_method}
                  fileType={e.file_type}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Решение аналитика</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            Текущий статус:
            <Badge variant={STATUS_VARIANT[detail.status]}>
              {STATUS_LABELS[detail.status]}
            </Badge>
          </div>

          <div className="grid gap-2">
            {DECISIONS.map((d) => (
              <Button
                key={d.value}
                type="button"
                className={decision === d.value ? d.className : ""}
                variant={decision === d.value ? "default" : "outline"}
                onClick={() => setDecision(d.value)}
              >
                {d.label}
              </Button>
            ))}
          </div>

          <Textarea
            placeholder="Комментарий (необязательно)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />

          <Button
            type="button"
            className="w-full"
            disabled={!decision || mutation.isPending}
            onClick={save}
          >
            {mutation.isPending ? "Сохранение…" : "Сохранить решение"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
