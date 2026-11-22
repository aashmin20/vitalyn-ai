"use client";

import { useCallback, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ShieldCheck } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listStaff, updateStaff, type StaffMember } from "@/lib/api/staff";
import { authErrorMessage, type Role } from "@/lib/api/auth";
import { useAuth } from "@/components/auth/AuthProvider";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { parseUtc } from "@/lib/utils";

const ROLES: Exclude<Role, "none">[] = ["admin", "doctor", "nurse", "receptionist"];

export default function StaffPage() {
  const { user } = useAuth();
  const { data: staff, loading, error, refetch } = usePoll<StaffMember[]>(useCallback(() => listStaff(), []), 10_000);
  const [picked, setPicked] = useState<Record<string, Role>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const apply = async (m: StaffMember, change: { role?: Role; status?: StaffMember["status"] }) => {
    setBusyId(m.id);
    setMessage(null);
    try {
      await updateStaff(m.id, change);
      refetch();
    } catch (e) {
      setMessage(authErrorMessage(e));
    } finally {
      setBusyId(null);
    }
  };

  const pending = (staff ?? []).filter((s) => s.status === "pending");

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <ShieldCheck className="h-6 w-6" /> Staff
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Approve sign-ups and assign roles</p>
      </div>

      {pending.length > 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          {pending.length} account{pending.length > 1 ? "s" : ""} waiting for approval.
        </p>
      )}
      {message && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">{message}</p>}

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-2 p-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : error ? (
            <p className="p-8 text-center text-sm text-red-600">Could not load staff (administrators only).</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Role</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Last sign-in</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {(staff ?? []).map((m) => {
                  const mine = !!user?.id && m.id === user.id;
                  const role = picked[m.id] ?? m.role;
                  return (
                    <tr key={m.id}>
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-800">{m.name}{mine && <span className="ml-1 text-xs text-slate-400">(you)</span>}</p>
                        <p className="text-xs text-slate-400">{m.email}</p>
                      </td>
                      <td className="px-4 py-3">
                        <Select
                          className="h-8 w-40"
                          value={role}
                          disabled={mine || busyId === m.id}
                          onChange={(e) => setPicked((p) => ({ ...p, [m.id]: e.target.value as Role }))}
                        >
                          {role === "none" && <option value="none">No role yet</option>}
                          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                        </Select>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={m.status === "active" ? "success" : m.status === "pending" ? "warning" : "muted"}>{m.status}</Badge>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {m.last_login_at ? formatDistanceToNow(parseUtc(m.last_login_at), { addSuffix: true }) : "never"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {mine ? null : m.status === "pending" ? (
                          <Button size="sm" disabled={busyId === m.id || role === "none"} onClick={() => apply(m, { role, status: "active" })}>
                            Approve
                          </Button>
                        ) : (
                          <div className="flex justify-end gap-2">
                            {role !== m.role && (
                              <Button size="sm" variant="outline" disabled={busyId === m.id} onClick={() => apply(m, { role })}>
                                Save role
                              </Button>
                            )}
                            {m.status === "active" ? (
                              <Button size="sm" variant="ghost" className="text-red-600" disabled={busyId === m.id} onClick={() => apply(m, { status: "disabled" })}>
                                Disable
                              </Button>
                            ) : (
                              <Button size="sm" variant="outline" disabled={busyId === m.id || role === "none"} onClick={() => apply(m, { status: "active" })}>
                                Enable
                              </Button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
