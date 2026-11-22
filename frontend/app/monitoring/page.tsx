"use client";

import { useCallback } from "react";
import Link from "next/link";
import { usePoll } from "@/lib/hooks/usePoll";
import { listRooms } from "@/lib/api/rooms";
import { listJobs } from "@/lib/api/jobs";
import { getCurrentOccupancy } from "@/lib/api/occupancy";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Video, Upload, BedDouble } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { Room, CurrentOccupancy } from "@/lib/types";

const occupancyVariant = {
  occupied: "warning",
  vacant: "success",
  uncertain: "muted",
} as const;

export default function MonitoringOverviewPage() {
  const { data: rooms, loading: roomsLoading } = usePoll<Room[]>(
    useCallback(() => listRooms(), []),
    30_000,
  );

  const { data: occupancy, loading: occupancyLoading } = usePoll<CurrentOccupancy[]>(
    useCallback(() => getCurrentOccupancy(), []),
    15_000,
  );

  const { data: jobs, loading: jobsLoading } = usePoll(
    useCallback(() => listJobs(), []),
    15_000,
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Monitoring Overview</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Current status across all monitored rooms
        </p>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-2 gap-4">
        <Link href="/monitoring/live">
          <Card className="hover:shadow-md transition-shadow cursor-pointer border-slate-200">
            <CardContent className="p-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Video className="w-5 h-5 text-blue-700" />
              </div>
              <div>
                <p className="font-semibold text-slate-800">Video Review</p>
                <p className="text-xs text-slate-400">View video analysis with timeline</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/monitoring/analysis">
          <Card className="hover:shadow-md transition-shadow cursor-pointer border-slate-200">
            <CardContent className="p-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
                <Upload className="w-5 h-5 text-emerald-700" />
              </div>
              <div>
                <p className="font-semibold text-slate-800">Video Analysis</p>
                <p className="text-xs text-slate-400">Upload and process new footage</p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Current occupancy per bed */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-slate-700">
            Current Bed Occupancy
          </CardTitle>
        </CardHeader>
        <CardContent>
          {occupancyLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {[1,2,3,4].map(i => <Skeleton key={i} className="h-16" />)}
            </div>
          ) : occupancy && occupancy.length > 0 ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {occupancy.map((o) => (
                <div
                  key={o.bed_id}
                  className="border border-slate-200 rounded-lg p-3 space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-600 flex items-center gap-1">
                      <BedDouble className="w-3 h-3" />
                      Bed {o.bed_number}
                    </span>
                    <Badge variant={occupancyVariant[o.occupancy_status]}>
                      {o.occupancy_status}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-400">Room {o.room_number}</p>
                  <p className="text-xs text-slate-400">
                    {(o.confidence * 100).toFixed(0)}% confidence
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-slate-400 text-sm">
              No occupancy data yet. Upload and process a video to see results.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent jobs */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-slate-700">
            Recent Jobs
          </CardTitle>
        </CardHeader>
        <CardContent>
          {jobsLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : jobs && jobs.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {jobs.slice(0, 8).map((job) => (
                <div key={job.id} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-sm font-medium text-slate-800">{job.video_filename}</p>
                    <p className="text-xs text-slate-400">
                      {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                    </p>
                  </div>
                  <Badge
                    variant={
                      job.status === "completed" ? "success" :
                      job.status === "failed" ? "destructive" :
                      job.status === "processing" ? "warning" : "muted"
                    }
                  >
                    {job.status}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400 text-center py-6">No jobs yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
