"use client";

import { useCallback } from "react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listAlerts } from "@/lib/api/alerts";
import { AlertTable } from "@/components/alerts/AlertTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function ActiveAlertsPage() {
  const { data, loading, refetch } = usePoll(
    useCallback(() => listAlerts(), []),
    10_000,
  );

  const active = data?.filter((a) => a.status === "active") ?? [];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Active Alerts</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Unacknowledged alerts requiring attention. Acknowledge to mark a potential fall as seen and under review; resolve it only after verifying the patient is safe.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-slate-700">
            {loading ? "Loading…" : `${active.length} active alert${active.length !== 1 ? "s" : ""}`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-16" />)}</div>
          ) : (
            <AlertTable alerts={active} mode="active" onRefresh={refetch} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
