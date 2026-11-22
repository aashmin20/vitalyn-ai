"use client";

import { useCallback } from "react";
import { formatDistanceToNow } from "date-fns";
import { usePoll } from "@/lib/hooks/usePoll";
import { getCurrentOccupancy } from "@/lib/api/occupancy";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BedDouble } from "lucide-react";
import type { CurrentOccupancy } from "@/lib/types";

const occupancyVariant = {
  occupied: "warning",
  vacant: "success",
  uncertain: "muted",
} as const;

const occupancyColor = {
  occupied: "border-l-amber-400",
  vacant: "border-l-emerald-400",
  uncertain: "border-l-slate-300",
};

export default function OccupancyPage() {
  const { data, loading } = usePoll<CurrentOccupancy[]>(
    useCallback(() => getCurrentOccupancy(), []),
    15_000,
  );

  const occupied = data?.filter((d) => d.occupancy_status === "occupied").length ?? 0;
  const vacant = data?.filter((d) => d.occupancy_status === "vacant").length ?? 0;
  const uncertain = data?.filter((d) => d.occupancy_status === "uncertain").length ?? 0;
  const total = data?.length ?? 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Occupancy</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Latest occupancy status per bed, derived from inference results
        </p>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total Beds", value: total, color: "text-slate-900" },
          { label: "Occupied", value: occupied, color: "text-amber-700" },
          { label: "Vacant", value: vacant, color: "text-emerald-700" },
          { label: "Uncertain", value: uncertain, color: "text-slate-500" },
        ].map(({ label, value, color }) => (
          <Card key={label}>
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide font-medium">{label}</p>
              {loading ? (
                <Skeleton className="h-8 w-10 mt-1" />
              ) : (
                <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Bed-level table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <BedDouble className="w-4 h-4" />
            Current Status per Bed
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
            </div>
          ) : data && data.length > 0 ? (
            <div className="space-y-2">
              {data.map((row) => (
                <div
                  key={row.bed_id}
                  className={`flex items-center justify-between p-3 rounded-lg border-l-4 border border-slate-100 bg-slate-50 ${occupancyColor[row.occupancy_status]}`}
                >
                  <div className="flex items-center gap-3">
                    <BedDouble className="w-4 h-4 text-slate-400 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-slate-800">
                        Bed {row.bed_number}
                        <span className="text-slate-400 font-normal ml-2">· Room {row.room_number}</span>
                      </p>
                      <p className="text-xs text-slate-400">
                        Last observed {formatDistanceToNow(new Date(row.observed_at), { addSuffix: true })}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-500">
                      {(row.confidence * 100).toFixed(0)}% confidence
                    </span>
                    <Badge variant={occupancyVariant[row.occupancy_status]}>
                      {row.occupancy_status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-slate-400">
              <BedDouble className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">No occupancy data yet.</p>
              <p className="text-xs mt-1">
                Upload and process a video in{" "}
                <a href="/monitoring/analysis" className="text-blue-500 hover:underline">
                  Video Analysis
                </a>{" "}
                to see results here.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
