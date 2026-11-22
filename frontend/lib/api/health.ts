import { apiFetch } from "./client";

export interface HealthStatus {
  status: "healthy" | "degraded" | "unhealthy";
  components: Record<string, string>;
  live_sessions?: number;
}

export const getHealth = () => apiFetch<HealthStatus>("/health");
