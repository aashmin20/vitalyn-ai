import { apiFetch } from "./client";
import type { Alert } from "../types";

export const listAlerts = () =>
  apiFetch<Alert[]>("/api/v1/alerts");

export const getAlert = (id: string) =>
  apiFetch<Alert>(`/api/v1/alerts/${id}`);

export const acknowledgeAlert = (alertId: string) =>
  apiFetch<Alert>(`/api/v1/alerts/${alertId}/acknowledge`, { method: "PATCH" });

export const resolveAlert = (alertId: string) =>
  apiFetch<Alert>(`/api/v1/alerts/${alertId}/resolve`, { method: "PATCH" });
