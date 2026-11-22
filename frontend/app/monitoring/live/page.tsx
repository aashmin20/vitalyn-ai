"use client";

import { useCallback, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { usePoll } from "@/lib/hooks/usePoll";
import { listRooms, listRoomBeds } from "@/lib/api/rooms";
import { listJobs, getJobResults } from "@/lib/api/jobs";
import { listFallEvents } from "@/lib/api/events";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DualVideoPlayer } from "@/components/monitoring/DualVideoPlayer";
import { AlertTriangle, BedDouble, Activity } from "lucide-react";
import type { Room, Bed, InferenceJob, JobResults, FallEvent } from "@/lib/types";

export default function LiveMonitoringPage() {
  const [selectedRoomId, setSelectedRoomId] = useState("");
  const [selectedJobId, setSelectedJobId] = useState("");

  const { data: rooms } = usePoll<Room[]>(
    useCallback(() => listRooms(), []),
    60_000,
  );

  const { data: beds } = usePoll<Bed[]>(
    useCallback(() => {
      if (!selectedRoomId) return Promise.resolve([]);
      return listRoomBeds(selectedRoomId);
    }, [selectedRoomId]),
    30_000,
    { enabled: !!selectedRoomId },
  );

  const { data: jobs } = usePoll<InferenceJob[]>(
    useCallback(() => listJobs(), []),
    15_000,
  );

  const { data: results } = usePoll<JobResults>(
    useCallback(() => {
      if (!selectedJobId) return Promise.resolve({ job: null as any, occupancy_records: [], fall_events: [] });
      return getJobResults(selectedJobId);
    }, [selectedJobId]),
    10_000,
    { enabled: !!selectedJobId },
  );

  const { data: allFallEvents } = usePoll<FallEvent[]>(
    useCallback(() => listFallEvents(), []),
    10_000,
  );

  const roomJobs = jobs?.filter(
    (j) => j.room_id === selectedRoomId && j.status === "completed" && !j.video_path.startsWith("camera:"),
  ) ?? [];

  const activeFallEvents = allFallEvents?.filter((e) => e.status === "active") ?? [];
  const occupancyRecords = results?.occupancy_records ?? [];
  const jobFallEvents = results?.fall_events ?? [];

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Video Review</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Select a room and an inference job to review video analysis results
        </p>
      </div>

      {/* Selection row */}
      <div className="flex flex-wrap gap-4">
        <div className="min-w-[200px]">
          <label className="block text-xs font-medium text-slate-500 mb-1">Room</label>
          <Select
            value={selectedRoomId}
            onChange={(e) => { setSelectedRoomId(e.target.value); setSelectedJobId(""); }}
            placeholder="Select room…"
          >
            {rooms?.map((r) => (
              <option key={r.id} value={r.id}>
                Room {r.room_number} · Floor {r.floor}
              </option>
            ))}
          </Select>
        </div>

        {selectedRoomId && (
          <div className="min-w-[260px]">
            <label className="block text-xs font-medium text-slate-500 mb-1">Analysis Job</label>
            <Select
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              placeholder="Select completed job…"
            >
              {roomJobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.video_filename} — {new Date(j.created_at).toLocaleDateString()}
                </option>
              ))}
            </Select>
            {roomJobs.length === 0 && (
              <p className="text-xs text-slate-400 mt-1">
                No completed jobs for this room.{" "}
                <a href="/monitoring/analysis" className="text-blue-500 hover:underline">Upload one.</a>
              </p>
            )}
          </div>
        )}
      </div>

      {/* Main 4-panel layout */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Left panel — room info */}
        <div className="xl:col-span-1 space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Room Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {beds && beds.length > 0 ? (
                beds.map((bed) => (
                  <div key={bed.id} className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-sm text-slate-700">
                      <BedDouble className="w-3.5 h-3.5" />
                      Bed {bed.bed_number}
                    </span>
                    <Badge variant="muted">{bed.status}</Badge>
                  </div>
                ))
              ) : selectedRoomId ? (
                <p className="text-xs text-slate-400">No beds configured</p>
              ) : (
                <p className="text-xs text-slate-400">Select a room</p>
              )}
            </CardContent>
          </Card>

          {/* Active fall events for this room */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wide flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                Active Events
              </CardTitle>
            </CardHeader>
            <CardContent>
              {activeFallEvents.filter((e) => !selectedRoomId || e.room_id === selectedRoomId).length === 0 ? (
                <p className="text-xs text-slate-400">No active events</p>
              ) : (
                <div className="space-y-2">
                  {activeFallEvents
                    .filter((e) => !selectedRoomId || e.room_id === selectedRoomId)
                    .map((ev) => (
                      <div key={ev.id} className="bg-red-50 border border-red-100 rounded-lg p-2">
                        <p className="text-xs font-medium text-red-700 capitalize">
                          {ev.event_type.replace(/_/g, " ")}
                        </p>
                        <p className="text-xs text-red-500">
                          {(ev.confidence * 100).toFixed(0)}% confidence
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {formatDistanceToNow(new Date(ev.created_at), { addSuffix: true })}
                        </p>
                      </div>
                    ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Centre panel — video */}
        <div className="xl:col-span-2">
          <Card className="h-full">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Video Analysis
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!selectedJobId ? (
                <div className="aspect-video bg-slate-100 rounded-xl flex items-center justify-center">
                  <div className="text-center text-slate-400">
                    <Activity className="w-10 h-10 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">Select a room and completed job to view video</p>
                  </div>
                </div>
              ) : (
                <DualVideoPlayer
                  jobId={selectedJobId}
                  occupancyRecords={occupancyRecords}
                  fallEvents={jobFallEvents}
                />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right panel — detection metadata */}
        <div className="xl:col-span-1 space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Occupancy Results
              </CardTitle>
            </CardHeader>
            <CardContent>
              {occupancyRecords.length === 0 ? (
                <p className="text-xs text-slate-400">
                  {selectedJobId ? "No occupancy records for this job" : "Select a job"}
                </p>
              ) : (
                <div className="space-y-1.5">
                  {["occupied", "vacant", "uncertain"].map((status) => {
                    const count = occupancyRecords.filter((r) => r.occupancy_status === status).length;
                    const pct = occupancyRecords.length > 0
                      ? Math.round((count / occupancyRecords.length) * 100)
                      : 0;
                    return (
                      <div key={status} className="flex items-center justify-between text-xs">
                        <span className="capitalize text-slate-600">{status}</span>
                        <span className="font-semibold text-slate-800">{count} ({pct}%)</span>
                      </div>
                    );
                  })}
                  <div className="border-t border-slate-100 pt-1.5 mt-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-500">Total observations</span>
                      <span className="font-semibold">{occupancyRecords.length}</span>
                    </div>
                    {occupancyRecords.length > 0 && (
                      <div className="flex justify-between text-xs mt-0.5">
                        <span className="text-slate-500">Avg confidence</span>
                        <span className="font-semibold">
                          {(occupancyRecords.reduce((s, r) => s + r.confidence, 0) / occupancyRecords.length * 100).toFixed(0)}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Event Log
              </CardTitle>
            </CardHeader>
            <CardContent>
              {jobFallEvents.length === 0 ? (
                <p className="text-xs text-slate-400">
                  {selectedJobId ? "No fall events detected" : "Select a job"}
                </p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {jobFallEvents.map((ev) => (
                    <div key={ev.id} className="text-xs border-l-2 border-red-400 pl-2">
                      <p className="font-medium text-slate-700 capitalize">
                        {ev.event_type.replace(/_/g, " ")}
                      </p>
                      <p className="text-slate-500">
                        {(ev.confidence * 100).toFixed(0)}% · {ev.status}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
