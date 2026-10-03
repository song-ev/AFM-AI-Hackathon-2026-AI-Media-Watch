"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { IncidentListItem } from "@/lib/api/incidents";
import {
  STATUS_LABELS,
  STATUS_VARIANT,
  formatFollowers,
  PlatformIcon,
  riskDotClass,
  riskTextClass,
} from "@/lib/incidents-ui";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function IncidentCard({ incident }: { incident: IncidentListItem }) {
  return (
    <Link href={`/incidents/${incident.id}`} className="block">
      <Card className="overflow-hidden transition-colors hover:bg-accent/40">
        <div className="relative aspect-video w-full bg-muted">
          {incident.video.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={incident.video.thumbnail_url}
              alt=""
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-muted-foreground">
              <PlatformIcon code={incident.video.platform} className="h-8 w-8" />
            </div>
          )}
          <div className="absolute left-2 top-2 rounded-md bg-background/80 p-1">
            <PlatformIcon code={incident.video.platform} className="h-4 w-4" />
          </div>
          <Badge
            variant={STATUS_VARIANT[incident.status]}
            className="absolute right-2 top-2"
          >
            {STATUS_LABELS[incident.status]}
          </Badge>
        </div>

        <CardContent className="space-y-2 p-4">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm font-medium">
              @{incident.social_account.username}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {formatFollowers(incident.social_account.followers_count)}
            </span>
          </div>

          <p className="line-clamp-2 min-h-[2.5rem] text-xs text-muted-foreground">
            {incident.video.caption || "—"}
          </p>

          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${riskDotClass(
                  incident.risk_score
                )}`}
              />
              <span className={`text-sm font-semibold ${riskTextClass(incident.risk_score)}`}>
                {incident.risk_score.toFixed(0)}
              </span>
              <span className="text-xs text-muted-foreground">
                · приоритет {incident.priority_score.toFixed(1)}
              </span>
            </div>
            <span className="text-xs text-muted-foreground">
              {formatDate(incident.created_at)}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export function IncidentCardSkeleton() {
  return (
    <Card className="overflow-hidden">
      <div className="aspect-video w-full animate-pulse bg-muted" />
      <CardContent className="space-y-2 p-4">
        <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
        <div className="h-3 w-full animate-pulse rounded bg-muted" />
        <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
      </CardContent>
    </Card>
  );
}
