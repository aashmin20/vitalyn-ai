import { apiFetch } from "./client";
import type { Patient } from "../types";

export type AppointmentStatus = "scheduled" | "checked_in" | "in_consult" | "completed" | "cancelled" | "no_show";

export interface Appointment {
  id: string;
  start_at: string;            // hospital wall-clock time, "YYYY-MM-DDTHH:MM"
  end_at: string;
  status: AppointmentStatus;
  reason: string | null;
  patient: { id: string; patient_code: string; name: string; age: number; status: string } | null;
  doctor: { id: string; name: string; department: string | null } | null;
}

export interface Slot {
  start: string;
  end: string;
  free: boolean;
}

export interface ScheduleBlock {
  weekday: number;
  start: string;
  end: string;
  slot_minutes: number;
}

export const registerOutpatient = (data: { name: string; age: number; reason?: string | null; phone?: string | null }) =>
  apiFetch<Patient>("/api/v1/patients/register", { method: "POST", body: JSON.stringify(data) });

export const getAvailability = (doctorId: string, date: string) =>
  apiFetch<Slot[]>(`/api/v1/doctors/${doctorId}/availability?date=${date}`);

export const getSchedule = (doctorId: string) => apiFetch<ScheduleBlock[]>(`/api/v1/doctors/${doctorId}/schedule`);

export const putSchedule = (doctorId: string, blocks: ScheduleBlock[]) =>
  apiFetch<ScheduleBlock[]>(`/api/v1/doctors/${doctorId}/schedule`, { method: "PUT", body: JSON.stringify(blocks) });

export const listAppointments = (p: { date?: string; doctorId?: string } = {}) => {
  const q = new URLSearchParams();
  if (p.date) q.set("date", p.date);
  if (p.doctorId) q.set("doctor_id", p.doctorId);
  return apiFetch<Appointment[]>(`/api/v1/appointments?${q.toString()}`);
};

export const bookAppointment = (data: { patient_id: string; doctor_id: string; start_at: string; reason?: string | null }) =>
  apiFetch<Appointment>("/api/v1/appointments", { method: "POST", body: JSON.stringify(data) });

export const setAppointmentStatus = (id: string, status: Exclude<AppointmentStatus, "scheduled">) =>
  apiFetch<Appointment>(`/api/v1/appointments/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });

/** Today's date in the browser's local time as YYYY-MM-DD (the hospital's wall clock). */
export const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const timeOf = (iso: string) => iso.slice(11, 16);

export const admitOutpatient = (id: string, data: { doctor_id: string; room_id: string; bed_id?: string | null; condition?: string | null }) =>
  apiFetch<import("../types").AdmitResponse>(`/api/v1/patients/${id}/admit`, { method: "POST", body: JSON.stringify(data) });
