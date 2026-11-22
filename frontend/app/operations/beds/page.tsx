"use client";

import { useCallback } from "react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listBeds } from "@/lib/api/rooms";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BedDouble } from "lucide-react";

export default function BedsPage() {
  const { data: beds, loading } = usePoll(
    useCallback(() => listBeds(), []),
    30_000,
  );

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Beds</h1>
        <p className="text-sm text-slate-500 mt-0.5">All configured beds across all rooms</p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-slate-700">
            {loading ? "Loading…" : `${beds?.length ?? 0} beds`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-14" />)}</div>
          ) : beds && beds.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {beds.map((bed) => (
                <div key={bed.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <BedDouble className="w-4 h-4 text-slate-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-800">Bed {bed.bed_number}</p>
                      <p className="text-xs text-slate-400 font-mono text-[10px]">Room ID: {bed.room_id ?? "—"}</p>
                    </div>
                  </div>
                  <Badge variant={bed.status === "active" ? "success" : "muted"}>{bed.status}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400 text-center py-8">No beds configured yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
