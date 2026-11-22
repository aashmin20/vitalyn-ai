"use client";

import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ArrowRight, Video } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type { InferenceJob } from "@/lib/types";

interface Props {
  jobs: InferenceJob[];
  loading: boolean;
}

const statusVariant: Record<string, "default" | "success" | "destructive" | "warning" | "muted" | "info"> = {
  queued: "muted",
  processing: "warning",
  live: "info",
  completed: "success",
  failed: "destructive",
};

export function RecentJobsWidget({ jobs, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-slate-400">
        <Video className="w-8 h-8 mb-2 opacity-30" />
        <p className="text-sm">No inference jobs yet</p>
        <Link href="/monitoring/analysis" className="text-xs text-blue-500 hover:underline mt-1">
          Upload a video
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {jobs.slice(0, 5).map((job) => (
        <div key={job.id} className="p-3 rounded-lg border border-slate-100 bg-slate-50">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm font-medium text-slate-800 truncate max-w-[180px]">
              {job.video_filename}
            </span>
            <Badge variant={statusVariant[job.status] ?? "default"}>
              {job.status}
            </Badge>
          </div>
          {job.status === "processing" && (
            <Progress value={job.progress} className="h-1 mb-1.5" />
          )}
          <p className="text-xs text-slate-400">
            {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
          </p>
        </div>
      ))}

      <Link
        href="/monitoring/analysis"
        className="flex items-center justify-center gap-1 text-xs text-slate-500 hover:text-slate-800 pt-1 transition-colors"
      >
        View all jobs <ArrowRight className="w-3 h-3" />
      </Link>
    </div>
  );
}
