"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { DashboardOverview } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  data: DashboardOverview | null;
  loading: boolean;
}

const COLORS = {
  Occupied: "#1b1a17",
  Vacant: "#2e5b4f",
  Uncertain: "#b8893a",
};

export function OccupancyChart({ data, loading }: Props) {
  if (loading) return <Skeleton className="h-48 w-full" />;
  if (!data) return null;

  const chartData = [
    { name: "Occupied", value: data.occupied_beds },
    { name: "Vacant", value: data.vacant_beds },
    { name: "Uncertain", value: data.uncertain_beds },
  ].filter((d) => d.value > 0);

  if (chartData.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
        No occupancy data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={180}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={70}
          paddingAngle={3}
          dataKey="value"
        >
          {chartData.map((entry) => (
            <Cell
              key={entry.name}
              fill={COLORS[entry.name as keyof typeof COLORS]}
            />
          ))}
        </Pie>
        <Tooltip
          formatter={(value: number) => [value, "Beds"]}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value) => (
            <span className="text-xs text-slate-600">{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
