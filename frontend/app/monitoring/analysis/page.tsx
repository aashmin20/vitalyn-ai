"use client";

import { useCallback, useState } from "react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listRooms } from "@/lib/api/rooms";
import { listJobs } from "@/lib/api/jobs";
import { VideoUploader } from "@/components/monitoring/VideoUploader";
import { JobStatusCard } from "@/components/monitoring/JobStatusCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Room } from "@/lib/types";

export default function VideoAnalysisPage() {
  const [activeJobIds, setActiveJobIds] = useState<string[]>([]);

  const { data: rooms, loading: roomsLoading } = usePoll<Room[]>(
    useCallback(() => listRooms(), []),
    60_000,
  );

  const { data: jobs, loading: jobsLoading } = usePoll(
    useCallback(() => listJobs(), []),
    15_000,
  );

  const handleJobCreated = (jobId: string) => {
    setActiveJobIds((prev) => [jobId, ...prev]);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Video Analysis</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Upload a hospital room video to run occupancy and fall detection inference
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Upload panel */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-slate-700">
                Upload Video
              </CardTitle>
            </CardHeader>
            <CardContent>
              {roomsLoading ? (
                <Skeleton className="h-48 w-full" />
              ) : (
                <VideoUploader
                  rooms={rooms ?? []}
                  onJobCreated={handleJobCreated}
                />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Job tracking panel */}
        <div className="lg:col-span-3 space-y-4">
          <h2 className="text-sm font-semibold text-slate-700">
            Inference Jobs
          </h2>

          {/* Active jobs from this session first */}
          {activeJobIds.map((id) => (
            <JobStatusCard key={id} jobId={id} />
          ))}

          {/* Historic jobs */}
          {jobsLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            jobs
              ?.filter((j) => !activeJobIds.includes(j.id))
              .map((job) => (
                <JobStatusCard key={job.id} jobId={job.id} />
              ))
          )}

          {!jobsLoading && (jobs?.length ?? 0) === 0 && activeJobIds.length === 0 && (
            <div className="text-center py-12 text-slate-400 text-sm border-2 border-dashed border-slate-200 rounded-xl">
              No inference jobs yet. Upload a video to get started.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
