"use client";

import { useCallback, useEffect, useState } from "react";
import { Clock, Plus, Trash2 } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { describeApiError, listDoctors } from "@/lib/api/patients";
import { getSchedule, putSchedule, type ScheduleBlock } from "@/lib/api/opd";
import { useAuth } from "@/components/auth/AuthProvider";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import type { Doctor } from "@/lib/types";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const cell = "rounded-md border border-slate-200 px-2 py-1.5 text-sm";

export default function SchedulePage() {
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "doctor";
  const { data: doctors } = usePoll<Doctor[]>(useCallback(() => listDoctors(), []), 60_000);
  const [doctorId, setDoctorId] = useState("");
  const [blocks, setBlocks] = useState<ScheduleBlock[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!doctorId) { setBlocks([]); return; }
    let live = true;
    getSchedule(doctorId).then((b) => live && setBlocks(b)).catch((e) => live && setMessage({ ok: false, text: describeApiError(e) }));
    return () => { live = false; };
  }, [doctorId]);

  const patch = (i: number, change: Partial<ScheduleBlock>) => setBlocks((bs) => bs.map((b, j) => (j === i ? { ...b, ...change } : b)));

  const save = async () => {
    setBusy(true); setMessage(null);
    try {
      setBlocks(await putSchedule(doctorId, blocks));
      setMessage({ ok: true, text: "Schedule saved." });
    } catch (e) {
      setMessage({ ok: false, text: describeApiError(e) });      // e.g. a doctor editing someone else's hours
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><Clock className="h-6 w-6" /> Doctor schedules</h1>
        <p className="text-sm text-slate-500 mt-0.5">Weekly clinic hours. Appointment slots are generated from these (hospital local time).</p>
      </div>
      <DemoDataBanner />
      <Select className="w-64" value={doctorId} onChange={(e) => { setDoctorId(e.target.value); setMessage(null); }}>
        <option value="">Select doctor…</option>
        {doctors?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
      </Select>

      {doctorId && (
        <Card>
          <CardContent className="space-y-3 p-4">
            {blocks.length === 0 && <p className="text-sm text-slate-400">No clinic hours yet.</p>}
            {blocks.map((b, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <select className={cell} value={b.weekday} disabled={!canEdit} onChange={(e) => patch(i, { weekday: Number(e.target.value) })}>
                  {DAYS.map((d, n) => <option key={d} value={n}>{d}</option>)}
                </select>
                <input type="time" className={cell} value={b.start} disabled={!canEdit} onChange={(e) => patch(i, { start: e.target.value })} />
                <span className="text-slate-400">to</span>
                <input type="time" className={cell} value={b.end} disabled={!canEdit} onChange={(e) => patch(i, { end: e.target.value })} />
                <select className={cell} value={b.slot_minutes} disabled={!canEdit} onChange={(e) => patch(i, { slot_minutes: Number(e.target.value) })}>
                  {[10, 15, 20, 30, 45, 60].map((m) => <option key={m} value={m}>{m} min</option>)}
                </select>
                {canEdit && <Button size="sm" variant="ghost" aria-label="Remove block" onClick={() => setBlocks((bs) => bs.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>}
              </div>
            ))}
            {message && <p className={`rounded px-3 py-2 text-sm ${message.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-600"}`}>{message.text}</p>}
            {canEdit ? (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setBlocks((bs) => [...bs, { weekday: 0, start: "09:00", end: "13:00", slot_minutes: 15 }])}><Plus className="mr-1 h-4 w-4" /> Add hours</Button>
                <Button size="sm" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save schedule"}</Button>
              </div>
            ) : <p className="text-xs text-slate-400">Only doctors and administrators can change schedules.</p>}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
