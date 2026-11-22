"use client";

import { useCallback, useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import { usePoll } from "@/lib/hooks/usePoll";
import { listFallEvents } from "@/lib/api/events";
import { getEventSummary } from "@/lib/api/dashboard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BarChart2, AlertTriangle } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { FallEvent, EventSummary } from "@/lib/types";

function buildDailyChart(events: FallEvent[]) {
  const counts: Record<string, number> = {};
  events.forEach((ev) => {
    const day = format(parseISO(ev.created_at), "MMM d");
    counts[day] = (counts[day] ?? 0) + 1;
  });
  return Object.entries(counts)
    .map(([day, count]) => ({ day, count }))
    .slice(-14); // last 14 days
}

const statusVariant: Record<string, "destructive" | "warning" | "success" | "muted"> = {
  active: "destructive",
  acknowledged: "warning",
  resolved: "success",
};

export default function FallEventsAnalyticsPage() {
  const { data: events, loading: eventsLoading } = usePoll<FallEvent[]>(
    useCallback(() => listFallEvents(), []),
    15_000,
  );

  const { data: summary, loading: summaryLoading } = usePoll<EventSummary>(
    useCallback(() => getEventSummary(), []),
    15_000,
  );

  const chartData = useMemo(() => (events ? buildDailyChart(events) : []), [events]);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Fall Events Analytics</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          History and statistics for all detected potential fall events
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total Events", value: summary?.total_events, color: "text-slate-900" },
          { label: "Active", value: summary?.active_events, color: "text-red-700" },
          { label: "Acknowledged", value: summary?.acknowledged_events, color: "text-amber-700" },
          { label: "Resolved", value: summary?.resolved_events, color: "text-emerald-700" },
        ].map(({ label, value, color }) => (
          <Card key={label}>
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide font-medium">{label}</p>
              {summaryLoading ? (
                <Skeleton className="h-8 w-10 mt-1" />
              ) : (
                <p className={`text-3xl font-bold mt-1 ${color}`}>{value ?? 0}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Bar chart — events per day */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <BarChart2 className="w-4 h-4" />
            Events per Day (last 14 days)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {eventsLoading ? (
            <Skeleton className="h-56 w-full" />
          ) : chartData.length === 0 ? (
            <div className="h-56 flex items-center justify-center text-slate-400 text-sm">
              No events recorded yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ebe6da" />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#9a9385" }} tickLine={false} />
                <YAxis
                  tick={{ fontSize: 11, fill: "#9a9385" }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #d8d1c3" }}
                  formatter={(v: number) => [v, "Events"]}
                />
                <Bar dataKey="count" fill="#1b1a17" radius={[4, 4, 0, 0]} name="Events" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Full events table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-slate-700">
            All Events
          </CardTitle>
        </CardHeader>
        <CardContent>
          {eventsLoading ? (
            <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-14" />)}</div>
          ) : events && events.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {events.map((ev) => (
                <div key={ev.id} className="flex items-start justify-between py-3 gap-4">
                  <div className="flex items-start gap-3 min-w-0">
                    <AlertTriangle className={`w-4 h-4 mt-0.5 shrink-0 ${
                      ev.status === "active" ? "text-red-500" :
                      ev.status === "acknowledged" ? "text-amber-500" : "text-emerald-500"
                    }`} />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800 capitalize">
                        {ev.event_type.replace(/_/g, " ")}
                      </p>
                      <p className="text-xs text-slate-400">
                        {formatDistanceToNow(parseISO(ev.created_at), { addSuffix: true })}
                        {" · "}{(ev.confidence * 100).toFixed(0)}% confidence
                      </p>
                    </div>
                  </div>
                  <Badge variant={statusVariant[ev.status] ?? "muted"}>
                    {ev.status}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-10 text-slate-400 text-sm">
              No fall events recorded yet.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
