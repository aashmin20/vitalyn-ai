import { apiFetch } from "./client";
import type { FallEvent } from "../types";

export const listFallEvents = () =>
  apiFetch<FallEvent[]>("/api/v1/events/falls");

export const getFallEvent = (id: string) =>
  apiFetch<FallEvent>(`/api/v1/events/falls/${id}`);

export const resolveFallEvent = (eventId: string) =>
  apiFetch<FallEvent>(`/api/v1/events/falls/${eventId}/resolve`, { method: "PATCH" });
