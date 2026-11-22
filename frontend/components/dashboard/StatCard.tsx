import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: number | string | null;
  icon: LucideIcon;
  loading?: boolean;
  color?: "default" | "green" | "red" | "amber" | "blue";
  sub?: string;
}

const colorMap = {
  default: "bg-slate-100 text-slate-700",
  green: "bg-emerald-100 text-emerald-700",
  red: "bg-red-100 text-red-700",
  amber: "bg-amber-100 text-amber-700",
  blue: "bg-blue-100 text-blue-700",
};

export function StatCard({ label, value, icon: Icon, loading, color = "default", sub }: StatCardProps) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
            {loading ? (
              <Skeleton className="h-8 w-16 mt-1" />
            ) : (
              <p className="text-3xl font-bold text-slate-900 mt-1">{value ?? "—"}</p>
            )}
            {sub && !loading && (
              <p className="text-xs text-slate-400 mt-1">{sub}</p>
            )}
          </div>
          <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", colorMap[color])}>
            <Icon className="w-5 h-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
