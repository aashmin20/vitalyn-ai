"use client";

import Link from "next/link";
import { AlertTriangle, Video } from "lucide-react";
import type { BedState, BoardBed } from "@/lib/api/adt";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type SettableBedState = "available" | "cleaning" | "maintenance";

/** Shared by the Rooms page and the ward board so both show beds the same way. */
export const BED_LABEL: Record<BedState, string> = {
  occupied: "Occupied",
  available: "Vacant",
  cleaning: "Cleaning",
  maintenance: "Under maintenance",
};

export const BED_STYLE: Record<BedState, string> = {
  occupied: "border-slate-300 bg-white",
  available: "border-emerald-200 bg-emerald-50",
  cleaning: "border-amber-200 bg-amber-50",
  maintenance: "border-slate-200 bg-slate-100 text-slate-500",
};

export const BED_DOT: Record<BedState, string> = {
  occupied: "bg-slate-800",
  available: "bg-emerald-600",
  cleaning: "bg-amber-500",
  maintenance: "bg-slate-400",
};

export const BED_ORDER: BedState[] = ["occupied", "available", "cleaning", "maintenance"];

export function BedTile({
  bed,
  canChange,
  busy,
  onChange,
}: {
  bed: BoardBed;
  canChange: boolean;
  busy?: boolean;
  onChange: (bed: BoardBed, status: SettableBedState) => void;
}) {
  return (
    <div className={cn("rounded-lg border p-3 text-sm", BED_STYLE[bed.status])}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium">Bed {bed.bed_number}</span>
        <span className="inline-flex items-center gap-1.5 text-[11px]">
          <span className={cn("h-2 w-2 rounded-full", BED_DOT[bed.status])} />
          {BED_LABEL[bed.status]}
        </span>
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
      ) : canChange ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {bed.status !== "available" && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => onChange(bed, "available")}>Mark ready</Button>
          )}
          {bed.status !== "cleaning" && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onChange(bed, "cleaning")}>Cleaning</Button>
          )}
          {bed.status !== "maintenance" && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onChange(bed, "maintenance")}>Maintenance</Button>
          )}
        </div>
      ) : null}
    </div>
  );
}

/** Thin bar showing how a room's beds split across the four states. */
export function AvailabilityBar({ summary }: { summary: Record<BedState, number> }) {
  const total = BED_ORDER.reduce((n, s) => n + (summary[s] ?? 0), 0);
  if (!total) return null;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-100" aria-hidden>
      {BED_ORDER.map((s) =>
        summary[s] ? <div key={s} className={BED_DOT[s]} style={{ width: `${(summary[s] / total) * 100}%` }} /> : null,
      )}
    </div>
  );
}
