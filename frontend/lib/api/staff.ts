import { apiFetch } from "./client";
import type { Role } from "./auth";

export interface StaffMember {
  id: string;
  name: string;
  email: string;
  role: Role;
  status: "pending" | "active" | "disabled";
  created_at: string;
  last_login_at: string | null;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  entity: string | null;
  entity_id: string | null;
  detail: string | null;
  ip: string | null;
}

export const listStaff = () => apiFetch<StaffMember[]>("/api/v1/staff");

export const updateStaff = (id: string, change: { role?: Role; status?: StaffMember["status"] }) =>
  apiFetch<StaffMember>(`/api/v1/staff/${id}`, { method: "PATCH", body: JSON.stringify(change) });

export const listAudit = (params: { action?: string; actor?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.action) q.set("action", params.action);
  if (params.actor) q.set("actor", params.actor);
  q.set("limit", String(params.limit ?? 100));
  return apiFetch<AuditEntry[]>(`/api/v1/audit?${q.toString()}`);
};
