"use client";

import { useCallback, useMemo } from "react";
import { usePoll } from "./usePoll";
import { listFallEvents } from "../api/events";
import { listRooms } from "../api/rooms";
import { listJobs } from "../api/jobs";
import { listPatients } from "../api/patients";
import type { FallEvent } from "../types";

export interface AlertContext {
  event: FallEvent;
  roomLabel: string | null;
  sourceLabel: string | null;   // "Live camera" or the uploaded video's file name
  patientLabel: string | null;  // "P-0001 · Name"
  doctorName: string | null;
}

/** Joins fall event + room + job so an alert row can say where/when it came from. */
export function useAlertContext(): (fallEventId: string | null) => AlertContext | null {
  const { data: events } = usePoll(useCallback(() => listFallEvents(), []), 10_000);
  const { data: rooms } = usePoll(useCallback(() => listRooms(), []), 60_000);
  const { data: jobs } = usePoll(useCallback(() => listJobs(), []), 15_000);
  const { data: patients } = usePoll(useCallback(() => listPatients("all"), []), 30_000);

  return useMemo(() => {
    const eventById = new Map((events ?? []).map((e) => [e.id, e]));
    const roomById = new Map((rooms ?? []).map((r) => [r.id, r]));
    const jobById = new Map((jobs ?? []).map((j) => [j.id, j]));
    const patientById = new Map((patients ?? []).map((p) => [p.id, p]));
    return (fallEventId: string | null) => {
      if (!fallEventId) return null;
      const event = eventById.get(fallEventId);
      if (!event) return null;
      const room = event.room_id ? roomById.get(event.room_id) : undefined;
      const job = event.inference_job_id ? jobById.get(event.inference_job_id) : undefined;
      const patient = event.patient_id ? patientById.get(event.patient_id) : undefined;
      return {
        event,
        patientLabel: patient ? `${patient.patient_code} · ${patient.name}` : null,
        doctorName: patient?.doctor?.name ?? null,
        roomLabel: room ? `Room ${room.room_number}` : null,
        sourceLabel: job ? (job.video_path.startsWith("camera:") ? "Live camera" : job.video_filename) : null,
      };
    };
  }, [events, rooms, jobs, patients]);
}
