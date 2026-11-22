"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { UserPlus, CheckCircle2 } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listRooms } from "@/lib/api/rooms";
import { freeBeds, getWardBoard, type WardBoard } from "@/lib/api/adt";
import { admitPatient, createDoctor, describeApiError, listDoctors } from "@/lib/api/patients";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import { PatientQr } from "@/components/patients/PatientQr";
import type { AdmitResponse, Doctor, Room } from "@/lib/types";

const inputClass =
  "mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900 disabled:opacity-50";

export default function AdmitPatientPage() {
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [condition, setCondition] = useState("");
  const [roomId, setRoomId] = useState("");
  const [bedId, setBedId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [sex, setSex] = useState("");
  const [phone, setPhone] = useState("");
  const [emergency, setEmergency] = useState("");
  const [allergies, setAllergies] = useState("");
  const [addingDoctor, setAddingDoctor] = useState(false);
  const [docName, setDocName] = useState("");
  const [docDept, setDocDept] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdmitResponse | null>(null);

  const { data: rooms } = usePoll<Room[]>(useCallback(() => listRooms(), []), 60_000);
  const { data: doctors, refetch: refetchDoctors } = usePoll<Doctor[]>(useCallback(() => listDoctors(), []), 30_000);
  const { data: board } = usePoll<WardBoard>(useCallback(() => getWardBoard(), []), 15_000);
  const beds = freeBeds(board, roomId);

  const validate = (): string | null => {
    const n = name.trim();
    const a = Number(age);
    if (!n) return "Enter the patient's name.";
    if (n.length > 80) return "Name must be 80 characters or fewer.";
    if (age.trim() === "" || !Number.isInteger(a) || a < 0 || a > 130) return "Age must be a whole number from 0 to 130.";
    if (!condition.trim()) return "Enter the condition / diagnosis.";
    if (condition.trim().length > 200) return "Condition must be 200 characters or fewer.";
    if (!roomId) return "Choose a room.";
    if (!doctorId) return "Choose the allotted doctor.";
    return null;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const problem = validate();
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      setResult(
        await admitPatient({
          name: name.trim(),
          age: Number(age),
          condition: condition.trim(),
          doctor_id: doctorId,
          room_id: roomId,
          bed_id: bedId || null,
          sex: (sex || null) as "female" | "male" | "other" | null,
          phone: phone.trim() || null,
          emergency_contact: emergency.trim() || null,
          allergies: allergies.trim() || null,
        }),
      );
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const saveDoctor = async () => {
    if (!docName.trim()) return setError("Enter the doctor's name.");
    try {
      const d = await createDoctor({ name: docName.trim(), department: docDept.trim() || undefined });
      refetchDoctors();
      setDoctorId(d.id);
      setAddingDoctor(false);
      setDocName("");
      setDocDept("");
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    }
  };

  const reset = () => {
    setResult(null);
    setName("");
    setAge("");
    setCondition("");
    setBedId("");
    setSex("");
    setPhone("");
    setEmergency("");
    setAllergies("");
  };

  if (result) {
    const p = result.patient;
    return (
      <div className="max-w-xl mx-auto space-y-6">
        <DemoDataBanner />
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base text-emerald-700">
              <CheckCircle2 className="w-5 h-5" /> Patient {p.patient_code} admitted
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <p className="text-sm text-slate-600">
              {p.name}, {p.age} · {p.condition}
              <br />
              Room {p.room?.room_number} · {p.doctor?.name}
            </p>
            {result.camera_link ? (
              <PatientQr link={result.camera_link} patientCode={p.patient_code} roomNumber={p.room?.room_number ?? null} />
            ) : (
              <p className="rounded bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900">
                {result.camera_link_note ?? "No camera link was created."}
              </p>
            )}
            <div className="flex gap-2">
              <Link href={`/patients/${p.id}`} className="flex-1">
                <Button variant="outline" className="w-full">Open patient</Button>
              </Link>
              <Button className="flex-1" onClick={reset}>Admit another</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Admit patient</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Enter the details, then print the patient&apos;s camera QR code.
        </p>
      </div>
      <DemoDataBanner />

      <Card>
        <CardContent className="p-5">
          <form onSubmit={submit} className="space-y-4" noValidate>
            <label className="block text-xs font-medium text-slate-600">
              Patient name
              <input className={inputClass} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} disabled={busy} />
            </label>

            <label className="block text-xs font-medium text-slate-600">
              Age
              <input
                className={inputClass}
                inputMode="numeric"
                value={age}
                onChange={(e) => setAge(e.target.value.replace(/[^0-9]/g, "").slice(0, 3))}
                disabled={busy}
              />
            </label>

            <label className="block text-xs font-medium text-slate-600">
              Condition / diagnosis
              <input className={inputClass} value={condition} maxLength={200} onChange={(e) => setCondition(e.target.value)} disabled={busy} />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs font-medium text-slate-600">
                Sex (optional)
                <Select className="mt-1" value={sex} onChange={(e) => setSex(e.target.value)} disabled={busy}>
                  <option value="">Not stated</option>
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                  <option value="other">Other</option>
                </Select>
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Phone (optional)
                <input className={inputClass} value={phone} maxLength={30} onChange={(e) => setPhone(e.target.value)} disabled={busy} />
              </label>
            </div>
            <label className="block text-xs font-medium text-slate-600">
              Emergency contact (optional)
              <input className={inputClass} value={emergency} maxLength={120} onChange={(e) => setEmergency(e.target.value)} disabled={busy} />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Allergies (optional)
              <input className={inputClass} value={allergies} maxLength={200} onChange={(e) => setAllergies(e.target.value)} disabled={busy} />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs font-medium text-slate-600">
                Room
                <Select
                  className="mt-1"
                  value={roomId}
                  onChange={(e) => {
                    setRoomId(e.target.value);
                    setBedId("");
                  }}
                  disabled={busy}
                >
                  <option value="">Select room…</option>
                  {rooms?.map((r) => (
                    <option key={r.id} value={r.id}>
                      Room {r.room_number} · Floor {r.floor}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Free bed (optional)
                <Select className="mt-1" value={bedId} onChange={(e) => setBedId(e.target.value)} disabled={busy || !roomId}>
                  <option value="">Not assigned</option>
                  {beds.map((b) => (
                    <option key={b.id} value={b.id}>
                      Bed {b.bed_number}
                    </option>
                  ))}
                </Select>
              </label>
            </div>
            {rooms && rooms.length === 0 && (
              <p className="text-xs text-amber-700">
                No rooms yet. <Link href="/operations/rooms" className="underline">Add a room first</Link>.
              </p>
            )}

            <div>
              <label className="block text-xs font-medium text-slate-600">
                Allotted doctor
                <Select className="mt-1" value={doctorId} onChange={(e) => setDoctorId(e.target.value)} disabled={busy}>
                  <option value="">Select doctor…</option>
                  {doctors?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                      {d.department ? ` · ${d.department}` : ""}
                    </option>
                  ))}
                </Select>
              </label>
              {!addingDoctor ? (
                <button type="button" className="mt-1 text-[11px] text-slate-500 underline" onClick={() => setAddingDoctor(true)}>
                  Add a new doctor
                </button>
              ) : (
                <div className="mt-2 space-y-2 rounded-lg border border-slate-200 p-3">
                  <input className={inputClass} placeholder="Doctor name" value={docName} maxLength={80} onChange={(e) => setDocName(e.target.value)} />
                  <input className={inputClass} placeholder="Department (optional)" value={docDept} maxLength={60} onChange={(e) => setDocDept(e.target.value)} />
                  <div className="flex gap-2">
                    <Button type="button" size="sm" onClick={saveDoctor}>Save doctor</Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setAddingDoctor(false)}>Cancel</Button>
                  </div>
                </div>
              )}
            </div>

            {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2 break-words">{error}</p>}

            <Button type="submit" className="w-full" disabled={busy}>
              <UserPlus className="mr-2 h-4 w-4" /> {busy ? "Admitting…" : "Admit patient and create QR"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
