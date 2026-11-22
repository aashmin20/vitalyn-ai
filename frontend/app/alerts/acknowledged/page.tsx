"use client";

import { useCallback } from "react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listAlerts } from "@/lib/api/alerts";
import { AlertTable } from "@/components/alerts/AlertTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function AcknowledgedAlertsPage() {
  const { data, loading, refetch } = usePoll(
    useCallback(() => listAlerts(), []),
    15_000,
  );

  const acknowledged = data?.filter((a) => a.status === "acknowledged") ?? [];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Acknowledged Alerts</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Alerts seen by staff. Resolve only after physically verifying patient safety.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-slate-700">
            {loading ? "Loading…" : `${acknowledged.length} acknowledged alert${acknowledged.length !== 1 ? "s" : ""}`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-16" />)}</div>
          ) : (
            <AlertTable alerts={acknowledged} mode="acknowledged" onRefresh={refetch} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
