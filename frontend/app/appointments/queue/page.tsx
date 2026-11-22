"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Users } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { describeApiError, listDoctors } from "@/lib/api/patients";
import { listAppointments, setAppointmentStatus, todayStr, timeOf, type Appointment, type AppointmentStatus } from "@/lib/api/opd";
import { useAuth } from "@/components/auth/AuthProvider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import type { Doctor } from "@/lib/types";

const COLUMNS: { title: string; statuses: AppointmentStatus[] }[] = [
  { title: "Expected", statuses: ["scheduled"] },
  { title: "Waiting", statuses: ["checked_in"] },
  { title: "In consultation", statuses: ["in_consult"] },
  { title: "Done", statuses: ["completed", "no_show", "cancelled"] },
];

export default function QueuePage() {
  const { user } = useAuth();
  const isDoctor = user?.role === "admin" || user?.role === "doctor";
  const canDesk = isDoctor || user?.role === "receptionist";
  const [doctorId, setDoctorId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const { data: doctors } = usePoll<Doctor[]>(useCallback(() => listDoctors(), []), 60_000);
  const { data: appts, loading, error, refetch } = usePoll<Appointment[]>(
    useCallback(() => listAppointments({ date: todayStr(), doctorId: doctorId || undefined }), [doctorId]), 5_000);

  const act = async (a: Appointment, status: Exclude<AppointmentStatus, "scheduled">) => {
    setMessage(null);
    try { await setAppointmentStatus(a.id, status); refetch(); } catch (e) { setMessage(describeApiError(e)); }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <Link href="/appointments" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800">
        <ArrowLeft className="h-3.5 w-3.5" /> Appointments
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><Users className="h-6 w-6" /> OPD queue</h1>
          <p className="text-sm text-slate-500 mt-0.5">Today&apos;s outpatients, refreshed every few seconds</p>
        </div>
        <Select className="w-56" value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
          <option value="">All doctors</option>
          {doctors?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </div>
      <DemoDataBanner />
      {message && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">{message}</p>}

      {loading ? <Skeleton className="h-48" /> : error ? <p className="text-sm text-red-600">Could not load the queue.</p> : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {COLUMNS.map((col) => {
            const items = (appts ?? []).filter((a) => col.statuses.includes(a.status));
            return (
              <Card key={col.title}>
                <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold text-slate-700">{col.title} <span className="font-normal text-slate-400">({items.length})</span></CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {items.length === 0 && <p className="py-3 text-center text-xs text-slate-400">Nobody here.</p>}
                  {items.map((a) => (
                    <div key={a.id} className="rounded-lg border border-slate-200 p-2.5 text-sm">
                      <p className="font-medium text-slate-900">{a.patient?.name}</p>
                      <p className="text-xs text-slate-500">{timeOf(a.start_at)} · {a.doctor?.name}</p>
                      {["no_show", "cancelled"].includes(a.status) && <p className="text-[11px] text-slate-400">{a.status.replace("_", " ")}</p>}
                      <div className="mt-2 flex flex-wrap gap-1">
                        {a.status === "scheduled" && canDesk && <Button size="sm" onClick={() => act(a, "checked_in")}>Check in</Button>}
                        {a.status === "checked_in" && isDoctor && <Button size="sm" onClick={() => act(a, "in_consult")}>Start consult</Button>}
                        {a.status === "in_consult" && isDoctor && <Button size="sm" onClick={() => act(a, "completed")}>Complete</Button>}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
