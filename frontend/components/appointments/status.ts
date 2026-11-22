import type { AppointmentStatus } from "@/lib/api/opd";

export const STATUS_VARIANT: Record<AppointmentStatus, "success" | "warning" | "muted" | "destructive" | "default"> = {
  scheduled: "muted",
  checked_in: "warning",
  in_consult: "default",
  completed: "success",
  cancelled: "muted",
  no_show: "destructive",
};
