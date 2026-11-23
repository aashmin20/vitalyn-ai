import { apiFetch } from "./client";
import type { AdmitResponse, Patient } from "../types";
import type { DischargeSummary } from "./patients";

export type BedState = "occupied" | "available" | "cleaning" | "maintenance";

export interface BoardPatient {
  id: string;
  patient_code: string;
  name: string;
  age: number;
  doctor: string | null;
  // present only for clinical roles
  condition?: string;
  monitored?: boolean;
  active_alerts?: number;
}

export interface BoardBed {
  id: string;
  bed_number: string;
  status: BedState;
  patient: BoardPatient | null;
}

export interface BoardRoom {
  id: string;
  room_number: string;
  floor: string;
  beds: BoardBed[];
  unassigned: BoardPatient[];
  summary: Record<BedState, number>;
}

export interface WardBoard {
  rooms: BoardRoom[];
  counts: Record<BedState, number>;
}

export interface TimelineItem {
  kind: "admitted" | "transferred" | "discharged" | "readmitted" | "fall_event";
  at: string;
  by: string | null;
  from: string | null;
  to: string | null;
  note: string | null;
  summary: DischargeSummary | null;
}

export const getWardBoard = () => apiFetch<WardBoard>("/api/v1/ward-board");

export const getTimeline = (id: string) => apiFetch<TimelineItem[]>(`/api/v1/patients/${id}/timeline`);

export const transferPatient = (id: string, data: { room_id: string; bed_id: string; note?: string }) =>
  apiFetch<{ patient: Patient; monitoring_stopped: boolean }>(`/api/v1/patients/${id}/transfer`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const readmitPatient = (id: string, data: { room_id: string; bed_id?: string | null }) =>
  apiFetch<AdmitResponse>(`/api/v1/patients/${id}/readmit`, { method: "POST", body: JSON.stringify(data) });

export const setBedStatus = (bedId: string, status: "available" | "cleaning" | "maintenance") =>
  apiFetch<{ id: string; status: string }>(`/api/v1/beds/${bedId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

/** Admin: mark every vacant bed in a room; occupied beds are skipped and reported. */
export const setRoomStatus = (roomId: string, status: "available" | "cleaning" | "maintenance") =>
  apiFetch<{ id: string; status: string; changed: string[]; skipped_occupied: string[] }>(
    `/api/v1/rooms/${roomId}/status`,
    { method: "PATCH", body: JSON.stringify({ status }) },
  );

/** Free beds in one room, from the ward board. */
export const freeBeds = (board: WardBoard | null, roomId: string): BoardBed[] =>
  board?.rooms.find((r) => r.id === roomId)?.beds.filter((b) => b.status === "available") ?? [];
