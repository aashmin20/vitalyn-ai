import { apiFetch } from "./client";

export type Role = "admin" | "doctor" | "nurse" | "receptionist" | "none";

export interface AuthUser {
  id: string | null;
  email: string;
  name: string;
  role: Role;
  status: "pending" | "active" | "disabled";
  auth_off?: boolean;
}

export const getMe = () => apiFetch<AuthUser>("/api/v1/auth/me");

export const login = (email: string, password: string) =>
  apiFetch<AuthUser>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });

export const signup = (fullName: string, email: string, password: string) =>
  apiFetch<{ message: string }>("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify({ full_name: fullName, email, password }),
  });

export const logout = () => apiFetch<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" });

/** Plain-text message from an API error body ({"detail": "..."} or {"detail": {"message": "..."}}). */
export function authErrorMessage(e: unknown): string {
  if (e instanceof Error) {
    try {
      const d = JSON.parse(e.message)?.detail;
      if (typeof d === "string") return d;
      if (d && typeof d === "object" && !Array.isArray(d) && "message" in d) return String(d.message);
      if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg).filter(Boolean).join("; ");
    } catch {
      /* not JSON */
    }
    return e.message || "Request failed";
  }
  return "Request failed";
}
