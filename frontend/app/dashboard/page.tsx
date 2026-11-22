"use client";

import { useCallback } from "react";
import { BedDouble, AlertTriangle, Activity, TrendingUp } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { getOverview, getEventSummary } from "@/lib/api/dashboard";
import { listAlerts } from "@/lib/api/alerts";
import { listJobs } from "@/lib/api/jobs";
import { StatCard } from "@/components/dashboard/StatCard";
import { OccupancyChart } from "@/components/dashboard/OccupancyChart";
import { ActiveAlertsWidget } from "@/components/dashboard/ActiveAlertsWidget";
import { RecentJobsWidget } from "@/components/dashboard/RecentJobsWidget";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

export default function DashboardPage() {
  const { data: overview, loading: overviewLoading } = usePoll(
    useCallback(() => getOverview(), []),
    30_000,
  );

  const { data: eventSummary } = usePoll(
    useCallback(() => getEventSummary(), []),
    15_000,
  );

  const { data: alerts, loading: alertsLoading } = usePoll(
    useCallback(() => listAlerts(), []),
    10_000,
  );

  const { data: jobs, loading: jobsLoading } = usePoll(
    useCallback(() => listJobs(), []),
    15_000,
  );

  const activeAlerts = alerts?.filter((a) => a.status === "active") ?? [];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Command Centre</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Real-time hospital bed occupancy and fall alert monitoring
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Beds"
          value={overview?.total_beds ?? null}
          icon={BedDouble}
          loading={overviewLoading}
          color="default"
        />
        <StatCard
          label="Occupied"
          value={overview?.occupied_beds ?? null}
          icon={BedDouble}
          loading={overviewLoading}
          color="amber"
          sub={overview ? `${overview.occupied_percentage}%` : undefined}
        />
        <StatCard
          label="Vacant"
          value={overview?.vacant_beds ?? null}
          icon={BedDouble}
          loading={overviewLoading}
          color="green"
        />
        <StatCard
          label="Active Alerts"
          value={overview?.active_alerts ?? null}
          icon={AlertTriangle}
          loading={overviewLoading}
          color={overview && overview.active_alerts > 0 ? "red" : "default"}
        />
      </div>

      {/* Second row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Occupancy breakdown */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Activity className="w-4 h-4" />
              Bed Occupancy Breakdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            <OccupancyChart data={overview} loading={overviewLoading} />
            {overview && (
              <>
              <div className="mt-3 grid grid-cols-3 text-center text-xs text-slate-500">
                <div>
                  <span className="block font-semibold text-slate-900 text-base">
                    {overview.occupied_beds}
                  </span>
                  Occupied
                </div>
                <div>
                  <span className="block font-semibold text-emerald-700 text-base">
                    {overview.vacant_beds}
                  </span>
                  Vacant
                </div>
                <div>
                  <span className="block font-semibold text-amber-700 text-base">
                    {overview.not_ready_beds}
                  </span>
                  Not ready
                </div>
              </div>
              <p className="mt-3 text-center text-[11px] text-slate-400">
                From admissions. Cameras currently see a person in {overview.camera_occupied_beds} bed{overview.camera_occupied_beds === 1 ? "" : "s"}.
              </p>
              </>
            )}
          </CardContent>
        </Card>

        {/* Active alerts */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              Active Alerts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ActiveAlertsWidget alerts={activeAlerts} loading={alertsLoading} />
          </CardContent>
        </Card>

        {/* Fall events summary */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Fall Events
            </CardTitle>
          </CardHeader>
          <CardContent>
            {overviewLoading ? (
              <div className="space-y-3">
                {[1,2,3].map(i=><div key={i} className="h-10 bg-slate-100 rounded animate-pulse"/>)}
              </div>
            ) : (
              <div className="space-y-3">
                {[
                  { label: "Active (needs review)", value: eventSummary?.active_events ?? 0, color: "text-red-600" },
                  { label: "Acknowledged", value: eventSummary?.acknowledged_events ?? 0, color: "text-amber-700" },
                  { label: "Resolved", value: eventSummary?.resolved_events ?? 0, color: "text-emerald-700" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
                    <span className="text-sm text-slate-500">{label}</span>
                    <span className={`text-sm font-semibold ${color}`}>{value}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent jobs */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-slate-700">
            Recent Inference Jobs
          </CardTitle>
        </CardHeader>
        <CardContent>
          <RecentJobsWidget jobs={jobs ?? []} loading={jobsLoading} />
        </CardContent>
      </Card>
    </div>
  );
}
