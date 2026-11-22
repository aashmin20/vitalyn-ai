import { apiFetch, apiUrl } from "./client";
import type { LiveSources, LiveStatus } from "../types";

export const startLive = (roomId: string, source: string, patientId?: string) =>
  apiFetch<LiveStatus>("/api/v1/live/start", {
    method: "POST",
    body: JSON.stringify({ room_id: roomId, source, ...(patientId ? { patient_id: patientId } : {}) }),
  });

export const stopLive = (patientId?: string) =>
  apiFetch<LiveStatus & { stopped: boolean }>(`/api/v1/live/stop${patientId ? `?patient_id=${encodeURIComponent(patientId)}` : ""}`, { method: "POST" });

export const getLiveStatus = () => apiFetch<LiveStatus>("/api/v1/live/status");

export const liveStreamUrl = (cacheKey: string, patientId?: string) =>
  `${apiUrl("/api/v1/live/stream")}?${patientId ? `patient_id=${encodeURIComponent(patientId)}&` : ""}s=${encodeURIComponent(cacheKey)}`;

export const liveSnapshotUrl = (index: number, nonce: number) =>
  `${apiUrl("/api/v1/live/snapshot")}?index=${index}&t=${nonce}`;

export const liveEventsUrl = () => apiUrl("/api/v1/live/events");

export const getLiveSources = () => apiFetch<LiveSources>("/api/v1/live/sources");

