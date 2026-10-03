"use client";

import { AnomalyAlerts } from "@/components/trends/AnomalyAlerts";
import { DictionaryReviewDialog } from "@/components/trends/DictionaryReviewDialog";
import { GeographyChart } from "@/components/trends/GeographyChart";
import { IncidentGeoMap } from "@/components/trends/IncidentGeoMap";
import { KeywordTrendsChart } from "@/components/trends/KeywordTrendsChart";
import { RoiCards } from "@/components/trends/RoiCards";
import { SchemeGrowthChart } from "@/components/trends/SchemeGrowthChart";

// Access: this route is afm_lead/system_admin only. The AuthGuard wrapping the
// dashboard layout (G2) already redirects an analyst here back to /queue with a
// "недостаточно прав" toast — see requiredRolesForPath('/trends'). No extra
// page-level guard is required.
export default function TrendsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Дашборд трендов</h1>
          <p className="text-sm text-muted-foreground">
            Аналитика для руководства АФМ.
          </p>
        </div>
        <DictionaryReviewDialog />
      </div>

      <AnomalyAlerts />

      <section>
        <h2 className="mb-2 text-sm font-semibold text-muted-foreground">
          ROI системы
        </h2>
        <RoiCards />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <SchemeGrowthChart />
        <GeographyChart />
      </div>

      <IncidentGeoMap />

      <KeywordTrendsChart />
    </div>
  );
}
