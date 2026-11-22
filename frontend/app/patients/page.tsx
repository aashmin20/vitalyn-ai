"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { UserPlus, Users } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listPatients } from "@/lib/api/patients";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import { parseUtc } from "@/lib/utils";
import type { Patient } from "@/lib/types";

const FILTERS = [
  { id: "admitted", label: "Admitted" },
  { id: "outpatient", label: "Outpatients" },
  { id: "discharged", label: "Discharged" },
  { id: "all", label: "All" },
] as const;

export default function PatientsPage() {
  const [filter, setFilter] = useState<"admitted" | "discharged" | "outpatient" | "all">("admitted");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setSearch(query), 300);       // wait for a pause in typing
    return () => clearTimeout(t);
  }, [query]);
  const { data: patients, loading, error } = usePoll<Patient[]>(
    useCallback(() => listPatients(filter, search), [filter, search]),
    10_000,
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Patients</h1>
          <p className="text-sm text-slate-500 mt-0.5">Admitted patients and their camera QR codes</p>
        </div>
        <Link href="/patients/new">
          <Button>
            <UserPlus className="mr-2 h-4 w-4" /> Admit patient
          </Button>
        </Link>
      </div>
      <DemoDataBanner />

      <input
        className="w-full max-w-sm rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
        placeholder="Search by name, code or phone"
        value={query}
        maxLength={80}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="flex gap-1">
        {FILTERS.map((f) => (
          <Button key={f.id} size="sm" variant={filter === f.id ? "default" : "ghost"} onClick={() => setFilter(f.id)}>
            {f.label}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-2 p-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : error ? (
            <p className="p-8 text-center text-sm text-red-600">Could not load patients. Is the backend running?</p>
          ) : !patients || patients.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-14 text-slate-400">
              <Users className="h-10 w-10 opacity-30" />
              <p className="text-sm">No {filter === "all" ? "" : filter} patients yet.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                  <th className="px-4 py-3 font-medium">Code</th>
                  <th className="px-4 py-3 font-medium">Patient</th>
                  <th className="px-4 py-3 font-medium">Condition</th>
                  <th className="px-4 py-3 font-medium">Room / bed</th>
                  <th className="px-4 py-3 font-medium">Doctor</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {patients.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono text-xs">
                      <Link href={`/patients/${p.id}`} className="text-slate-900 underline-offset-2 hover:underline">
                        {p.patient_code}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-800">
                      {p.name} <span className="text-slate-400">· {p.age}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{p.condition}</td>
                    <td className="px-4 py-3 text-slate-600">{p.room ? `Room ${p.room.room_number}${p.bed_number ? ` · bed ${p.bed_number}` : ""}` : "-"}</td>
                    <td className="px-4 py-3 text-slate-600">{p.doctor?.name ?? "-"}</td>
                    <td className="px-4 py-3">
                      <Badge variant={p.status === "admitted" ? "success" : "muted"}>{p.status}</Badge>
                      <span className="ml-2 text-[11px] text-slate-400">
                        {format(parseUtc(p.admitted_at), "MMM d")}
                      </span>
                    </td>
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
