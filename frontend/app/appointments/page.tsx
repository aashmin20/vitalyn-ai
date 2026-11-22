"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CalendarDays, Plus } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listDoctors, listPatients, describeApiError } from "@/lib/api/patients";
import {
  bookAppointment, getAvailability, listAppointments, registerOutpatient, setAppointmentStatus, todayStr, timeOf,
  type Appointment, type AppointmentStatus, type Slot,
} from "@/lib/api/opd";
import { useAuth } from "@/components/auth/AuthProvider";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { STATUS_VARIANT } from "@/components/appointments/status";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import type { Doctor, Patient } from "@/lib/types";

const input = "mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900";

export default function AppointmentsPage() {
  const { user } = useAuth();
  const canBook = user?.role === "admin" || user?.role === "doctor" || user?.role === "receptionist";
  const [date, setDate] = useState(todayStr());
  const [doctorId, setDoctorId] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const { data: doctors } = usePoll<Doctor[]>(useCallback(() => listDoctors(), []), 60_000);
  const { data: appts, loading, error, refetch } = usePoll<Appointment[]>(
    useCallback(() => listAppointments({ date, doctorId: doctorId || undefined }), [date, doctorId]), 10_000);

  // booking dialog
  const [open, setOpen] = useState(false);
  const [bDoctor, setBDoctor] = useState("");
  const [bDate, setBDate] = useState(todayStr());
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slot, setSlot] = useState("");
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState("");
  const [newName, setNewName] = useState("");
  const [newAge, setNewAge] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !bDoctor) { setSlots([]); return; }
    let live = true;
    getAvailability(bDoctor, bDate).then((s) => live && setSlots(s)).catch(() => live && setSlots([]));
    return () => { live = false; };
  }, [open, bDoctor, bDate]);

  useEffect(() => {
    if (!open || q.trim().length < 2) { setFound([]); return; }
    const t = setTimeout(() => listPatients("all", q).then(setFound).catch(() => setFound([])), 300);
    return () => clearTimeout(t);
  }, [open, q]);

  const openBooking = () => {
    setBDoctor(doctorId); setBDate(date); setSlot(""); setQ(""); setPatientId(""); setNewName(""); setNewAge(""); setReason(""); setErr(null);
    setOpen(true);
  };

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      let pid = patientId;
      if (!pid) {
        if (!newName.trim() || newAge === "") throw new Error("Pick an existing patient or enter a name and age for a new one.");
        pid = (await registerOutpatient({ name: newName.trim(), age: Number(newAge), reason: reason.trim() || null })).id;
      }
      if (!bDoctor || !slot) throw new Error("Choose a doctor and a time slot.");
      await bookAppointment({ patient_id: pid, doctor_id: bDoctor, start_at: slot, reason: reason.trim() || null });
      setOpen(false);
      setDate(bDate);
      refetch();
    } catch (e) {
      setErr(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const act = async (a: Appointment, status: Exclude<AppointmentStatus, "scheduled">) => {
    setMessage(null);
    try { await setAppointmentStatus(a.id, status); refetch(); } catch (e) { setMessage(describeApiError(e)); }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><CalendarDays className="h-6 w-6" /> Appointments</h1>
          <p className="text-sm text-slate-500 mt-0.5">Outpatient bookings by day and doctor</p>
        </div>
        <div className="flex gap-2">
          <Link href="/appointments/queue"><Button variant="outline">Today&apos;s queue</Button></Link>
          {canBook && <Button onClick={openBooking}><Plus className="mr-2 h-4 w-4" /> Book appointment</Button>}
        </div>
      </div>
      <DemoDataBanner />
      {message && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">{message}</p>}

      <div className="flex flex-wrap gap-3">
        <input type="date" className="rounded-md border border-slate-200 px-3 py-2 text-sm" value={date} onChange={(e) => setDate(e.target.value)} />
        <Select className="w-56" value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
          <option value="">All doctors</option>
          {doctors?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? <div className="space-y-2 p-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
            : error ? <p className="p-8 text-center text-sm text-red-600">Could not load appointments.</p>
            : !appts || appts.length === 0 ? <p className="p-10 text-center text-sm text-slate-400">No appointments on this day.</p>
            : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                    <th className="px-4 py-3 font-medium">Time</th><th className="px-4 py-3 font-medium">Patient</th>
                    <th className="px-4 py-3 font-medium">Doctor</th><th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {appts.map((a) => (
                    <tr key={a.id}>
                      <td className="px-4 py-3 font-mono text-xs">{timeOf(a.start_at)}–{timeOf(a.end_at)}</td>
                      <td className="px-4 py-3">
                        {a.patient && <Link href={`/patients/${a.patient.id}`} className="hover:underline">{a.patient.name}</Link>}
                        <span className="ml-1 font-mono text-[11px] text-slate-400">{a.patient?.patient_code}</span>
                        {a.reason && <p className="text-xs text-slate-500">{a.reason}</p>}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{a.doctor?.name}</td>
                      <td className="px-4 py-3"><Badge variant={STATUS_VARIANT[a.status]}>{a.status.replace("_", " ")}</Badge></td>
                      <td className="px-4 py-3 text-right">
                        {canBook && a.status === "scheduled" && (
                          <div className="flex justify-end gap-1">
                            <Button size="sm" onClick={() => act(a, "checked_in")}>Check in</Button>
                            <Button size="sm" variant="ghost" onClick={() => act(a, "cancelled")}>Cancel</Button>
                            <Button size="sm" variant="ghost" onClick={() => act(a, "no_show")}>No-show</Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={(o) => !o && !busy && setOpen(false)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Book appointment</DialogTitle>
            <DialogDescription>Find the patient or register a new outpatient, then pick a free slot.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <label className="block text-xs font-medium text-slate-600">
              Find patient (name, code or phone)
              <input className={input} value={q} onChange={(e) => { setQ(e.target.value); setPatientId(""); }} disabled={busy} />
            </label>
            {found.length > 0 && !patientId && (
              <ul className="max-h-32 divide-y divide-slate-100 overflow-y-auto rounded border border-slate-200 text-sm">
                {found.map((p) => (
                  <li key={p.id}>
                    <button type="button" className="w-full px-3 py-1.5 text-left hover:bg-slate-50" onClick={() => { setPatientId(p.id); setQ(`${p.patient_code} · ${p.name}`); }}>
                      {p.name} <span className="font-mono text-xs text-slate-400">{p.patient_code}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {!patientId && (
              <div className="grid grid-cols-3 gap-2">
                <label className="col-span-2 block text-xs font-medium text-slate-600">New patient name
                  <input className={input} value={newName} maxLength={80} onChange={(e) => setNewName(e.target.value)} disabled={busy} /></label>
                <label className="block text-xs font-medium text-slate-600">Age
                  <input className={input} inputMode="numeric" value={newAge} onChange={(e) => setNewAge(e.target.value.replace(/\D/g, "").slice(0, 3))} disabled={busy} /></label>
              </div>
            )}
            <label className="block text-xs font-medium text-slate-600">Doctor
              <Select className="mt-1" value={bDoctor} onChange={(e) => { setBDoctor(e.target.value); setSlot(""); }} disabled={busy}>
                <option value="">Select doctor…</option>
                {doctors?.map((d) => <option key={d.id} value={d.id}>{d.name}{d.department ? ` · ${d.department}` : ""}</option>)}
              </Select></label>
            <label className="block text-xs font-medium text-slate-600">Date
              <input type="date" className={input} value={bDate} onChange={(e) => { setBDate(e.target.value); setSlot(""); }} disabled={busy} /></label>
            <div>
              <p className="text-xs font-medium text-slate-600">Time slot</p>
              {!bDoctor ? <p className="mt-1 text-xs text-slate-400">Choose a doctor first.</p>
                : slots.length === 0 ? <p className="mt-1 text-xs text-slate-400">No clinic hours for this doctor on that day (set them under Schedules).</p>
                : (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {slots.map((s) => (
                      <Button key={s.start} type="button" size="sm" variant={slot === s.start ? "default" : "outline"} disabled={!s.free || busy} onClick={() => setSlot(s.start)}>
                        {timeOf(s.start)}
                      </Button>
                    ))}
                  </div>
                )}
            </div>
            <label className="block text-xs font-medium text-slate-600">Reason (optional)
              <input className={input} value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} disabled={busy} /></label>
            {err && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">{err}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
            <Button onClick={submit} disabled={busy}>{busy ? "Booking…" : "Book"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
