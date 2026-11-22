"use client";

import { useCallback } from "react";
import { formatDistanceToNow } from "date-fns";
import { CheckCircle2, XCircle, Clock, Loader2 } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { getJob, getJobResults } from "@/lib/api/jobs";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { InferenceJob, JobResults } from "@/lib/types";

interface Props {
  jobId: string;
}

const statusIcon = {
  queued: <Clock className="w-4 h-4 text-slate-500" />,
  processing: <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />,
  live: <Loader2 className="w-4 h-4 text-red-500 animate-spin" />,
  completed: <CheckCircle2 className="w-4 h-4 text-emerald-600" />,
  failed: <XCircle className="w-4 h-4 text-red-500" />,
};

const statusVariant: Record<string, "muted" | "warning" | "success" | "destructive" | "info"> = {
  queued: "muted",
  processing: "warning",
  live: "info",
  completed: "success",
  failed: "destructive",
};

export function JobStatusCard({ jobId }: Props) {
  const { data: job, loading } = usePoll<InferenceJob>(
    useCallback(() => getJob(jobId), [jobId]),
    3_000,
    { stopWhen: (j) => j.status === "completed" || j.status === "failed" },
  );

  const { data: results } = usePoll<JobResults>(
    useCallback(() => getJobResults(jobId), [jobId]),
    5_000,
    { enabled: job?.status === "completed" },
  );

  if (loading) return <Skeleton className="h-32 w-full" />;
  if (!job) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold text-slate-700">
            {job.video_filename}
          </CardTitle>
          <div className="flex items-center gap-2">
            {statusIcon[job.status]}
            <Badge variant={statusVariant[job.status]}>{job.status}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {job.status === "processing" && (
          <div>
            <div className="flex justify-between text-xs text-slate-500 mb-1">
              <span>Processing…</span>
              <span>{Math.round(job.progress)}%</span>
            </div>
            <Progress value={job.progress} />
          </div>
        )}

        {job.error_message && job.status === "failed" && (
          <p className="text-xs text-red-600 bg-red-50 rounded px-2 py-1">
            {job.error_message}
          </p>
        )}

        {job.error_message && job.status === "completed" && (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
            ⚠ {job.error_message}
          </p>
        )}

        <div className="text-xs text-slate-400">
          Created {formatDistanceToNow(new Date(job.created_at.endsWith("Z") ? job.created_at : job.created_at + "Z"), { addSuffix: true })}
        </div>

        {/* Results */}
        {results && job.status === "completed" && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            {results.fall_events.length > 0 ? (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
                <XCircle className="w-4 h-4 text-red-600 shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-red-700">Fall detected</p>
                  <p className="text-xs text-red-500">
                    {results.fall_events.length} event{results.fall_events.length > 1 ? "s" : ""},{" "}
                    highest confidence{" "}
                    {Math.max(...results.fall_events.map((e) => e.confidence * 100)).toFixed(0)}%
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <p className="text-sm font-semibold text-emerald-700">No fall detected</p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
