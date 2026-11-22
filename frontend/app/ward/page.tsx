"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { BedDouble, Video, AlertTriangle } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { getWardBoard, setBedStatus, type BedState, type BoardBed, type WardBoard } from "@/lib/api/adt";
import { describeApiError } from "@/lib/api/patients";
import { useAuth } from "@/components/auth/AuthProvider";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import { cn } from "@/lib/utils";

const STYLE: Record<BedState, string> = {
  occupied: "border-slate-300 bg-white",
  available: "border-emerald-200 bg-emerald-50",
  cleaning: "border-amber-200 bg-amber-50",
  maintenance: "border-slate-200 bg-slate-100 text-slate-500",
};

export default function WardBoardPage() {
  const { user } = useAuth();
  const { data: board, loading, error, refetch } = usePoll<WardBoard>(useCallback(() => getWardBoard(), []), 5_000);
  const [message, setMessage] = useState<string | null>(null);
  const canBeds = user?.role === "admin" || user?.role === "doctor" || user?.role === "nurse";

  const change = async (bed: BoardBed, status: "available" | "cleaning" | "maintenance") => {
    setMessage(null);
    try {
      await setBedStatus(bed.id, status);
      refetch();
    } catch (e) {
      setMessage(describeApiError(e));
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <BedDouble className="h-6 w-6" /> Ward board
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Every room and bed, who is in it, and what needs attention</p>
      </div>
      <DemoDataBanner />
      {message && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">{message}</p>}

      {board && (
        <div className="flex flex-wrap gap-2 text-xs">
          {(["occupied", "available", "cleaning", "maintenance"] as BedState[]).map((s) => (
            <span key={s} className={cn("rounded-full border px-3 py-1", STYLE[s])}>{board.counts[s]} {s}</span>
          ))}
        </div>
      )}

      {loading ? (
        <Skeleton className="h-48" />
      ) : error || !board ? (
        <p className="text-sm text-red-600">Could not load the ward board.</p>
      ) : board.rooms.length === 0 ? (
        <p className="text-sm text-slate-400">No rooms yet. Add rooms and beds under Hospital Ops.</p>
      ) : (
        board.rooms.map((room) => (
          <Card key={room.id}>
            <CardContent className="p-4">
              <p className="mb-3 text-sm font-semibold text-slate-800">
                Room {room.room_number} <span className="font-normal text-slate-400">· Floor {room.floor}</span>
              </p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {room.beds.map((bed) => (
                  <div key={bed.id} className={cn("rounded-lg border p-3 text-sm", STYLE[bed.status])}>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium">Bed {bed.bed_number}</span>
                      <span className="text-[11px] capitalize">{bed.status}</span>
                    </div>
                    {bed.patient ? (
                      <Link href={`/patients/${bed.patient.id}`} className="mt-2 block hover:underline">
                        <p className="font-medium text-slate-900">{bed.patient.name}, {bed.patient.age}</p>
                        <p className="font-mono text-[11px] text-slate-500">{bed.patient.patient_code}</p>
                        <div className="mt-1 flex flex-wrap gap-2 text-[11px]">
                          {bed.patient.monitored && (
                            <span className="inline-flex items-center gap-1 text-emerald-700"><Video className="h-3 w-3" /> monitored</span>
                          )}
                          {!!bed.patient.active_alerts && (
                            <span className="inline-flex items-center gap-1 font-medium text-red-600">
                              <AlertTriangle className="h-3 w-3" /> {bed.patient.active_alerts} possible fall
                            </span>
                          )}
                        </div>
                      </Link>
                    ) : canBeds && bed.status !== "occupied" ? (
                      <div className="mt-2 flex gap-1">
                        {bed.status !== "available" && <Button size="sm" variant="outline" onClick={() => change(bed, "available")}>Mark ready</Button>}
                        {bed.status === "available" && <Button size="sm" variant="ghost" onClick={() => change(bed, "cleaning")}>Cleaning</Button>}
                        {bed.status !== "maintenance" && <Button size="sm" variant="ghost" onClick={() => change(bed, "maintenance")}>Maintenance</Button>}
                      </div>
                    ) : null}
                  </div>
                ))}
                {room.unassigned.map((p) => (
                  <Link key={p.id} href={`/patients/${p.id}`} className="rounded-lg border border-dashed border-slate-300 p-3 text-sm hover:underline">
                    <p className="text-[11px] text-slate-400">No bed assigned</p>
                    <p className="font-medium text-slate-900">{p.name}, {p.age}</p>
                    <p className="font-mono text-[11px] text-slate-500">{p.patient_code}</p>
                  </Link>
                ))}
                {room.beds.length === 0 && room.unassigned.length === 0 && (
                  <p className="text-xs text-slate-400">No beds in this room.</p>
                )}
              </div>
            </CardContent>
          </Card>
        ))
      )}
      <p className="text-[11px] text-slate-400">Possible falls need human review. Detection is not clinically validated.</p>
    </div>
  );
}
