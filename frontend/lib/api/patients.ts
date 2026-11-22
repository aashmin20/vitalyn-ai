import { apiFetch } from "./client";
import type { AdmitResponse, CameraLink, Doctor, FallEvent, NewPatient, Patient } from "../types";

export const listDoctors = () => apiFetch<Doctor[]>("/api/v1/doctors");

export const createDoctor = (data: { name: string; department?: string }) =>
  apiFetch<Doctor>("/api/v1/doctors", { method: "POST", body: JSON.stringify(data) });

export const listPatients = (status: "admitted" | "discharged" | "outpatient" | "all" = "admitted", q = "") =>
  apiFetch<Patient[]>(`/api/v1/patients?status=${status}${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`);

export const getPatient = (id: string) => apiFetch<Patient>(`/api/v1/patients/${id}`);

export const admitPatient = (data: NewPatient) =>
  apiFetch<AdmitResponse>("/api/v1/patients", { method: "POST", body: JSON.stringify(data) });

export const regenerateCameraLink = (id: string) =>
  apiFetch<{ camera_link: CameraLink | null; camera_link_note: string | null }>(
    `/api/v1/patients/${id}/camera-link`,
    { method: "POST" },
  );

export interface DischargeSummary {
  type: "home" | "transfer" | "ama" | "other";
  diagnosis?: string | null;
  instructions?: string | null;
  follow_up_date?: string | null;
}

export const dischargePatient = (id: string, summary?: DischargeSummary) =>
  apiFetch<Patient>(`/api/v1/patients/${id}/discharge`, {
    method: "POST",
    body: summary ? JSON.stringify(summary) : undefined,
  });

export const deletePatient = (id: string) =>
  apiFetch<{ deleted: boolean }>(`/api/v1/patients/${id}`, { method: "DELETE" });

export const getPatientEvents = (id: string) => apiFetch<FallEvent[]>(`/api/v1/patients/${id}/events`);

/** Turn an ApiError body ({"detail": ...}) into a readable message. */
export function describeApiError(e: unknown): string {
  if (e instanceof Error) {
    try {
      const body = JSON.parse(e.message);
      if (typeof body?.detail === "string") return body.detail;
      if (Array.isArray(body?.detail)) {
        return body.detail
          .map((d: { loc?: (string | number)[]; msg?: string }) => `${(d.loc ?? []).slice(-1)[0] ?? "field"}: ${d.msg}`)
          .join("; ");
      }
    } catch {
      /* not JSON */
    }
    return e.message;
  }
  return "Request failed";
}

export const monitorPatient = (id: string) =>
  apiFetch<{ state: "live" | "starting"; kind: "phone" | "webcam" }>(`/api/v1/patients/${id}/monitor`, { method: "POST" });

export const stopMonitoring = (id: string) =>
  apiFetch<{ stopped: boolean }>(`/api/v1/patients/${id}/monitor/stop`, { method: "POST" });

export const registerWebcam = (id: string, index: number) =>
  apiFetch<Patient>(`/api/v1/patients/${id}/camera`, {
    method: "PUT",
    body: JSON.stringify({ kind: "webcam", index }),
  });

export const unregisterCamera = (id: string) =>
  apiFetch<Patient>(`/api/v1/patients/${id}/camera`, { method: "DELETE" });

export interface ApiProblem {
  code?: string;
  message: string;
}

/** Errors from the monitor endpoints carry {code, message}; other errors are plain text. */
export function parseApiProblem(e: unknown): ApiProblem {
  if (e instanceof Error) {
    try {
      const body = JSON.parse(e.message);
      const d = body?.detail;
      if (d && typeof d === "object" && !Array.isArray(d) && "message" in d) {
        return { code: d.code, message: String(d.message) };
      }
    } catch {
      /* not JSON */
    }
  }
  return { message: describeApiError(e) };
}
