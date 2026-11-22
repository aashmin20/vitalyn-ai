"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { formatDistanceToNow, format } from "date-fns";
import { ArrowLeft, QrCode, LogOut, Trash2, History, Video, ArrowRightLeft, Printer, RotateCcw } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import {
  deletePatient,
  describeApiError,
  dischargePatient,
  getPatient,
  listDoctors,
  regenerateCameraLink,
  type DischargeSummary,
} from "@/lib/api/patients";
import { freeBeds, getTimeline, getWardBoard, readmitPatient, transferPatient, type TimelineItem, type WardBoard } from "@/lib/api/adt";
import { listRooms } from "@/lib/api/rooms";
import { Select } from "@/components/ui/select";
import { admitOutpatient } from "@/lib/api/opd";
import { useAuth } from "@/components/auth/AuthProvider";
import { getLiveStatus } from "@/lib/api/live";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import { PatientQr } from "@/components/patients/PatientQr";
import { parseUtc } from "@/lib/utils";
import type { CameraLink, Doctor, LiveStatus, Patient, Room } from "@/lib/types";

type Confirm = "discharge" | "delete" | "transfer" | "readmit" | "admit" | null;

const KIND_LABEL: Record<TimelineItem["kind"], string> = {
  admitted: "Admitted",
  transferred: "Transferred",
  discharged: "Discharged",
  readmitted: "Re-admitted",
  fall_event: "Possible fall",
};
const field = "mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900";

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const role = user?.role;
  const isClinical = role === "admin" || role === "doctor" || role === "nurse";
  const isDoctor = role === "admin" || role === "doctor";
  const canRegister = isDoctor || role === "receptionist";
  const [link, setLink] = useState<CameraLink | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: patient, loading, refetch } = usePoll<Patient>(useCallback(() => getPatient(id), [id]), 10_000);
  const { data: timeline, refetch: refetchTimeline } = usePoll<TimelineItem[]>(useCallback(() => getTimeline(id), [id]), 10_000);
  const { data: rooms } = usePoll<Room[]>(useCallback(() => listRooms(), []), 60_000);
  const { data: board } = usePoll<WardBoard>(useCallback(() => getWardBoard(), []), 10_000);
  const { data: doctors } = usePoll<Doctor[]>(useCallback(() => listDoctors(), []), 60_000);
  const [doctorId, setDoctorId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [bedId, setBedId] = useState("");
  const [moveNote, setMoveNote] = useState("");
  const [dType, setDType] = useState<DischargeSummary["type"]>("home");
  const [dDiagnosis, setDDiagnosis] = useState("");
  const [dInstructions, setDInstructions] = useState("");
  const [dFollowUp, setDFollowUp] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const { data: live } = usePoll<LiveStatus>(useCallback(() => getLiveStatus(), []), 3_000);

  const monitoring = live?.state === "live" && live.patient_id === id;

  const regenerate = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await regenerateCameraLink(id);
      setLink(r.camera_link);
      setNote(r.camera_link_note);
      refetch();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const runConfirmed = async () => {
    setBusy(true);
    setError(null);
    try {
      if (confirm === "discharge") {
        await dischargePatient(id, {
          type: dType,
          diagnosis: dDiagnosis.trim() || null,
          instructions: dInstructions.trim() || null,
          follow_up_date: dFollowUp || null,
        });
        setLink(null);
        refetch();
        refetchTimeline();
        setConfirm(null);
      } else if (confirm === "transfer") {
        if (!roomId || !bedId) throw new Error("Choose a room and a free bed.");
        const r = await transferPatient(id, { room_id: roomId, bed_id: bedId, note: moveNote.trim() || undefined });
        setNotice(r.monitoring_stopped ? "Transferred. The live camera session ended; open the live view again for the new room." : "Transferred.");
        refetch();
        refetchTimeline();
        setConfirm(null);
      } else if (confirm === "admit") {
        if (!roomId || !doctorId) throw new Error("Choose a doctor and a room.");
        const r = await admitOutpatient(id, { doctor_id: doctorId, room_id: roomId, bed_id: bedId || null });
        setLink(r.camera_link);
        setNote(r.camera_link_note);
        refetch();
        refetchTimeline();
        setConfirm(null);
      } else if (confirm === "readmit") {
        if (!roomId) throw new Error("Choose a room.");
        const r = await readmitPatient(id, { room_id: roomId, bed_id: bedId || null });
        setLink(r.camera_link);
        setNote(r.camera_link_note);
        refetch();
        refetchTimeline();
        setConfirm(null);
      } else if (confirm === "delete") {
        await deletePatient(id);
        router.push("/patients");
      }
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Skeleton className="mx-auto h-64 max-w-3xl" />;
  if (!patient) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 text-center text-sm text-slate-500">
        <p>Patient not found.</p>
        <Link href="/patients" className="underline">Back to patients</Link>
      </div>
    );
  }

  const admitted = patient.status === "admitted";
  const outpatient = patient.status === "outpatient";
  const openMove = (kind: "transfer" | "readmit" | "admit") => {
    setDoctorId(patient.doctor?.id ?? "");
    setRoomId(patient.room?.id ?? "");
    setBedId("");
    setMoveNote("");
    setError(null);
    setConfirm(kind);
  };
  const discharge = timeline?.find((t) => t.kind === "discharged");

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Link href="/patients" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800">
        <ArrowLeft className="h-3.5 w-3.5" /> All patients
      </Link>
      <DemoDataBanner />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
            <span className="font-mono text-base text-slate-500">{patient.patient_code}</span>
            {patient.name}, {patient.age}
            <Badge variant={admitted ? "success" : outpatient ? "warning" : "muted"}>{patient.status}</Badge>
            {monitoring && <Badge variant="destructive">Monitoring live</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-sm">
          <Info label="Condition" value={patient.condition} />
          <Info label="Room / bed" value={patient.room ? `Room ${patient.room.room_number}${patient.bed_number ? ` · bed ${patient.bed_number}` : ""}` : "-"} />
          {patient.sex && <Info label="Sex" value={patient.sex} />}
          {patient.phone && <Info label="Phone" value={patient.phone} />}
          {patient.emergency_contact && <Info label="Emergency contact" value={patient.emergency_contact} />}
          {patient.allergies && <Info label="Allergies" value={patient.allergies} />}
          <Info label="Doctor" value={patient.doctor?.name ?? "-"} />
          <Info label="Admitted" value={format(parseUtc(patient.admitted_at), "MMM d, yyyy HH:mm")} />
          <Info
            label="Registered camera"
            value={
              patient.camera_kind
                ? `${patient.camera_label ?? patient.camera_kind}${patient.camera_kind === "phone" ? (patient.phone_online ? " · online" : " · offline") : ""}`
                : "None yet (register it on Watch Live)"
            }
          />
          {patient.discharged_at && (
            <Info label="Discharged" value={format(parseUtc(patient.discharged_at), "MMM d, yyyy HH:mm")} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <QrCode className="h-4 w-4" /> Camera QR
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!admitted ? (
            <p className="text-sm text-slate-500">{outpatient ? "Outpatients have no camera QR; it is issued when they are admitted." : "Discharged: the camera QR no longer works."}</p>
          ) : link ? (
            <PatientQr link={link} patientCode={patient.patient_code} roomNumber={patient.room?.room_number ?? null} />
          ) : (
            <p className="text-sm text-slate-600">
              {patient.has_camera_link
                ? "A camera QR is active for this patient. For security it cannot be shown again."
                : "No camera QR is active."}{" "}
              Generate a new one to print or scan; the old QR stops working.
            </p>
          )}
          {note && <p className="rounded bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900">{note}</p>}
          {admitted && isClinical && (
            <Button size="sm" variant="outline" onClick={regenerate} disabled={busy}>
              {link ? "Regenerate again" : "Generate new QR"}
            </Button>
          )}
          {monitoring && (
            <p className="text-[11px] text-slate-400">Regenerating the QR also ends the current live session.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <History className="h-4 w-4" /> Timeline
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!timeline || timeline.length === 0 ? (
            <p className="py-4 text-center text-sm text-slate-400">No history yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {timeline.map((t, i) => (
                <li key={i} className="flex items-start justify-between gap-4 py-2 text-sm">
                  <span className="text-slate-800">
                    <Badge variant={t.kind === "fall_event" ? "destructive" : "muted"}>{KIND_LABEL[t.kind]}</Badge>{" "}
                    {t.from && t.to ? `${t.from} → ${t.to}` : t.to ?? t.from ?? ""}
                    {t.note && <span className="block text-xs text-slate-500">{t.note}</span>}
                    {t.by && <span className="block text-[11px] text-slate-400">by {t.by}</span>}
                  </span>
                  <span className="shrink-0 text-xs text-slate-400">
                    {format(parseUtc(t.at), "MMM d, HH:mm")}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[11px] text-slate-400">Every fall detection needs human review. Not clinically validated.</p>
        </CardContent>
      </Card>

      {!admitted && discharge?.summary && (
        <Card className="print:shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-sm font-semibold text-slate-700">
              Discharge summary
              <Button size="sm" variant="outline" className="print:hidden" onClick={() => window.print()}>
                <Printer className="mr-2 h-4 w-4" /> Print
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm">
            <Info label="Patient" value={`${patient.patient_code} · ${patient.name}`} />
            <Info label="Type" value={discharge.summary.type} />
            <Info label="Diagnosis" value={discharge.summary.diagnosis || patient.condition} />
            <Info label="Follow-up" value={discharge.summary.follow_up_date || "-"} />
            <div className="col-span-2"><Info label="Instructions" value={discharge.summary.instructions || "-"} /></div>
            <p className="col-span-2 text-[11px] text-amber-700">DEMO DATA: fictional patient, not a medical record.</p>
          </CardContent>
        </Card>
      )}

      {notice && <p className="rounded bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</p>}
      {error && !confirm && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}

      <div className="flex flex-wrap gap-2">
        {admitted && isClinical && (
          <Button variant="outline" onClick={() => openMove("transfer")}>
            <ArrowRightLeft className="mr-2 h-4 w-4" /> Transfer
          </Button>
        )}
        {admitted && isDoctor && (
          <Button variant="outline" onClick={() => { setError(null); setConfirm("discharge"); }}>
            <LogOut className="mr-2 h-4 w-4" /> Discharge
          </Button>
        )}
        {outpatient && canRegister && (
          <Button variant="outline" onClick={() => openMove("admit")}>
            <RotateCcw className="mr-2 h-4 w-4" /> Admit to ward
          </Button>
        )}
        {!admitted && !outpatient && canRegister && (
          <Button variant="outline" onClick={() => openMove("readmit")}>
            <RotateCcw className="mr-2 h-4 w-4" /> Re-admit
          </Button>
        )}
        {admitted && isClinical && (
          <Link href={`/monitoring/watch?patient=${patient.id}`}>
            <Button variant="outline">
              <Video className="mr-2 h-4 w-4" /> {monitoring ? "Watch live" : "Open live view"}
            </Button>
          </Link>
        )}
        {role === "admin" && (
          <Button variant="ghost" className="text-red-600 hover:text-red-700" onClick={() => setConfirm("delete")}>
            <Trash2 className="mr-2 h-4 w-4" /> Delete record (demo cleanup)
          </Button>
        )}
      </div>

      <Dialog open={!!confirm} onOpenChange={(open) => !open && !busy && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirm === "delete" ? "Delete patient record" : confirm === "admit" ? "Admit to ward" : confirm === "transfer" ? "Transfer patient" : confirm === "readmit" ? "Re-admit patient" : "Discharge patient"}
            </DialogTitle>
            <DialogDescription>
              {confirm === "delete"
                ? "This permanently removes the patient's details. Their fall events stay in the system without the patient link. This cannot be undone."
                : confirm === "admit"
                  ? "Admits this outpatient to a ward and issues their camera QR."
                  : confirm === "transfer"
                  ? "Moves the patient to a free bed. The bed they leave goes to cleaning, and a live camera session for the old room ends."
                  : confirm === "readmit"
                    ? "Starts a new stay in a free bed and issues a new camera QR."
                    : "This ends monitoring for this patient, revokes their camera QR, stops any live session and sends the bed to cleaning."}
            </DialogDescription>
          </DialogHeader>
          {(confirm === "transfer" || confirm === "readmit" || confirm === "admit") && (
            <div className="space-y-3">
              {confirm === "admit" && (
                <label className="block text-xs font-medium text-slate-600">
                  Doctor
                  <Select className="mt-1" value={doctorId} onChange={(e) => setDoctorId(e.target.value)} disabled={busy}>
                    <option value="">Select doctor…</option>
                    {doctors?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </Select>
                </label>
              )}
              <label className="block text-xs font-medium text-slate-600">
                Room
                <Select className="mt-1" value={roomId} onChange={(e) => { setRoomId(e.target.value); setBedId(""); }} disabled={busy}>
                  <option value="">Select room…</option>
                  {rooms?.map((r) => <option key={r.id} value={r.id}>Room {r.room_number} · Floor {r.floor}</option>)}
                </Select>
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Free bed
                <Select className="mt-1" value={bedId} onChange={(e) => setBedId(e.target.value)} disabled={busy || !roomId}>
                  <option value="">{confirm === "readmit" ? "Not assigned" : "Select bed…"}</option>
                  {freeBeds(board, roomId).map((b) => <option key={b.id} value={b.id}>Bed {b.bed_number}</option>)}
                </Select>
              </label>
              {confirm === "transfer" && (
                <label className="block text-xs font-medium text-slate-600">
                  Reason (optional)
                  <input className={field} value={moveNote} maxLength={200} onChange={(e) => setMoveNote(e.target.value)} disabled={busy} />
                </label>
              )}
            </div>
          )}
          {confirm === "discharge" && (
            <div className="space-y-3">
              <label className="block text-xs font-medium text-slate-600">
                Discharge type
                <Select className="mt-1" value={dType} onChange={(e) => setDType(e.target.value as DischargeSummary["type"])} disabled={busy}>
                  <option value="home">Home</option>
                  <option value="transfer">Transfer to another facility</option>
                  <option value="ama">Against medical advice</option>
                  <option value="other">Other</option>
                </Select>
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Final diagnosis (optional)
                <input className={field} value={dDiagnosis} maxLength={200} onChange={(e) => setDDiagnosis(e.target.value)} disabled={busy} />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Instructions (optional)
                <textarea className={field} rows={3} value={dInstructions} maxLength={500} onChange={(e) => setDInstructions(e.target.value)} disabled={busy} />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Follow-up date (optional)
                <input type="date" className={field} value={dFollowUp} onChange={(e) => setDFollowUp(e.target.value)} disabled={busy} />
              </label>
            </div>
          )}
          {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)} disabled={busy}>Cancel</Button>
            <Button variant={confirm === "delete" ? "destructive" : "default"} onClick={runConfirmed} disabled={busy}>
              {busy ? "Working…" : confirm === "delete" ? "Delete" : confirm === "admit" ? "Admit" : confirm === "transfer" ? "Transfer" : confirm === "readmit" ? "Re-admit" : "Discharge"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="text-slate-800">{value}</p>
    </div>
  );
}
