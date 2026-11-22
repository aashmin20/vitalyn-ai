"use client";

import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Alert } from "@/lib/types";

interface Props {
  alerts: Alert[];
  loading: boolean;
}

const severityVariant = {
  high: "destructive",
  medium: "warning",
  low: "info",
} as const;

export function ActiveAlertsWidget({ alerts, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-slate-400">
        <AlertTriangle className="w-8 h-8 mb-2 opacity-30" />
        <p className="text-sm">No active alerts</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.slice(0, 5).map((alert) => (
        <div
          key={alert.id}
          className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50 hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-3 min-w-0">
            <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-800 truncate capitalize">
                {alert.alert_type.replace(/_/g, " ")}
              </p>
              <p className="text-xs text-slate-400">
                {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
              </p>
            </div>
          </div>
          <Badge variant={severityVariant[alert.severity] ?? "secondary"} className="shrink-0 ml-2">
            {alert.severity}
          </Badge>
        </div>
      ))}

      {alerts.length > 5 && (
        <Link
          href="/alerts/active"
          className="flex items-center justify-center gap-1 text-xs text-slate-500 hover:text-slate-800 pt-1 transition-colors"
        >
          View all {alerts.length} alerts <ArrowRight className="w-3 h-3" />
        </Link>
      )}
    </div>
  );
}
