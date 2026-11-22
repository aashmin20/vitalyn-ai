"use client";

import { useState } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { useAlertContext } from "@/lib/hooks/useAlertContext";
import { parseUtc } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, Archive } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { acknowledgeAlert, resolveAlert } from "@/lib/api/alerts";
import type { Alert } from "@/lib/types";

interface Props {
  alerts: Alert[];
  mode: "active" | "acknowledged" | "resolved";
  onRefresh: () => void;
}

const severityVariant = {
  high: "destructive",
  medium: "warning",
  low: "info",
} as const;

export function AlertTable({ alerts, mode, onRefresh }: Props) {
  const contextFor = useAlertContext();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [action, setAction] = useState<"acknowledge" | "resolve" | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openDialog = (id: string, act: "acknowledge" | "resolve") => {
    setPendingId(id);
    setAction(act);
    setError(null);
  };

  const closeDialog = () => {
    setPendingId(null);
    setAction(null);
    setError(null);
  };

  const handleConfirm = async () => {
    if (!pendingId || !action) return;
    setLoading(true);
    try {
      if (action === "acknowledge") await acknowledgeAlert(pendingId);
      else await resolveAlert(pendingId);
      closeDialog();
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setLoading(false);
    }
  };

  if (alerts.length === 0) {
    const EmptyIcon = mode === "active" ? AlertTriangle : mode === "acknowledged" ? CheckCircle2 : Archive;
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-400">
        <EmptyIcon className="w-10 h-10 mb-3 opacity-30" />
        <p className="text-sm">No {mode} alerts</p>
      </div>
    );
  }

  return (
    <>
      <div className="divide-y divide-slate-100">
        {alerts.map((alert) => (
          <div key={alert.id} className="flex items-start justify-between py-4 gap-4">
            <div className="flex items-start gap-3 min-w-0">
              <AlertTriangle className={`w-4 h-4 mt-0.5 shrink-0 ${
                alert.severity === "high" ? "text-red-500" :
                alert.severity === "medium" ? "text-amber-500" : "text-blue-400"
              }`} />
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-800 capitalize">
                    {alert.alert_type.replace(/_/g, " ")}
                  </span>
                  <Badge variant={severityVariant[alert.severity] ?? "secondary"}>
                    {alert.severity}
                  </Badge>
                  <Badge variant="muted">{alert.status}</Badge>
                </div>
                {(() => {
                  const ctx = contextFor(alert.fall_event_id);
                  if (!ctx) return null;
                  const when = ctx.event.started_at ?? alert.created_at;
                  return (
                    <p className="text-xs text-slate-600 mt-0.5">
                      {[
                        ctx.patientLabel,
                        ctx.roomLabel,
                        ctx.doctorName ? `Dr: ${ctx.doctorName.replace(/^Dr\.?\s*/i, "")}` : null,
                        ctx.sourceLabel,
                        `confidence ${(ctx.event.confidence * 100).toFixed(0)}%`,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                      {" · "}
                      {format(parseUtc(when), "MMM d, HH:mm:ss")}
                    </p>
                  );
                })()}
                <p className="text-xs text-slate-400 mt-0.5">
                  Created {formatDistanceToNow(parseUtc(alert.created_at), { addSuffix: true })}
                </p>
                {alert.acknowledged_at && (
                  <p className="text-xs text-slate-400">
                    Acknowledged {formatDistanceToNow(new Date(alert.acknowledged_at), { addSuffix: true })}
                  </p>
                )}
                {alert.resolved_at && (
                  <p className="text-xs text-slate-400">
                    Resolved {formatDistanceToNow(new Date(alert.resolved_at), { addSuffix: true })}
                  </p>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 shrink-0">
              {mode === "active" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => openDialog(alert.id, "acknowledge")}
                >
                  Acknowledge
                </Button>
              )}
              {mode === "acknowledged" && (
                <Button
                  size="sm"
                  variant="success"
                  onClick={() => openDialog(alert.id, "resolve")}
                >
                  Resolve
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Confirm dialog */}
      <Dialog open={!!pendingId} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {action === "acknowledge" ? "Acknowledge Alert" : "Resolve Alert"}
            </DialogTitle>
            <DialogDescription>
              {action === "acknowledge"
                ? "Acknowledging marks this potential fall as seen and under review. It is not yet confirmed or cleared."
                : "Resolving closes this alert and its fall event. Only resolve after physically verifying the patient is safe."}
            </DialogDescription>
          </DialogHeader>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={closeDialog} disabled={loading}>
              Cancel
            </Button>
            <Button
              variant={action === "acknowledge" ? "default" : "success"}
              onClick={handleConfirm}
              disabled={loading}
            >
              {loading ? "Processing…" : action === "acknowledge" ? "Acknowledge" : "Resolve"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
