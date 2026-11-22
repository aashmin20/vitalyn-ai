"use client";

import { useCallback, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { format, subHours, parseISO } from "date-fns";
import { usePoll } from "@/lib/hooks/usePoll";
import { getOccupancyTrends } from "@/lib/api/dashboard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp } from "lucide-react";
import type { OccupancyTrend } from "@/lib/types";

const RANGES = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "All", hours: Infinity },
];

function buildChartData(trends: OccupancyTrend[], rangeHours: number) {
  const cutoff = rangeHours === Infinity
    ? new Date(0)
    : subHours(new Date(), rangeHours);

  const filtered = trends.filter((t) => parseISO(t.observed_at) >= cutoff);

  // Group by time bucket (every 30 min) and count status
  const buckets: Record<string, { time: string; occupied: number; vacant: number; uncertain: number }> = {};

  filtered.forEach((t) => {
    const d = parseISO(t.observed_at);
    // Round to 30-min bucket
    const mins = d.getMinutes() < 30 ? "00" : "30";
    const bucket = `${format(d, "MM/dd HH")}:${mins}`;

    if (!buckets[bucket]) {
      buckets[bucket] = { time: bucket, occupied: 0, vacant: 0, uncertain: 0 };
    }
    buckets[bucket][t.occupancy_status]++;
  });

  return Object.values(buckets).sort((a, b) => a.time.localeCompare(b.time));
}

export default function OccupancyTrendsPage() {
  const [rangeHours, setRangeHours] = useState(24);

  const { data: trends, loading } = usePoll<OccupancyTrend[]>(
    useCallback(() => getOccupancyTrends(), []),
    30_000,
  );

  const chartData = useMemo(
    () => (trends ? buildChartData(trends, rangeHours) : []),
    [trends, rangeHours],
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Occupancy Trends</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Historical occupancy observations over time
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Observations per 30-minute window
            </CardTitle>
            {/* Range selector */}
            <div className="flex gap-1">
              {RANGES.map((r) => (
                <Button
                  key={r.label}
                  size="sm"
                  variant={rangeHours === r.hours ? "default" : "ghost"}
                  onClick={() => setRangeHours(r.hours)}
                  className="h-7 px-2.5 text-xs"
                >
                  {r.label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-64 w-full" />
          ) : chartData.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
              No occupancy data for this time range
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ebe6da" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: "#9a9385" }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "#9a9385" }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #d8d1c3" }}
                />
                <Legend
                  iconType="circle"
                  iconSize={8}
                  wrapperStyle={{ fontSize: 12 }}
                />
                <Line
                  type="monotone"
                  dataKey="occupied"
                  stroke="#b8893a"
                  strokeWidth={2}
                  dot={false}
                  name="Occupied"
                />
                <Line
                  type="monotone"
                  dataKey="vacant"
                  stroke="#2e5b4f"
                  strokeWidth={2}
                  dot={false}
                  name="Vacant"
                />
                <Line
                  type="monotone"
                  dataKey="uncertain"
                  stroke="#9a9385"
                  strokeWidth={2}
                  dot={false}
                  name="Uncertain"
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Raw data table */}
      {trends && trends.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold text-slate-700">
              Recent Observations
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 border-b border-slate-100">
                    <th className="text-left pb-2 font-medium">Bed</th>
                    <th className="text-left pb-2 font-medium">Status</th>
                    <th className="text-left pb-2 font-medium">Confidence</th>
                    <th className="text-left pb-2 font-medium">Observed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {trends.slice(0, 20).map((t, i) => (
                    <tr key={i} className="text-xs">
                      <td className="py-2 text-slate-700">{t.bed_number}</td>
                      <td className="py-2">
                        <span className={
                          t.occupancy_status === "occupied" ? "text-amber-700" :
                          t.occupancy_status === "vacant" ? "text-emerald-700" : "text-slate-500"
                        }>
                          {t.occupancy_status}
                        </span>
                      </td>
                      <td className="py-2 text-slate-600">{(t.confidence * 100).toFixed(0)}%</td>
                      <td className="py-2 text-slate-400">
                        {format(parseISO(t.observed_at), "MMM d, HH:mm")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
