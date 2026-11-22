"use client";

import { useCallback } from "react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listAlerts } from "@/lib/api/alerts";
import { AlertTable } from "@/components/alerts/AlertTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function ResolvedAlertsPage() {
  const { data, loading, refetch } = usePoll(
    useCallback(() => listAlerts(), []),
    30_000,
  );

  const resolved = data?.filter((a) => a.status === "resolved") ?? [];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Resolved Alerts</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Historical record of resolved alerts. Read-only.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-slate-700">
            {loading ? "Loading…" : `${resolved.length} resolved alert${resolved.length !== 1 ? "s" : ""}`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-16" />)}</div>
          ) : (
            <AlertTable alerts={resolved} mode="resolved" onRefresh={refetch} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
