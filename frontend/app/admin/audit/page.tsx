"use client";

import { useCallback, useState } from "react";
import { format } from "date-fns";
import { ScrollText } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listAudit, type AuditEntry } from "@/lib/api/staff";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select } from "@/components/ui/select";
import { parseUtc } from "@/lib/utils";

const FILTERS = [
  ["", "Everything"],
  ["auth.", "Sign-ins"],
  ["patient.", "Patient records"],
  ["monitor.", "Monitoring"],
  ["alert.", "Alerts"],
  ["staff.", "Staff changes"],
] as const;

export default function AuditPage() {
  const [action, setAction] = useState("");
  const { data, loading, error } = usePoll<AuditEntry[]>(useCallback(() => listAudit({ action: action || undefined }), [action]), 10_000);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ScrollText className="h-6 w-6" /> Audit log
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Who did what and when (latest 100)</p>
        </div>
        <Select className="w-52" value={action} onChange={(e) => setAction(e.target.value)}>
          {FILTERS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </Select>
      </div>
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-2 p-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div>
          ) : error ? (
            <p className="p-8 text-center text-sm text-red-600">Could not load the audit log (administrators only).</p>
          ) : !data || data.length === 0 ? (
            <p className="p-8 text-center text-sm text-slate-400">No entries.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500">
                  <th className="px-4 py-3 font-medium">When</th>
                  <th className="px-4 py-3 font-medium">Who</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                  <th className="px-4 py-3 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data.map((e) => (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap px-4 py-2 text-slate-500">{format(parseUtc(e.at), "MMM d, HH:mm:ss")}</td>
                    <td className="px-4 py-2 text-slate-700">
                      {e.actor_email ?? "—"} {e.actor_role && <span className="text-slate-400">({e.actor_role})</span>}
                    </td>
                    <td className="px-4 py-2 font-mono text-slate-800">{e.action}</td>
                    <td className="px-4 py-2 text-slate-500">{e.detail ?? e.entity_id ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
