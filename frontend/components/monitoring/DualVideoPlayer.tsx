"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { Play, Pause, Volume2, VolumeX, Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn, parseUtc } from "@/lib/utils";
import type { OccupancyRecord, FallEvent } from "@/lib/types";
import { videoStreamUrl } from "@/lib/api/jobs";

interface Props {
  jobId: string;
  occupancyRecords: OccupancyRecord[];
  fallEvents: FallEvent[];
}

function formatTime(secs: number): string {
  const m = Math.floor(secs / 60).toString().padStart(2, "0");
  const s = Math.floor(secs % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export function DualVideoPlayer({ jobId, occupancyRecords, fallEvents }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const streamUrl = videoStreamUrl(jobId);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) { v.play(); setPlaying(true); }
    else { v.pause(); setPlaying(false); }
  }, []);

  const toggleMute = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  }, []);

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = Number(e.target.value);
    if (videoRef.current) videoRef.current.currentTime = t;
    setCurrentTime(t);
  };

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime);
    const onMeta = () => setDuration(v.duration);
    const onEnded = () => setPlaying(false);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("ended", onEnded);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("ended", onEnded);
    };
  }, []);

  // Timeline positions come from the real timestamps the pipeline stored.
  // Occupancy records are written one per second from the video start, so the
  // earliest record is the video's t=0; fall events are offset from the same origin.
  const originMs = occupancyRecords.length
    ? Math.min(...occupancyRecords.map((r) => parseUtc(r.observed_at).getTime()))
    : null;
  const toSecs = (iso: string) =>
    originMs === null ? null : (parseUtc(iso).getTime() - originMs) / 1000;

  const sortedRecords = [...occupancyRecords].sort(
    (a, b) => parseUtc(a.observed_at).getTime() - parseUtc(b.observed_at).getTime(),
  );
  const segments = sortedRecords.map((r, i) => {
    const start = toSecs(r.observed_at) ?? 0;
    const next = sortedRecords[i + 1];
    const end = next ? (toSecs(next.observed_at) ?? start + 1) : start + 1;
    return { start, end, status: r.occupancy_status };
  });

  const fallMarkers = fallEvents.flatMap((fe) => {
    if (!fe.started_at) return [];
    const start = toSecs(fe.started_at);
    if (start === null) return [];
    const end = fe.ended_at ? (toSecs(fe.ended_at) ?? start) : start;
    return [{ id: fe.id, start, end: Math.max(end, start), confidence: fe.confidence }];
  });

  const seekTo = (t: number) => {
    if (videoRef.current) videoRef.current.currentTime = Math.min(Math.max(t, 0), duration || t);
    setCurrentTime(t);
  };

  const statusColor = {
    occupied: "bg-amber-400",
    vacant: "bg-emerald-400",
    uncertain: "bg-slate-300",
  };

  return (
    <div className="space-y-3">
      {/* Video */}
      <div className="relative bg-black rounded-xl overflow-hidden aspect-video group">
        <video
          ref={videoRef}
          src={streamUrl}
          muted={muted}
          className="w-full h-full object-contain"
          preload="metadata"
        />

        {/* Overlay controls */}
        <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="p-3 flex items-center gap-3">
            <Button
              size="icon"
              variant="ghost"
              className="text-white hover:bg-white/20 h-8 w-8"
              onClick={togglePlay}
            >
              {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="text-white hover:bg-white/20 h-8 w-8"
              onClick={toggleMute}
            >
              {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </Button>
            <span className="text-white text-xs font-mono">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
            <div className="flex-1" />
            <Button
              size="icon"
              variant="ghost"
              className="text-white hover:bg-white/20 h-8 w-8"
              onClick={() => videoRef.current?.requestFullscreen()}
            >
              <Maximize2 className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Click to play */}
        {!playing && (
          <button
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center"
          >
            <div className="w-16 h-16 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
              <Play className="w-7 h-7 text-white ml-1" />
            </div>
          </button>
        )}
      </div>

      {/* Timeline scrubber with occupancy segments */}
      <div className="space-y-2">
        <div className="relative h-6">
          {/* Coloured occupancy segments */}
          {duration > 0 && segments.map((seg, i) => (
            <div
              key={i}
              className={cn("absolute top-1 h-4 rounded-sm opacity-70", statusColor[seg.status])}
              style={{
                left: `${(seg.start / duration) * 100}%`,
                width: `${((seg.end - seg.start) / duration) * 100}%`,
              }}
            />
          ))}

          {/* Fall event markers */}
          {duration > 0 && fallMarkers.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => seekTo(m.start)}
              className="absolute top-0 h-6 min-w-[4px] bg-red-600/80 hover:bg-red-600 z-30 rounded-sm"
              style={{
                left: `${Math.min(100, (m.start / duration) * 100)}%`,
                width: `${Math.max(0, ((Math.min(m.end, duration) - m.start) / duration) * 100)}%`,
              }}
              title={`Potential fall ${formatTime(m.start)}–${formatTime(m.end)} · ${(m.confidence * 100).toFixed(0)}% — click to review`}
            />
          ))}

          {/* Scrub input on top */}
          <input
            type="range"
            className="scrubber absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
            min={0}
            max={duration || 100}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
          />

          {/* Visible track */}
          <div className="absolute top-2 left-0 right-0 h-2 bg-slate-200 rounded-full pointer-events-none" />

          {/* Progress fill */}
          <div
            className="absolute top-2 left-0 h-2 bg-slate-700 rounded-full pointer-events-none transition-all"
            style={{ width: duration > 0 ? `${(currentTime / duration) * 100}%` : "0%" }}
          />
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <span className="w-3 h-2 rounded-sm bg-amber-400 inline-block" /> Occupied
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-2 rounded-sm bg-emerald-400 inline-block" /> Vacant
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-2 rounded-sm bg-slate-300 inline-block" /> Uncertain
          </span>
          {fallEvents.length > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-0.5 h-3 bg-red-600 inline-block" /> Fall event
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
